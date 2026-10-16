"""Check macOS SDK layouts and synthetic CoreFoundation ownership, without UI access."""

import ctypes as c
from pathlib import Path
import subprocess
import sys
import tempfile

from desktop_interface import NativeCallError
from desktop_interface._native import macos
from desktop_interface._native.ownership import OwnedReference


TYPES = (
    "CGFloat", "CGDirectDisplayID", "CGError", "Boolean", "CFIndex", "CFTypeID",
    "CFTypeRef", "CFStringRef", "CFStringEncoding", "CGPoint", "CGSize", "CGRect", "CFRange",
)
FIELDS = {"CGPoint": ("x", "y"), "CGSize": ("width", "height"),
          "CGRect": ("origin", "size"), "CFRange": ("location", "length")}


def check_layouts() -> None:
    source = (
        "#include <CoreFoundation/CoreFoundation.h>\n"
        "#include <CoreGraphics/CoreGraphics.h>\n"
        "#include <stddef.h>\n#include <stdio.h>\nint main(void) {\n"
        + "\n".join(
            f'printf("{name} %zu %zu\\n", sizeof({name}), _Alignof({name}));'
            for name in TYPES
        )
        + "\n"
        + "\n".join(
            f'printf("{name}.{field} %zu\\n", offsetof({name}, {field}));'
            for name, fields in FIELDS.items() for field in fields
        )
        + "\nreturn 0;\n}\n"
    )
    with tempfile.TemporaryDirectory(prefix="desktop-interface-abi-") as temporary:
        work = Path(temporary)
        (work / "probe.c").write_text(source)
        subprocess.run(
            ["xcrun", "clang", "-std=c11", "-Werror", str(work / "probe.c"),
             "-framework", "CoreFoundation", "-framework", "CoreGraphics",
             "-o", str(work / "probe")], check=True, timeout=60,
        )
        result = subprocess.run(
            [str(work / "probe")], check=True, capture_output=True, text=True, timeout=15,
        )
    native = {parts[0]: tuple(map(int, parts[1:])) for line in result.stdout.splitlines()
              if (parts := line.split())}
    declared = {
        name: (c.sizeof(getattr(macos, name)), c.alignment(getattr(macos, name)))
        for name in TYPES
    }
    declared.update({
        f"{name}.{field}": (getattr(getattr(macos, name), field).offset,)
        for name, fields in FIELDS.items() for field in fields
    })
    if declared != native:
        raise AssertionError(f"SDK ABI mismatch: declared={declared}, SDK={native}")
    print(f"SDK ABI verified: {len(TYPES)} types and {sum(map(len, FIELDS.values()))} field offsets")


def check_synthetic_reference() -> None:
    library = macos.core_foundation()
    release = library.bind(macos.CF_RELEASE)
    retain = library.bind(macos.CF_RETAIN)
    create = library.bind(macos.CF_STRING_CREATE)
    get_length = library.bind(macos.CF_STRING_LENGTH)
    get_bytes = library.bind(macos.CF_STRING_BYTES)
    expected = "Synthetic fixture: café 👋\0 tail".encode("utf-8")
    data = (c.c_uint8 * len(expected)).from_buffer_copy(expected)
    pointer = create(None, data, len(expected), macos.UTF8, False)
    if not pointer:
        raise NativeCallError("CFStringCreateWithBytes")
    with OwnedReference(pointer, release) as owned:
        length = get_length(owned.pointer)
        output = (c.c_uint8 * len(expected))()
        used = macos.CFIndex()
        converted = get_bytes(
            owned.pointer, macos.CFRange(0, length), macos.UTF8, 0, False,
            output, len(output), c.byref(used),
        )
        if converted != length or bytes(output[:used.value]) != expected:
            raise AssertionError("Synthetic Unicode bytes did not round-trip")
        retained = retain(owned.pointer)
        if not retained:
            raise NativeCallError("CFRetain")
        with OwnedReference(retained, release) as second_owner:
            if second_owner.pointer.value != owned.pointer.value:
                raise AssertionError("CFRetain returned a different object")
    print("Synthetic CoreFoundation Unicode and reference ownership verified")


def main() -> None:
    if sys.platform != "darwin":
        print("macOS ABI check skipped on this platform")
        return
    check_layouts()
    check_synthetic_reference()


if __name__ == "__main__":
    main()
