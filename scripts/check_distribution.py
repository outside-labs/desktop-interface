"""Build and verify isolated wheel and source installations using stdlib tools."""

import argparse
from email.message import Message
from email.parser import BytesParser
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import venv
import zipfile


ROOT = Path(__file__).resolve().parents[1]


def run(*args: str, cwd: Path) -> None:
    subprocess.run(args, cwd=cwd, check=True, timeout=180)


def check_metadata(content: bytes, version: str) -> None:
    metadata: Message = BytesParser().parsebytes(content)
    assert metadata["Name"] == "desktop-interface", "Unexpected distribution name"
    assert metadata["Version"] == version, "Distribution version differs from project"
    assert metadata["Requires-Python"] == ">=3.12", "Unexpected Python requirement"
    assert not metadata.get_all("Requires-Dist"), "Unexpected runtime dependency"
    assert metadata["License-Expression"] == "MIT", "Expected MIT license metadata"
    assert metadata.get_all("License-File") == ["LICENSE"], "Expected packaged license"


def package_files(wheel: Path, version: str) -> dict[str, bytes]:
    with zipfile.ZipFile(wheel) as archive:
        metadata_names = [
            name for name in archive.namelist() if name.endswith(".dist-info/METADATA")
        ]
        assert len(metadata_names) == 1, "Expected one package metadata file"
        check_metadata(archive.read(metadata_names[0]), version)
        license_name = metadata_names[0].removesuffix("METADATA") + "licenses/LICENSE"
        assert archive.read(license_name) == (ROOT / "LICENSE").read_bytes(), "License differs"
        files = {
            name: archive.read(name)
            for name in archive.namelist()
            if name.startswith("desktop_interface/") and not name.endswith("/")
        }
        assert "desktop_interface/__init__.py" in files
        assert "desktop_interface/py.typed" in files
        for name in archive.namelist():
            assert name.startswith(("desktop_interface/", "desktop_interface-")), name
        return files


def check_installation(wheel: Path, environment: Path, cache: Path, cwd: Path) -> None:
    venv.EnvBuilder(with_pip=False).create(environment)
    interpreter = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    run(
        "uv", "pip", "install", "--python", str(interpreter), "--no-deps",
        "--offline", "--cache-dir", str(cache), str(wheel), cwd=cwd,
    )
    run(
        str(interpreter), "-I", "-c",
        "import ctypes, importlib, importlib.metadata, importlib.resources, pkgutil; "
        "ctypes.CDLL = lambda *a, **k: (_ for _ in ()).throw(AssertionError('native load')); "
        "import desktop_interface as package; "
        "assert importlib.metadata.version('desktop-interface') == package.__version__; "
        "assert not importlib.metadata.requires('desktop-interface'); "
        "assert importlib.resources.files(package).joinpath('py.typed').is_file(); "
        "[importlib.import_module(m.name) for m in "
        "pkgutil.walk_packages(package.__path__, package.__name__ + '.')]; "
        "print('Installed package verified')",
        cwd=cwd,
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", help="Require the release tag to match the project version")
    parser.add_argument(
        "--output-dir", type=Path,
        help="Copy verified artifacts to a new or empty directory after all checks pass",
    )
    args = parser.parse_args(argv)
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    version = project["project"]["version"]
    if args.tag is not None and args.tag != f"v{version}":
        parser.error(f"release tag must be v{version}, got {args.tag!r}")
    if args.output_dir is not None and args.output_dir.exists():
        if not args.output_dir.is_dir() or any(args.output_dir.iterdir()):
            parser.error("output directory must be new or empty")

    with tempfile.TemporaryDirectory(prefix="desktop-interface-distribution-") as temporary:
        work = Path(temporary)
        cache = work / "cache"
        artifacts = work / "artifacts"
        run("uv", "build", "--out-dir", str(artifacts), "--cache-dir", str(cache), cwd=ROOT)
        wheels = list(artifacts.glob("*.whl"))
        sources = list(artifacts.glob("*.tar.gz"))
        assert len(wheels) == len(sources) == 1
        original_files = package_files(wheels[0], version)
        extracted = work / "source"
        with tarfile.open(sources[0]) as archive:
            prefix = f"desktop_interface-{version}/"
            metadata_file = archive.extractfile(prefix + "PKG-INFO")
            license_file = archive.extractfile(prefix + "LICENSE")
            assert metadata_file is not None and license_file is not None
            with metadata_file, license_file:
                check_metadata(metadata_file.read(), version)
                assert license_file.read() == (ROOT / "LICENSE").read_bytes(), "License differs"
            for member in archive.getmembers():
                path = Path(member.name)
                assert not path.is_absolute() and ".." not in path.parts
                assert not any(part in {".git", ".venv", ".env", "__pycache__"} for part in path.parts)
                assert not member.issym() and not member.islnk()
            archive.extractall(extracted, filter="data")
        source_roots = list(extracted.iterdir())
        assert len(source_roots) == 1
        rebuilt = work / "rebuilt"
        run(
            "uv", "build", "--wheel", "--out-dir", str(rebuilt), "--cache-dir", str(cache),
            cwd=source_roots[0],
        )
        rebuilt_wheels = list(rebuilt.glob("*.whl"))
        assert len(rebuilt_wheels) == 1
        assert package_files(rebuilt_wheels[0], version) == original_files, "Source build differs from wheel"
        check_installation(wheels[0], work / "wheel-env", cache, work)
        check_installation(rebuilt_wheels[0], work / "source-env", cache, work)
        if args.output_dir is not None:
            args.output_dir.mkdir(parents=True, exist_ok=True)
            for artifact in (wheels[0], sources[0]):
                shutil.copy2(artifact, args.output_dir / artifact.name)
    print("Wheel and source distribution checks passed")


if __name__ == "__main__":
    main()
