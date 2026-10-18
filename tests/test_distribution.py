"""Guard release identity, license metadata and verified artifact export."""

from contextlib import redirect_stderr
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from scripts import check_distribution as distribution


class DistributionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="desktop-interface-release-test-")
        self.addCleanup(temporary.cleanup)
        self.work = Path(temporary.name)

    def wheel(self, metadata=None, license_content=None):
        fields = {
            "Metadata-Version": "2.4",
            "Name": "desktop-interface",
            "Version": "0.1.0",
            "Requires-Python": ">=3.12",
            "License-Expression": "MIT",
            "License-File": "LICENSE",
        }
        fields.update(metadata or {})
        wheel = self.work / "desktop_interface-0.1.0-py3-none-any.whl"
        prefix = "desktop_interface-0.1.0.dist-info/"
        with zipfile.ZipFile(wheel, "w") as archive:
            archive.writestr(
                prefix + "METADATA",
                "".join(f"{key}: {value}\n" for key, value in fields.items()) + "\n",
            )
            archive.writestr(
                prefix + "licenses/LICENSE",
                (distribution.ROOT / "LICENSE").read_bytes()
                if license_content is None else license_content,
            )
            archive.writestr("desktop_interface/__init__.py", '__version__ = "0.1.0"\n')
            archive.writestr("desktop_interface/py.typed", "")
        return wheel

    def test_accepts_licensed_typed_wheel(self):
        files = distribution.package_files(self.wheel(), "0.1.0")
        self.assertEqual(set(files), {"desktop_interface/__init__.py", "desktop_interface/py.typed"})

    def test_rejects_wrong_metadata_and_runtime_dependencies(self):
        for fields in (
            {"Name": "another-package"},
            {"Version": "0.2.0"},
            {"Requires-Python": ">=3.14"},
            {"License-Expression": "Apache-2.0"},
            {"License-File": "COPYING"},
            {"Requires-Dist": "unexpected-dependency"},
        ):
            with self.subTest(fields=fields), self.assertRaises(AssertionError):
                distribution.package_files(self.wheel(metadata=fields), "0.1.0")

    def test_rejects_changed_license_text(self):
        with self.assertRaisesRegex(AssertionError, "License differs"):
            distribution.package_files(self.wheel(license_content=b"different license"), "0.1.0")

    def test_rejects_missing_license_text(self):
        wheel = self.wheel()
        replacement = self.work / "missing-license.whl"
        with zipfile.ZipFile(wheel) as source, zipfile.ZipFile(replacement, "w") as target:
            for name in source.namelist():
                if not name.endswith("/licenses/LICENSE"):
                    target.writestr(name, source.read(name))
        with self.assertRaises(KeyError):
            distribution.package_files(replacement, "0.1.0")

    def test_rejects_wrong_release_tag_before_building(self):
        for tag in ("v0.2.0", "0.1.0", "main"):
            with self.subTest(tag=tag), patch.object(distribution, "run") as run:
                with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                    distribution.main(["--tag", tag])
                self.assertEqual(error.exception.code, 2)
                run.assert_not_called()

    def test_preserves_nonempty_output_directory(self):
        output = self.work / "dist"
        output.mkdir()
        sentinel = output / "existing.whl"
        sentinel.write_bytes(b"preserve")
        with patch.object(distribution, "run") as run:
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                distribution.main(["--output-dir", str(output)])
            self.assertEqual(error.exception.code, 2)
            run.assert_not_called()
        self.assertEqual(sentinel.read_bytes(), b"preserve")

    def test_does_not_export_failed_build(self):
        output = self.work / "dist"
        with patch.object(distribution, "run", side_effect=RuntimeError("build failed")):
            with self.assertRaisesRegex(RuntimeError, "build failed"):
                distribution.main(["--output-dir", str(output), "--tag", "v0.1.0"])
        self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
