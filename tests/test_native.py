"""Native declaration and ownership behavior using isolated synthetic objects."""

from concurrent.futures import ThreadPoolExecutor
import ctypes
import sys
from threading import Barrier
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from desktop_interface import NativeLibraryError, NativeSymbolError, UnsupportedPlatformError
from desktop_interface._native.binding import FunctionSpec, NativeLibrary
from desktop_interface._native.macos import core_foundation, core_graphics
from desktop_interface._native.ownership import OwnedReference


class BindingTests(unittest.TestCase):
    def library(self, handle=None, *, loader=None, platform=None):
        if loader is None:
            loader = Mock(return_value=handle)
        return NativeLibrary("/system/libfixture", platform=platform or sys.platform, loader=loader), loader

    def test_construction_and_macos_factories_are_passive(self):
        with patch("ctypes.CDLL", side_effect=AssertionError("Native load")):
            self.assertEqual(core_foundation().platform, "darwin")
            self.assertEqual(core_graphics().platform, "darwin")
            self.library()

    def test_relative_paths_and_incomplete_declarations_fail(self):
        with self.assertRaises(ValueError):
            NativeLibrary("libfixture", platform=sys.platform)
        with self.assertRaises(TypeError):
            NativeLibrary(None, platform=sys.platform)
        with self.assertRaises(TypeError):
            FunctionSpec("Fixture", ())
        with self.assertRaises(TypeError):
            FunctionSpec("Fixture", [], None)
        with self.assertRaises(ValueError):
            FunctionSpec("", (), None)

    def test_wrong_platform_rejects_before_loading(self):
        library, loader = self.library(platform="unavailable-platform")
        with self.assertRaises(UnsupportedPlatformError):
            library.bind(FunctionSpec("Fixture", (), None))
        loader.assert_not_called()

    def test_macos_32_bit_process_is_rejected_before_loading(self):
        library, loader = self.library(platform="darwin")
        with patch("sys.platform", "darwin"), patch("ctypes.sizeof", return_value=4):
            with self.assertRaises(UnsupportedPlatformError):
                library.bind(FunctionSpec("Fixture", (), None))
        loader.assert_not_called()

    def test_pointer_result_keeps_full_native_width(self):
        address = (1 << (ctypes.sizeof(ctypes.c_void_p) * 8 - 2)) + 123
        callback = ctypes.CFUNCTYPE(ctypes.c_void_p)(lambda: address)
        library, loader = self.library(SimpleNamespace(Fixture=callback))
        function = library.bind(FunctionSpec("Fixture", (), ctypes.c_void_p))
        self.assertEqual(function(), address)
        self.assertEqual(function.argtypes, [])
        self.assertIs(function.restype, ctypes.c_void_p)
        loader.assert_called_once_with("/system/libfixture")

    def test_void_result_is_explicit_and_binding_does_not_invoke(self):
        function = Mock()
        library, _ = self.library(SimpleNamespace(Fixture=function))
        self.assertIs(library.bind(FunctionSpec("Fixture", (), None)), function)
        self.assertIsNone(function.restype)
        self.assertEqual(function.argtypes, [])
        function.assert_not_called()

    def test_missing_library_preserves_the_loader_error(self):
        cause = OSError("Fixture library missing")
        library, _ = self.library(loader=Mock(side_effect=cause))
        with self.assertRaises(NativeLibraryError) as result:
            library.bind(FunctionSpec("Fixture", (), None))
        self.assertIs(result.exception.__cause__, cause)

    def test_missing_symbol_does_not_poison_other_functions(self):
        library, loader = self.library(SimpleNamespace(Available=Mock()))
        with self.assertRaises(NativeSymbolError) as result:
            library.bind(FunctionSpec("Missing", (), None))
        self.assertIsInstance(result.exception.__cause__, AttributeError)
        self.assertIsNotNone(library.bind(FunctionSpec("Available", (), None)))
        loader.assert_called_once()

    def test_cached_symbol_cannot_be_redeclared_incompatibly(self):
        library, loader = self.library(SimpleNamespace(Fixture=Mock()))
        original = library.bind(FunctionSpec("Fixture", (ctypes.c_void_p,), None))
        with self.assertRaises(ValueError):
            library.bind(FunctionSpec("Fixture", (ctypes.c_int,), None))
        self.assertEqual(original.argtypes, [ctypes.c_void_p])
        loader.assert_called_once()

    def test_concurrent_binding_loads_and_configures_once(self):
        library, loader = self.library(SimpleNamespace(Fixture=Mock()))
        barrier = Barrier(8)

        def bind():
            barrier.wait(timeout=10)
            return library.bind(FunctionSpec("Fixture", (), None))

        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(bind) for _ in range(8)]
            functions = [future.result(timeout=15) for future in futures]
        self.assertTrue(all(function is functions[0] for function in functions))
        loader.assert_called_once()

    def test_exported_variable_uses_an_explicit_type_and_shared_lazy_handle(self):
        handle = SimpleNamespace(Fixture=Mock())
        library, loader = self.library(handle)
        ctype = Mock()
        ctype.in_dll.return_value = ctypes.c_void_p(123)
        self.assertEqual(library.variable("FixtureGlobal", ctype).value, 123)
        library.bind(FunctionSpec("Fixture", (), None))
        ctype.in_dll.assert_called_once_with(handle, "FixtureGlobal")
        loader.assert_called_once()
        with self.assertRaises(ValueError):
            library.variable("", ctype)
        with self.assertRaises(TypeError):
            library.variable("FixtureGlobal", object)

    def test_missing_exported_variable_preserves_the_native_failure(self):
        library, _ = self.library(SimpleNamespace())
        cause = ValueError("Fixture global is missing")
        ctype = Mock()
        ctype.in_dll.side_effect = cause
        with self.assertRaises(NativeSymbolError) as result:
            library.variable("MissingGlobal", ctype)
        self.assertIs(result.exception.__cause__, cause)


class OwnershipTests(unittest.TestCase):
    def test_context_releases_once_even_when_body_fails(self):
        release = Mock()
        reference = OwnedReference(123, release)
        with self.assertRaisesRegex(RuntimeError, "Fixture failure"):
            with reference as owned:
                self.assertEqual(owned.pointer.value, 123)
                raise RuntimeError("Fixture failure")
        reference.close()
        self.assertTrue(reference.closed)
        self.assertEqual(release.call_count, 1)
        self.assertEqual(release.call_args.args[0].value, 123)

    def test_closed_reference_cannot_be_borrowed_or_reentered(self):
        reference = OwnedReference(ctypes.c_void_p(123), Mock())
        reference.close()
        with self.assertRaises(ReferenceError):
            reference.pointer
        with self.assertRaises(ReferenceError):
            reference.__enter__()

    def test_null_and_invalid_addresses_are_rejected_before_release(self):
        release = Mock()
        for address in (None, 0, -1, ctypes.c_void_p(), 1 << (ctypes.sizeof(ctypes.c_void_p) * 8)):
            with self.subTest(address=address):
                with self.assertRaises(ValueError):
                    OwnedReference(address, release)
        for address in (True, "123", 123.0):
            with self.subTest(address=address):
                with self.assertRaises(TypeError):
                    OwnedReference(address, release)
        with self.assertRaises(TypeError):
            OwnedReference(123, None)
        release.assert_not_called()

    def test_release_failure_does_not_allow_a_second_release(self):
        release = Mock(side_effect=RuntimeError("Fixture cleanup failure"))
        reference = OwnedReference(123, release)
        with self.assertRaises(RuntimeError):
            reference.close()
        reference.close()
        self.assertTrue(reference.closed)
        release.assert_called_once()

    def test_release_can_reenter_close_without_deadlocking(self):
        release = Mock(side_effect=lambda pointer: reference.close())
        reference = OwnedReference(123, release)
        reference.close()
        release.assert_called_once()

    def test_concurrent_close_releases_once(self):
        release = Mock()
        reference = OwnedReference(123, release)
        barrier = Barrier(8)

        def close():
            barrier.wait(timeout=10)
            reference.close()

        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(close) for _ in range(8)]
            for future in futures:
                future.result(timeout=15)
        release.assert_called_once()
        self.assertTrue(reference.closed)


if __name__ == "__main__":
    unittest.main()
