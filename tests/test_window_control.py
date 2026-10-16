"""Window matching, supported setters and bounded confirmation without a desktop."""

import ctypes as c
import unittest
from unittest.mock import Mock, patch

from cf_fixture import CFHeap
from desktop_interface import (AmbiguousTargetError, Backend, ClosedSessionError, Desktop,
    NativeCallError, OperationTimeoutError, PermissionRequiredError, Point, Rect, Size,
    StaleTargetError, UnsupportedFeatureError, Window, WindowId, WindowInfo, WindowState)
from desktop_interface._backends.macos.window_control import MacOSWindowControl, _status


class AXHeap(CFHeap):
    TYPES = CFHeap.TYPES | {"element": 6, "value": 7}

    def __init__(self):
        super().__init__()
        self.info = WindowInfo(WindowId(Backend.MACOS, 7), 42, Rect(10, 20, 300, 200), "Fixture")
        self.app = self.add("element", {})
        self.window = self.make_window()
        self.objects[self.app][1].update({"AXWindows": self.add("array", [self.window]),
            "AXFrontmost": self.add("boolean", False), "AXFocusedWindow": self.window})
        self.unsettable = set()
        self.true, self.false = self.add("boolean", True), self.add("boolean", False)
        self.functions.update({
            "CFStringCreateWithBytes": Mock(side_effect=lambda alloc, data, size, enc, external:
                self.add("string", bytes(data[:size]).decode("utf-8"))),
            "CFEqual": Mock(side_effect=lambda a, b: self.address(a) == self.address(b)),
            "AXUIElementCreateApplication": Mock(return_value=self.app),
            "AXUIElementGetTypeID": Mock(return_value=6),
            "AXValueGetTypeID": Mock(return_value=7),
            "AXUIElementSetMessagingTimeout": Mock(return_value=0),
            "AXUIElementGetPid": Mock(side_effect=self.pid),
            "AXUIElementCopyAttributeValue": Mock(side_effect=self.copy),
            "AXUIElementIsAttributeSettable": Mock(side_effect=self.settable),
            "AXUIElementSetAttributeValue": Mock(side_effect=self.set),
            "AXUIElementCopyActionNames": Mock(side_effect=self.actions),
            "AXUIElementPerformAction": Mock(return_value=0),
            "AXValueCreate": Mock(side_effect=self.value_create),
            "AXValueGetType": Mock(side_effect=lambda p: self.object(p)[1][0]),
            "AXValueGetValue": Mock(side_effect=self.value_get),
        })
        self.windows = Mock()
        self.windows.get.return_value = self.info

    def variable(self, name, ctype):
        return ctype(self.true if name == "kCFBooleanTrue" else self.false)

    def make_window(self):
        return self.add("element", {"AXPosition": self.add("value", (1, (10, 20))),
            "AXSize": self.add("value", (2, (300, 200))), "AXTitle": self.add("string", "Fixture"),
            "AXMinimized": self.add("boolean", False)})

    def pid(self, element, output):
        output._obj.value = 42
        return 0

    def copy(self, element, name, output):
        pointer = self.object(element)[1].get(self.object(name)[1])
        if pointer is None:
            return -25212
        output._obj.value = pointer
        return 0

    def settable(self, element, name, output):
        output._obj.value = self.object(name)[1] not in self.unsettable
        return 0

    def set(self, element, name, value):
        self.object(element)[1][self.object(name)[1]] = self.address(value)
        return 0

    def actions(self, element, output):
        output._obj.value = self.add("array", [self.add("string", "AXRaise")])
        return 0

    def value_create(self, kind, data):
        value = data._obj
        return self.add("value", (kind, (value.x, value.y) if kind == 1 else (value.width, value.height)))

    def value_get(self, pointer, kind, output):
        a, b = self.object(pointer)[1][1]
        if kind == 1:
            output._obj.x, output._obj.y = a, b
        else:
            output._obj.width, output._obj.height = a, b
        return True

    def run(self, action=None, value=None, timeout=None):
        with patch("desktop_interface._native.macos.core_foundation", return_value=self.library), \
             patch("desktop_interface._native.macos.application_services", return_value=self.library):
            return MacOSWindowControl(self.windows).run(self.info, action, value, timeout)


class WindowControlTests(unittest.TestCase):
    def test_move_resize_and_minimize_confirm_copied_state(self):
        for action, value, expected in (("move", Point(-20, 35), Rect(-20, 35, 300, 200)),
                                        ("resize", Size(400, 250), Rect(10, 20, 400, 250)),
                                        ("minimize", True, Rect(10, 20, 300, 200))):
            with self.subTest(action=action):
                fixture = AXHeap()
                if action in ("move", "resize"):
                    updated = WindowInfo(fixture.info.id, 42, expected, "Fixture")
                    fixture.windows.get.side_effect = [fixture.info, updated]
                state = fixture.run(action, value, 0)
                self.assertEqual(state.bounds, expected)
                self.assertEqual(state.minimized, action == "minimize")
                self.assertIn(fixture.app, fixture.released)
                # The array member is borrowed, but AXFocusedWindow returns an owned copy.
                self.assertEqual(fixture.released.count(fixture.window), 1)
                fixture.functions["AXUIElementIsAttributeSettable"].assert_called_once()

    def test_confirmed_geometry_waits_for_quartz_to_catch_up_without_reposting(self):
        fixture = AXHeap()
        updated = WindowInfo(fixture.info.id, 42, Rect(30, 40, 300, 200), "Fixture")
        fixture.windows.get.side_effect = [fixture.info, fixture.info, updated]
        state = fixture.run("move", Point(30, 40), 1)
        self.assertEqual(state.bounds, updated.bounds)
        self.assertEqual(fixture.windows.get.call_count, 3)
        fixture.functions["AXUIElementSetAttributeValue"].assert_called_once()

    def test_focus_checks_every_operation_before_writing_and_confirms(self):
        fixture = AXHeap()
        self.assertTrue(fixture.run("focus", timeout=0).focused)
        fixture.functions["AXUIElementPerformAction"].assert_called_once()
        fixture = AXHeap()
        fixture.unsettable.add("AXMain")
        with self.assertRaises(UnsupportedFeatureError):
            fixture.run("focus")
        fixture.functions["AXUIElementSetAttributeValue"].assert_not_called()
        fixture.functions["AXUIElementPerformAction"].assert_not_called()

    def test_readonly_focused_window_does_not_block_advertised_main_window_focus(self):
        fixture = AXHeap()
        fixture.unsettable.add("AXFocusedWindow")
        self.assertTrue(fixture.run("focus", timeout=0).focused)
        written = [fixture.object(call.args[1])[1]
                   for call in fixture.functions["AXUIElementSetAttributeValue"].call_args_list]
        self.assertEqual(written, ["AXMain", "AXFrontmost"])

    def test_unadvertised_raise_is_rejected_before_any_focus_change(self):
        fixture = AXHeap()
        def actions(element, output):
            output._obj.value = fixture.add("array", [])
            return 0
        fixture.functions["AXUIElementCopyActionNames"].side_effect = actions
        with self.assertRaises(UnsupportedFeatureError):
            fixture.run("focus")
        fixture.functions["AXUIElementSetAttributeValue"].assert_not_called()

    def test_no_confirmation_means_submission_only(self):
        fixture = AXHeap()
        self.assertIsNone(fixture.run("move", Point(30, 40)))
        fixture.functions["AXUIElementSetAttributeValue"].assert_called_once()

    def test_application_adjustment_times_out_without_retrying_write(self):
        fixture = AXHeap()
        fixture.functions["AXUIElementSetAttributeValue"].side_effect = None
        fixture.functions["AXUIElementSetAttributeValue"].return_value = 0
        with self.assertRaises(OperationTimeoutError):
            fixture.run("resize", Size(400, 300), 0)
        fixture.functions["AXUIElementSetAttributeValue"].assert_called_once()

    def test_same_metadata_is_ambiguous_and_changed_metadata_is_stale(self):
        fixture = AXHeap()
        fixture.objects[fixture.app][1]["AXWindows"] = fixture.add("array", [fixture.window, fixture.make_window()])
        with self.assertRaises(AmbiguousTargetError):
            fixture.run("minimize", True)
        fixture.functions["AXUIElementSetAttributeValue"].assert_not_called()
        fixture = AXHeap()
        fixture.windows.get.return_value = WindowInfo(fixture.info.id, 42, Rect(11, 20, 300, 200), "Fixture")
        with self.assertRaises(StaleTargetError):
            fixture.run("minimize", True)
        fixture.functions["AXUIElementSetAttributeValue"].assert_not_called()

    def test_missing_title_can_match_bounds_but_wrong_title_cannot(self):
        fixture = AXHeap()
        fixture.info = WindowInfo(fixture.info.id, 42, fixture.info.bounds)
        fixture.windows.get.return_value = fixture.info
        self.assertEqual(fixture.run().bounds, fixture.info.bounds)
        fixture = AXHeap()
        fixture.objects[fixture.window][1]["AXTitle"] = fixture.add("string", "Other")
        with self.assertRaises(StaleTargetError):
            fixture.run()

    def test_malformed_values_and_excessive_windows_fail_without_setters(self):
        for malformed in (True, False):
            fixture = AXHeap()
            if malformed:
                fixture.objects[fixture.window][1]["AXPosition"] = fixture.add("string", "invalid")
            else:
                fixture.objects[fixture.app][1]["AXWindows"] = fixture.add("array", [fixture.window] * 129)
            with self.assertRaises(NativeCallError):
                fixture.run("move", Point(50, 50))
            fixture.functions["AXUIElementSetAttributeValue"].assert_not_called()
            self.assertIn(fixture.app, fixture.released)

    def test_native_errors_preserve_codes_and_cleanup(self):
        for code, expected in ((-25204, NativeCallError), (-25202, StaleTargetError),
                                (-25205, UnsupportedFeatureError), (-25211, PermissionRequiredError)):
            fixture = AXHeap()
            fixture.functions["AXUIElementSetAttributeValue"].side_effect = None
            fixture.functions["AXUIElementSetAttributeValue"].return_value = code
            with self.assertRaises(expected) as caught:
                fixture.run("minimize", True)
            native = caught.exception if isinstance(caught.exception, NativeCallError) else caught.exception.__cause__
            self.assertEqual(native.code, code)
            self.assertIn(fixture.app, fixture.released)

    def test_query_budget_expiration_stops_before_a_write(self):
        fixture = AXHeap()
        with patch("desktop_interface._backends.macos.window_control.time.monotonic", side_effect=[0, 6]):
            with self.assertRaises(OperationTimeoutError):
                fixture.run("minimize", True)
        fixture.functions["AXUIElementSetAttributeValue"].assert_not_called()
        self.assertIn(fixture.app, fixture.released)

    def test_missing_bounds_or_unsigned_pid_cannot_be_used_for_control(self):
        for pid, bounds in ((42, None), (0, Rect(0, 0, 2, 2)), (0xFFFFFFFF, Rect(0, 0, 2, 2))):
            fixture = AXHeap()
            fixture.info = WindowInfo(fixture.info.id, pid, bounds)
            with self.assertRaises(UnsupportedFeatureError):
                fixture.run("focus")
            fixture.functions["AXUIElementCreateApplication"].assert_not_called()

    def test_permission_and_python_validation_precede_control(self):
        with patch("sys.platform", "darwin"):
            desktop = Desktop()
        window = Window(desktop, AXHeap().info)
        with patch.object(desktop._backend, "window_control") as control:
            for call in (lambda: window.move((1, 2)), lambda: window.resize(Size(0, 2)),
                         lambda: window.minimize(1), lambda: window.focus(timeout=True),
                         lambda: window.focus(timeout=31)):
                with self.assertRaises((TypeError, ValueError)):
                    call()
            control.assert_not_called()
        with patch.object(desktop._backend, "check_permission") as permission, \
             patch.object(desktop._backend._window_control, "run") as run:
            permission.return_value.granted = False
            with self.assertRaises(PermissionRequiredError):
                window.focus()
            run.assert_not_called()
        desktop.close()
        with self.assertRaises(ClosedSessionError):
            window.state()


if __name__ == "__main__":
    unittest.main()
