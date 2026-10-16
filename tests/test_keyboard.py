"""Key ownership, layout boundaries and event failures with no global input."""

import ctypes as c
from threading import Event, Thread
import unittest
from unittest.mock import Mock, patch

from desktop_interface import (ClosedSessionError, Desktop, InputCancelledError,
                               Key, NativeCallError, PermissionRequiredError)
from desktop_interface._backends.macos.events import KEY_CODES, MacOSEvents
from desktop_interface._native import macos as n
from test_permissions import FakeLibrary


class KeyboardTests(unittest.TestCase):
    def session(self):
        with patch("sys.platform", "darwin"):
            desktop = Desktop()
        self.backend = Mock()
        self.backend.key_state.return_value = False
        desktop._backend = self.backend
        self.desktop = desktop
        return desktop.keyboard

    def events(self):
        return [(call.args[0], call.args[1]) for call in self.backend.key_event.call_args_list]

    def test_press_and_shortcut_order_release_modifiers_last(self):
        keyboard = self.session()
        keyboard.shortcut(Key.COMMAND, Key.SHIFT, Key.A)
        self.assertEqual(self.events(), [(Key.COMMAND, True), (Key.SHIFT, True), (Key.A, True),
                                        (Key.A, False), (Key.SHIFT, False), (Key.COMMAND, False)])
        self.assertFalse(keyboard._owned)

    def test_existing_physical_keys_and_nested_holds_are_not_released(self):
        keyboard = self.session()
        self.backend.key_state.side_effect = lambda key: key is Key.SHIFT
        with keyboard.hold(Key.SHIFT, Key.COMMAND):
            with keyboard.hold(Key.COMMAND):
                self.assertTrue(keyboard.is_pressed(Key.COMMAND))
            self.assertEqual(self.events(), [(Key.COMMAND, True)])
        self.assertEqual(self.events(), [(Key.COMMAND, True), (Key.COMMAND, False)])

    def test_exception_and_cancel_release_every_acquired_key(self):
        keyboard = self.session()
        with self.assertRaises(RuntimeError):
            with keyboard.hold(Key.COMMAND, Key.SHIFT):
                raise RuntimeError("Fixture")
        self.assertEqual(self.events()[-2:], [(Key.SHIFT, False), (Key.COMMAND, False)])
        cancel = Event()
        def post(key, down, owned):
            if down:
                cancel.set()
        self.backend.key_event.side_effect = post
        with self.assertRaises(InputCancelledError):
            keyboard.press(Key.A, duration=1, cancel=cancel)
        self.assertEqual(self.events()[-2:], [(Key.A, True), (Key.A, False)])

    def test_partial_acquisition_releases_the_uncertain_down_and_prior_keys(self):
        keyboard = self.session()
        def post(key, down, owned):
            if down and key is Key.SHIFT:
                raise NativeCallError("Fixture")
        self.backend.key_event.side_effect = post
        with self.assertRaises(NativeCallError):
            with keyboard.hold(Key.COMMAND, Key.SHIFT):
                self.fail("Acquisition should fail")
        self.assertEqual(self.events()[-2:], [(Key.SHIFT, False), (Key.COMMAND, False)])
        self.assertFalse(keyboard._owned)

    def test_failed_release_does_not_skip_other_releases(self):
        keyboard = self.session()
        keyboard.down(Key.COMMAND)
        keyboard.down(Key.SHIFT)
        self.backend.key_event.side_effect = NativeCallError("Fixture release")
        with self.assertRaises(ExceptionGroup) as caught:
            self.desktop.close()
        self.assertEqual(len(caught.exception.exceptions), 2)
        self.assertEqual(self.events()[-2:], [(Key.SHIFT, False), (Key.COMMAND, False)])
        self.assertTrue(self.desktop.closed)
        self.desktop.close()

    def test_close_from_another_thread_releases_keys_inside_a_context(self):
        keyboard = self.session()
        with keyboard.hold(Key.COMMAND):
            worker = Thread(target=self.desktop.close)
            worker.start()
            worker.join(timeout=2)
            self.assertFalse(worker.is_alive())
        self.assertEqual(self.events(), [(Key.COMMAND, True), (Key.COMMAND, False)])
        with self.assertRaises(ClosedSessionError):
            keyboard.press(Key.A)

    def test_up_never_releases_an_unowned_key_and_down_is_idempotent(self):
        keyboard = self.session()
        self.assertFalse(keyboard.up(Key.A))
        self.assertTrue(keyboard.down(Key.A))
        self.assertFalse(keyboard.down(Key.A))
        self.assertTrue(keyboard.up(Key.A))
        self.assertFalse(keyboard.up(Key.A))
        self.assertEqual(self.events(), [(Key.A, True), (Key.A, False)])

    def test_unicode_scalars_preserve_pairs_and_do_not_translate_physical_keys(self):
        keyboard = self.session()
        keyboard.type_text("é👋\0")
        payloads = [call.args[0] for call in self.backend.text_pair.call_args_list]
        self.assertEqual(payloads, [value.encode("utf-16-le") for value in "é👋\0"])
        self.backend.key_event.assert_not_called()
        self.assertEqual(len(payloads[1]), 4)

    def test_all_invalid_inputs_and_pre_cancel_are_rejected_before_posting(self):
        keyboard = self.session()
        cancel = Event()
        cancel.set()
        invalid = (lambda: keyboard.press("a"), lambda: keyboard.press(True),
            lambda: keyboard.press(Key.A, duration=-1), lambda: keyboard.press(Key.A, cancel=object()),
            lambda: keyboard.shortcut(Key.A, Key.COMMAND), lambda: keyboard.shortcut(Key.COMMAND, Key.COMMAND),
            lambda: keyboard.type_text("a\ud800"), lambda: keyboard.type_text("a" * 16385),
            lambda: keyboard.type_text("a" * 100, interval=1), lambda: keyboard.type_text(1))
        for call in invalid:
            with self.assertRaises((ValueError, TypeError)):
                call()
        with self.assertRaises(InputCancelledError):
            keyboard.press(Key.A, cancel=cancel)
        self.backend.require_post_access.assert_not_called()
        self.backend.key_event.assert_not_called()
        self.backend.text_pair.assert_not_called()

    def test_missing_permission_prevents_submission(self):
        keyboard = self.session()
        self.backend.require_post_access.side_effect = PermissionRequiredError("Fixture")
        with self.assertRaises(PermissionRequiredError):
            keyboard.press(Key.A)
        with self.assertRaises(PermissionRequiredError):
            keyboard.type_text("Fixture")
        self.backend.key_event.assert_not_called()
        self.backend.text_pair.assert_not_called()


class NativeKeyTests(unittest.TestCase):
    def native(self):
        self.post, self.release = Mock(), Mock()
        self.flags, self.unicode = Mock(), Mock()
        self.create = Mock(side_effect=[100, 101])
        self.state = Mock(return_value=False)
        library = FakeLibrary({"CGEventCreateKeyboardEvent": self.create,
            "CGEventPost": self.post, "CGEventSetFlags": self.flags,
            "CGEventKeyboardSetUnicodeString": self.unicode,
            "CGEventSourceFlagsState": Mock(return_value=1 << 16),
            "CGEventSourceKeyState": self.state, "CFRelease": self.release})
        with patch.object(n, "core_graphics", return_value=library), \
             patch.object(n, "core_foundation", return_value=library):
            return MacOSEvents()

    def test_every_physical_position_has_a_unique_native_code(self):
        self.assertEqual(set(KEY_CODES), set(Key))
        self.assertEqual(len(set(KEY_CODES.values())), len(Key))
        self.assertEqual(KEY_CODES[Key.Z], 6)  # US reference position, not text translation
        self.assertEqual(KEY_CODES[Key.RIGHT_COMMAND], 54)

    def test_explicit_flags_preserve_caps_and_owned_modifiers(self):
        native = self.native()
        native.key_event(Key.A, True, (Key.SHIFT, Key.COMMAND))
        self.assertEqual(self.create.call_args.args, (None, 0, True))
        self.assertEqual(self.flags.call_args.args[1], (1 << 16) | (1 << 17) | (1 << 20))
        self.post.assert_called_once()
        self.release.assert_called_once()

    def test_releasing_one_side_preserves_the_other_side(self):
        native = self.native()
        self.state.side_effect = lambda state, code: code == KEY_CODES[Key.RIGHT_SHIFT]
        native.key_event(Key.SHIFT, False, ())
        self.assertTrue(self.flags.call_args.args[1] & (1 << 17))

    def test_unicode_payload_uses_utf16_units_and_both_events_are_released(self):
        native = self.native()
        native.text_pair("👋".encode("utf-16-le"), ())
        self.assertEqual(self.unicode.call_count, 2)
        self.assertEqual(self.unicode.call_args.args[1], 2)
        self.assertEqual(bytes(self.unicode.call_args.args[2]), "👋".encode("utf-16-le"))
        self.assertEqual([call.args[1].value for call in self.post.call_args_list], [100, 101])
        self.assertEqual([call.args[0].value for call in self.release.call_args_list], [101, 100])

    def test_allocation_failure_prevents_text_submission_and_frees_prior_event(self):
        native = self.native()
        self.create.side_effect = [100, None]
        with self.assertRaises(NativeCallError):
            native.text_pair(b"a\0", ())
        self.post.assert_not_called()
        self.release.assert_called_once()

    def test_post_failure_still_attempts_prepared_text_release(self):
        native = self.native()
        self.post.side_effect = [NativeCallError("Fixture"), None]
        with self.assertRaises(NativeCallError):
            native.text_pair(b"a\0", ())
        self.assertEqual(self.post.call_count, 2)
        self.assertEqual(self.release.call_count, 2)


if __name__ == "__main__":
    unittest.main()
