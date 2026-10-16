"""Pointer paths, units and button cleanup using deterministic native substitutes."""

from threading import Event
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from desktop_interface import (ClosedSessionError, Desktop, DisplayTopologyChangedError,
    InputCancelledError, Key, MouseButton, NativeCallError, PermissionRequiredError,
    PixelPoint, Point, Rect, ScrollUnit, UnsupportedFeatureError)
from desktop_interface._backends.macos.events import MacOSEvents
from desktop_interface._native import macos as n
from test_permissions import FakeLibrary


class MouseTests(unittest.TestCase):
    def session(self):
        with patch("sys.platform", "darwin"):
            desktop = Desktop()
        backend = Mock()
        backend.button_state.return_value = False
        backend.key_state.return_value = False
        backend.pointer_position.return_value = Point(-20, 30)
        self.topology = SimpleNamespace(displays=(SimpleNamespace(bounds=Rect(-100, -100, 500, 500)),))
        backend.display_snapshot.return_value = self.topology
        backend.pointer_move.side_effect = lambda point, button, keys: setattr(backend.pointer_position, "return_value", point)
        desktop._backend = backend
        self.desktop, self.backend = desktop, backend
        return desktop.mouse

    def events(self):
        return [(call.args[0], call.args[1]) for call in self.backend.button_event.call_args_list]

    def test_negative_logical_motion_preserves_coordinates_without_pixel_scaling(self):
        mouse = self.session()
        mouse.move(Point(-50.5, 20.25))
        self.backend.pointer_move.assert_called_once_with(Point(-50.5, 20.25), None, ())

    def test_paths_crossing_a_monitor_gap_fail_before_drag_down(self):
        mouse = self.session()
        self.backend.pointer_position.return_value = Point(-80, 20)
        self.topology.displays = (SimpleNamespace(bounds=Rect(-100, 0, 50, 100)),
                                  SimpleNamespace(bounds=Rect(0, 0, 50, 100)))
        with self.assertRaises(ValueError):
            mouse.drag(Point(20, 20), duration=0.1)
        self.backend.button_event.assert_not_called()
        self.backend.pointer_move.assert_not_called()

    def test_nested_and_existing_holds_are_not_released(self):
        mouse = self.session()
        with mouse.hold():
            with mouse.hold():
                self.assertTrue(mouse.is_pressed(MouseButton.LEFT))
            self.assertEqual(self.events(), [(MouseButton.LEFT, True)])
        self.assertEqual(self.events(), [(MouseButton.LEFT, True), (MouseButton.LEFT, False)])
        self.backend.button_event.reset_mock()
        self.backend.button_state.return_value = True
        with mouse.hold():
            pass
        mouse.click()
        self.backend.button_event.assert_not_called()
        with self.assertRaises(UnsupportedFeatureError):
            mouse.drag(Point(0, 0))

    def test_old_context_does_not_release_a_later_acquisition_of_the_same_button(self):
        mouse = self.session()
        with mouse.hold():
            mouse.up()
            mouse.down()
        self.assertTrue(mouse._owned)
        self.assertEqual(self.events(), [(MouseButton.LEFT, True), (MouseButton.LEFT, False), (MouseButton.LEFT, True)])
        self.desktop.close()
        self.assertEqual(self.events()[-1], (MouseButton.LEFT, False))

    def test_drag_emits_drag_motion_and_releases_on_cancel(self):
        mouse = self.session()
        cancel = Event()
        self.backend.pointer_move.side_effect = lambda *args: cancel.set()
        with self.assertRaises(InputCancelledError):
            mouse.drag(Point(40, 40), duration=0.05, cancel=cancel)
        self.assertEqual(self.backend.pointer_move.call_args.args[1], MouseButton.LEFT)
        self.assertEqual(self.events(), [(MouseButton.LEFT, True), (MouseButton.LEFT, False)])
        self.assertFalse(mouse._owned)

    def test_topology_change_aborts_and_releases_drag(self):
        mouse = self.session()
        changed = SimpleNamespace(displays=())
        self.backend.display_snapshot.side_effect = [self.topology, self.topology, self.topology, changed]
        with self.assertRaises(DisplayTopologyChangedError):
            mouse.drag(Point(40, 40), duration=0.05)
        self.assertEqual(self.backend.pointer_move.call_count, 1)
        self.assertEqual(self.events()[-1], (MouseButton.LEFT, False))

    def test_partial_button_failure_attempts_release_and_preserves_primary_error(self):
        mouse = self.session()
        self.backend.button_event.side_effect = [NativeCallError("Fixture down"), None]
        with self.assertRaises(NativeCallError):
            mouse.down()
        self.assertEqual(self.events(), [(MouseButton.LEFT, True), (MouseButton.LEFT, False)])

    def test_cleanup_uses_last_point_if_position_query_fails(self):
        mouse = self.session()
        mouse.down()
        self.backend.pointer_position.side_effect = NativeCallError("Fixture position")
        mouse.up()
        self.assertEqual(self.backend.button_event.call_args.args[2], Point(-20, 30))

    def test_close_releases_mouse_and_keyboard_even_if_one_cleanup_fails(self):
        mouse = self.session()
        self.desktop.keyboard.down(Key.COMMAND)
        with mouse.hold():
            self.backend.button_event.side_effect = NativeCallError("Fixture release")
            with self.assertRaises(ExceptionGroup):
                self.desktop.close()
        self.assertEqual(self.backend.key_event.call_args.args[:2], (Key.COMMAND, False))
        self.assertFalse(mouse._owned)
        with self.assertRaises(ClosedSessionError):
            mouse.position()

    def test_double_click_counts_and_keyboard_modifiers_reach_backend(self):
        mouse = self.session()
        with self.desktop.keyboard.hold(Key.SHIFT):
            mouse.click(count=2, interval=0)
        self.assertEqual([call.args[-1] for call in self.backend.button_event.call_args_list], [1, 1, 2, 2])
        self.assertTrue(all(call.args[3] == (Key.SHIFT,) for call in self.backend.button_event.call_args_list))

    def test_scroll_units_and_signed_deltas_are_explicit(self):
        mouse = self.session()
        mouse.scroll(-3, 2, unit=ScrollUnit.LINE)
        self.backend.scroll_event.assert_called_once_with(-3, 2, ScrollUnit.LINE, ())
        mouse.scroll(4, -5, unit=ScrollUnit.PIXEL)
        self.assertEqual(self.backend.scroll_event.call_args.args[:3], (4, -5, ScrollUnit.PIXEL))

    def test_invalid_values_and_pre_cancel_never_submit_input(self):
        mouse = self.session()
        invalid = (lambda: mouse.move(PixelPoint(1, 2)), lambda: mouse.move(Point(500, 500)),
            lambda: mouse.drag(Point(0, 0), duration=31), lambda: mouse.click(count=True),
            lambda: mouse.click(count=4), lambda: mouse.scroll(True), lambda: mouse.scroll(1 << 31),
            lambda: mouse.scroll(1, unit="line"), lambda: mouse.down("left"),
            lambda: mouse.click(cancel=object()))
        for call in invalid:
            with self.assertRaises((TypeError, ValueError)):
                call()
        cancel = Event()
        cancel.set()
        with self.assertRaises(InputCancelledError):
            mouse.drag(Point(0, 0), cancel=cancel)
        self.backend.pointer_move.assert_not_called()
        self.backend.button_event.assert_not_called()
        self.backend.scroll_event.assert_not_called()

    def test_permission_failure_never_posts_and_multi_button_chords_fail(self):
        mouse = self.session()
        self.backend.require_post_access.side_effect = PermissionRequiredError("Fixture")
        with self.assertRaises(PermissionRequiredError):
            mouse.click()
        self.backend.button_event.assert_not_called()
        self.backend.require_post_access.side_effect = None
        self.backend.button_state.side_effect = lambda button: button is MouseButton.RIGHT
        with self.assertRaises(UnsupportedFeatureError):
            mouse.down(MouseButton.LEFT)
        self.backend.button_event.assert_not_called()


class NativeMouseTests(unittest.TestCase):
    def native(self):
        self.create, self.scroll = Mock(return_value=100), Mock(return_value=101)
        self.post, self.release, self.integer = Mock(), Mock(), Mock()
        self.location = Mock(return_value=n.CGPoint(-25.5, 30))
        self.library = FakeLibrary({"CGEventCreateMouseEvent": self.create,
            "CGEventCreateScrollWheelEvent2": self.scroll, "CGEventPost": self.post,
            "CGEventSetFlags": Mock(), "CGEventSetIntegerValueField": self.integer,
            "CFRelease": self.release, "CGEventSourceKeyState": Mock(return_value=False),
            "CGEventSourceFlagsState": Mock(return_value=0), "CGEventCreate": Mock(return_value=102),
            "CGEventGetLocation": self.location, "CGEventSourceButtonState": Mock(return_value=False)})
        with patch.object(n, "core_graphics", return_value=self.library), \
             patch.object(n, "core_foundation", return_value=self.library):
            return MacOSEvents()

    def test_pointer_read_copies_and_releases_without_posting(self):
        native = self.native()
        self.assertEqual(native.pointer_position(), Point(-25.5, 30))
        self.post.assert_not_called()
        self.release.assert_called_once()

    def test_right_and_middle_buttons_and_drag_event_types(self):
        native = self.native()
        native.button_event(MouseButton.RIGHT, True, Point(-10, 20), (), 2)
        self.assertEqual((self.create.call_args.args[1], self.create.call_args.args[3]), (3, 1))
        self.assertEqual(self.integer.call_args.args[1:], (1, 2))
        native.button_event(MouseButton.MIDDLE, False, Point(-10, 20), (), 1)
        self.assertEqual((self.create.call_args.args[1], self.create.call_args.args[3]), (26, 2))
        native.pointer_move(Point(-10, 20), MouseButton.MIDDLE, ())
        self.assertEqual(self.create.call_args.args[1], 27)
        self.assertEqual(self.release.call_count, 3)

    def test_scroll_uses_fixed_signature_instead_of_variadic_arguments(self):
        native = self.native()
        native.scroll_event(-3, 2, ScrollUnit.PIXEL, ())
        self.scroll.assert_called_once_with(None, 0, 2, -3, 2, 0)
        self.assertEqual(n.CG_SCROLL_EVENT.name, "CGEventCreateScrollWheelEvent2")
        self.assertEqual(len(n.CG_SCROLL_EVENT.argtypes), 6)
        self.release.assert_called_once()

    def test_post_and_decode_failures_release_native_event(self):
        native = self.native()
        self.post.side_effect = NativeCallError("Fixture post")
        with self.assertRaises(NativeCallError):
            native.pointer_move(Point(0, 0), None, ())
        self.release.assert_called_once()
        native = self.native()
        self.location.return_value = n.CGPoint(float("nan"), 0)
        with self.assertRaises(NativeCallError):
            native.pointer_position()
        self.release.assert_called_once()


if __name__ == "__main__":
    unittest.main()
