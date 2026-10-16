"""Build and verify isolated wheel and source installations using stdlib tools."""

from email.parser import BytesParser
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import venv
import zipfile


ROOT = Path(__file__).resolve().parents[1]


def run(*args: str, cwd: Path) -> None:
    subprocess.run(args, cwd=cwd, check=True, timeout=180)


def package_files(wheel: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(wheel) as archive:
        metadata_names = [
            name for name in archive.namelist() if name.endswith(".dist-info/METADATA")
        ]
        assert len(metadata_names) == 1, "Expected one package metadata file"
        metadata = BytesParser().parsebytes(archive.read(metadata_names[0]))
        assert metadata["Name"] == "desktop-interface"
        assert metadata["Requires-Python"] == ">=3.12"
        assert not metadata.get_all("Requires-Dist"), "Unexpected runtime dependency"
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


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="desktop-interface-distribution-") as temporary:
        work = Path(temporary)
        cache = work / "cache"
        artifacts = work / "artifacts"
        run("uv", "build", "--out-dir", str(artifacts), "--cache-dir", str(cache), cwd=ROOT)
        wheels = list(artifacts.glob("*.whl"))
        sources = list(artifacts.glob("*.tar.gz"))
        assert len(wheels) == len(sources) == 1
        original_files = package_files(wheels[0])
        extracted = work / "source"
        with tarfile.open(sources[0]) as archive:
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
        assert package_files(rebuilt_wheels[0]) == original_files, "Source build differs from wheel"
        check_installation(wheels[0], work / "wheel-env", cache, work)
        check_installation(rebuilt_wheels[0], work / "source-env", cache, work)
    print("Wheel and source distribution checks passed")


if __name__ == "__main__":
    main()
