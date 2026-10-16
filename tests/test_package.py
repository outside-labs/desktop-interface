"""Verify that package imports are safe on every supported Python platform."""

import subprocess
import sys
import textwrap
import unittest


class PackageTests(unittest.TestCase):
    def test_all_module_imports_leave_native_loaders_unused(self):
        code = textwrap.dedent(
            """
            import ctypes
            import ctypes.util
            import importlib
            import pkgutil

            def blocked(*args, **kwargs):
                raise AssertionError("Import attempted to load a native library")

            for name in ("CDLL", "PyDLL", "WinDLL", "OleDLL"):
                if hasattr(ctypes, name):
                    setattr(ctypes, name, blocked)
            ctypes.util.find_library = blocked

            import desktop_interface
            assert desktop_interface.__version__ == "0.1.0"
            for module in pkgutil.walk_packages(
                desktop_interface.__path__, desktop_interface.__name__ + "."
            ):
                importlib.import_module(module.name)
            """
        )
        result = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True, timeout=15
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
