"""Permission semantics and session lifetime without invoking system prompts."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError
from threading import Event
import unittest
from unittest.mock import Mock, patch

from desktop_interface import (
    Backend, ClosedSessionError, Desktop, Feature, NativeCallError,
    NativeSymbolError, Permission, PermissionState, PermissionStatus, Support,
    UnsupportedPlatformError,
)
from desktop_interface._backends.macos.permissions import MacOSPermissions


class FakeLibrary:
    def __init__(self, functions=None, variables=None):
        self.functions = functions or {}
        self.variables = variables or {}
        self.bound = []

    def bind(self, spec):
        self.bound.append(spec.name)
        if spec.name not in self.functions:
            raise NativeSymbolError(spec.name)
        return self.functions[spec.name]

    def variable(self, name, ctype):
        if name not in self.variables:
            raise NativeSymbolError(name)
        return ctype(self.variables[name])


class MacOSPermissionTests(unittest.TestCase):
    def make_permissions(self, *, granted=False, request_result=False):
        self.checks = {name: Mock(return_value=granted) for name in (
            "CGPreflightListenEventAccess", "CGPreflightPostEventAccess",
            "CGPreflightScreenCaptureAccess", "AXIsProcessTrusted",
        )}
        self.requests = {name: Mock(return_value=request_result) for name in (
            "CGRequestListenEventAccess", "CGRequestPostEventAccess",
            "CGRequestScreenCaptureAccess", "AXIsProcessTrustedWithOptions",
        )}
        self.release = Mock()
        self.create = Mock(return_value=900)
        self.cg = FakeLibrary(self.checks | self.requests)
        self.app = FakeLibrary(self.checks | self.requests, {"kAXTrustedCheckOptionPrompt": 100})
        self.cf = FakeLibrary(
            {"CFRelease": self.release, "CFDictionaryCreate": self.create},
            {"kCFBooleanTrue": 200},
        )
        module = "desktop_interface._backends.macos.permissions.native"
        with patch(module + ".core_graphics", return_value=self.cg), \
             patch(module + ".application_services", return_value=self.app), \
             patch(module + ".core_foundation", return_value=self.cf):
            return MacOSPermissions()

    def test_preflight_never_requests_access_and_false_stays_unknown(self):
        permissions = self.make_permissions()
        for permission in Permission:
            report = permissions.check(permission)
            self.assertIs(report.state, PermissionState.UNKNOWN)
            self.assertFalse(report.granted)
            self.assertFalse(report.request_sent)
            self.assertIsNone(report.restart_required)
        for request in self.requests.values():
            request.assert_not_called()
        self.create.assert_not_called()

    def test_granted_preflight_skips_request_paths(self):
        permissions = self.make_permissions(granted=True)
        for permission in Permission:
            report = permissions.request(permission)
            self.assertTrue(report.granted)
            self.assertFalse(report.request_sent)
        for request in self.requests.values():
            request.assert_not_called()

    def test_coregraphics_requests_preserve_current_grant_or_unknown(self):
        for result in (False, True):
            permissions = self.make_permissions(request_result=result)
            for permission in (Permission.INPUT_MONITORING, Permission.POST_EVENTS, Permission.SCREEN_CAPTURE):
                with self.subTest(result=result, permission=permission):
                    report = permissions.request(permission)
                    self.assertIs(report.granted, result)
                    self.assertTrue(report.request_sent)
                    self.assertIs(report.state, PermissionState.GRANTED if result else PermissionState.UNKNOWN)
                    self.assertIsNone(report.restart_required)

    def test_accessibility_options_borrow_constants_and_release_dictionary(self):
        permissions = self.make_permissions()
        report = permissions.request(Permission.ACCESSIBILITY)
        self.assertTrue(report.request_sent)
        self.assertIs(report.state, PermissionState.UNKNOWN)
        allocator, keys, values, count, key_callbacks, value_callbacks = self.create.call_args.args
        self.assertIsNone(allocator)
        self.assertEqual((keys[0], values[0], count), (100, 200, 1))
        self.assertIsNone(key_callbacks)
        self.assertIsNone(value_callbacks)
        self.assertEqual(self.requests["AXIsProcessTrustedWithOptions"].call_args.args[0].value, 900)
        self.assertEqual(self.release.call_args.args[0].value, 900)
        self.release.assert_called_once()

    def test_accessibility_request_exception_still_releases_options(self):
        permissions = self.make_permissions()
        self.requests["AXIsProcessTrustedWithOptions"].side_effect = NativeCallError("Fixture")
        with self.assertRaises(NativeCallError):
            permissions.request(Permission.ACCESSIBILITY)
        self.release.assert_called_once()

    def test_null_dictionary_or_constants_do_not_submit_a_request(self):
        for null_constant in (False, True):
            permissions = self.make_permissions()
            if null_constant:
                self.app.variables["kAXTrustedCheckOptionPrompt"] = 0
            else:
                self.create.return_value = 0
            with self.assertRaises(NativeCallError):
                permissions.request(Permission.ACCESSIBILITY)
            self.requests["AXIsProcessTrustedWithOptions"].assert_not_called()
            self.release.assert_not_called()

    def test_missing_check_or_request_is_explicitly_unavailable(self):
        permissions = self.make_permissions()
        del self.cg.functions["CGPreflightPostEventAccess"]
        report = permissions.check(Permission.POST_EVENTS)
        self.assertIs(report.support, Support.UNSUPPORTED)
        self.assertIs(report.state, PermissionState.UNKNOWN)
        report = permissions.request(Permission.POST_EVENTS)
        self.assertFalse(report.request_sent)
        permissions = self.make_permissions()
        del self.cg.functions["CGRequestPostEventAccess"]
        report = permissions.request(Permission.POST_EVENTS)
        self.assertIs(report.support, Support.UNSUPPORTED)
        self.assertFalse(report.request_sent)


class DesktopTests(unittest.TestCase):
    def session(self):
        with patch("sys.platform", "darwin"):
            return Desktop()

    def test_construction_and_capabilities_are_passive(self):
        with patch("ctypes.CDLL", side_effect=AssertionError("Native load")):
            desktop = self.session()
            self.assertIs(desktop.backend, Backend.MACOS)
            reports = desktop.capabilities()
            self.assertEqual({report.feature for report in reports}, set(Feature))
            supported = {report.feature for report in reports if report.support is Support.SUPPORTED}
            self.assertEqual(supported, {Feature.DISPLAY_INFO, Feature.WINDOW_INFO, Feature.WINDOW_CONTROL})
            desktop.close()

    def test_unimplemented_or_mismatched_backends_fail_without_loading(self):
        with patch("ctypes.CDLL", side_effect=AssertionError("Native load")):
            for platform, backend in (("linux", None), ("win32", None),
                                      ("darwin", Backend.WINDOWS), ("linux", Backend.MACOS)):
                with self.subTest(platform=platform, backend=backend), patch("sys.platform", platform):
                    with self.assertRaises(UnsupportedPlatformError):
                        Desktop(backend)
            with self.assertRaises(ValueError):
                Desktop("unrecognized")
            with self.assertRaises(TypeError):
                Desktop(1)

    def test_session_context_and_retained_managers_reject_use_after_close(self):
        desktop = self.session()
        manager = desktop.permissions
        with desktop:
            self.assertFalse(desktop.closed)
        desktop.close()
        self.assertTrue(desktop.closed)
        for operation in (desktop.capabilities, desktop.__enter__, manager.check_all,
                          lambda: manager.check(Permission.ACCESSIBILITY),
                          lambda: manager.request(Permission.ACCESSIBILITY)):
            with self.assertRaises(ClosedSessionError):
                operation()

    def test_session_closes_when_context_body_raises(self):
        desktop = self.session()
        with self.assertRaises(ValueError):
            with desktop:
                raise ValueError("Fixture")
        self.assertTrue(desktop.closed)

    def test_fake_denial_remains_distinct_from_unknown(self):
        desktop = self.session()
        denied = PermissionStatus(Backend.MACOS, Permission.ACCESSIBILITY, PermissionState.DENIED)
        with patch.object(desktop._backend, "check_permission", return_value=denied):
            self.assertIs(desktop.permissions.check(Permission.ACCESSIBILITY).state, PermissionState.DENIED)
        for operation in (desktop.permissions.check, desktop.permissions.request):
            with self.assertRaises(TypeError):
                operation("accessibility")

    def test_explicit_requests_require_main_thread(self):
        desktop = self.session()
        with patch.object(desktop._backend, "request_permission") as request:
            with ThreadPoolExecutor(max_workers=1) as executor:
                result = executor.submit(desktop.permissions.request, Permission.ACCESSIBILITY)
                with self.assertRaises(RuntimeError):
                    result.result(timeout=10)
            request.assert_not_called()

    def test_close_waits_for_an_inflight_operation(self):
        desktop = self.session()
        entered, release, closing = Event(), Event(), Event()
        expected = PermissionStatus(Backend.MACOS, Permission.POST_EVENTS, PermissionState.UNKNOWN)

        def check(permission):
            entered.set()
            if not release.wait(timeout=10):
                raise TimeoutError("Fixture was not released")
            return expected

        def close():
            closing.set()
            desktop.close()

        with patch.object(desktop._backend, "check_permission", side_effect=check), \
             ThreadPoolExecutor(max_workers=2) as executor:
            operation = executor.submit(desktop.permissions.check, Permission.POST_EVENTS)
            try:
                self.assertTrue(entered.wait(timeout=5))
                cleanup = executor.submit(close)
                self.assertTrue(closing.wait(timeout=5))
                self.assertFalse(cleanup.done())
            finally:
                release.set()
            self.assertIs(operation.result(timeout=10), expected)
            cleanup.result(timeout=10)
        self.assertTrue(desktop.closed)

    def test_permission_status_is_validated_and_immutable(self):
        status = PermissionStatus(Backend.MACOS, Permission.POST_EVENTS, PermissionState.UNKNOWN)
        with self.assertRaises(FrozenInstanceError):
            status.request_sent = True
        for overrides in ({"state": "denied"}, {"request_sent": 1},
                          {"restart_required": 0}, {"detail": 42}):
            args = {"backend": Backend.MACOS, "permission": Permission.POST_EVENTS,
                    "state": PermissionState.UNKNOWN} | overrides
            with self.assertRaises(TypeError):
                PermissionStatus(**args)


if __name__ == "__main__":
    unittest.main()
