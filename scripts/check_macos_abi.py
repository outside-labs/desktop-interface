"""Check macOS SDK layouts and synthetic CoreFoundation ownership, without UI access."""

import ctypes as c
from contextlib import ExitStack
from pathlib import Path
import platform
import subprocess
import sys
import tempfile

from desktop_interface import Backend, NativeCallError, Rect, WindowId, WindowInfo
from desktop_interface._backends.macos.windows import MacOSWindows
from desktop_interface._native.binding import FunctionSpec
from desktop_interface._native import macos
from desktop_interface._native.ownership import OwnedReference


TYPES = (
    "CGFloat", "CGDirectDisplayID", "CGError", "Boolean", "boolean_t", "CFIndex", "CFTypeID",
    "CFTypeRef", "CFStringRef", "CFStringEncoding", "CGPoint", "CGSize", "CGRect", "CFRange",
    "CFNumberType", "CGWindowID", "CGWindowListOption",
)
FIELDS = {"CGPoint": ("x", "y"), "CGSize": ("width", "height"),
          "CGRect": ("origin", "size"), "CFRange": ("location", "length")}


def check_layouts() -> None:
    source = (
        "#include <CoreFoundation/CoreFoundation.h>\n"
        "#include <CoreGraphics/CoreGraphics.h>\n"
        "#include <stddef.h>\n#include <stdbool.h>\n#include <stdio.h>\nint main(void) {\n"
        'printf("bool %zu %zu\\n", sizeof(bool), _Alignof(bool));\n'
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
    declared["bool"] = (c.sizeof(c.c_bool), c.alignment(c.c_bool))
    declared.update({
        f"{name}.{field}": (getattr(getattr(macos, name), field).offset,)
        for name, fields in FIELDS.items() for field in fields
    })
    if declared != native:
        raise AssertionError(f"SDK ABI mismatch: declared={declared}, SDK={native}")
    print(f"SDK ABI verified: {len(TYPES) + 1} types and {sum(map(len, FIELDS.values()))} field offsets")


def check_synthetic_reference() -> None:
    library = macos.core_foundation()
    release = library.bind(macos.CF_RELEASE)
    retain = library.bind(macos.CF_RETAIN)
    create = library.bind(macos.CF_STRING_CREATE)
    get_length = library.bind(macos.CF_STRING_LENGTH)
    get_bytes = library.bind(macos.CF_STRING_BYTES)
    create_dictionary = library.bind(macos.CF_DICTIONARY_CREATE)
    dictionary_value = library.bind(macos.CF_DICTIONARY_VALUE)
    true_value = library.variable("kCFBooleanTrue", macos.CFTypeRef).value
    if not true_value:
        raise NativeCallError("kCFBooleanTrue")
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
        keys = (macos.CFTypeRef * 1)(owned.pointer.value)
        values = (macos.CFTypeRef * 1)(true_value)
        dictionary = create_dictionary(None, keys, values, 1, None, None)
        if not dictionary:
            raise NativeCallError("CFDictionaryCreate")
        with OwnedReference(dictionary, release) as options:
            if dictionary_value(options.pointer, owned.pointer) != true_value:
                raise AssertionError("Borrowed dictionary constants did not round-trip")
    print("Synthetic CoreFoundation Unicode, variables, dictionary and ownership verified")


def check_synthetic_windows() -> None:
    """Decode genuine CF metadata objects without querying any live windows."""
    reader = MacOSWindows()
    library, graphics = reader.cf.library, reader.cg
    release = library.bind(macos.CF_RELEASE)
    number = library.bind(FunctionSpec("CFNumberCreate", (macos.CFTypeRef, macos.CFNumberType, c.c_void_p), macos.CFTypeRef))
    string = library.bind(macos.CF_STRING_CREATE)
    dictionary = library.bind(macos.CF_DICTIONARY_CREATE)
    array = library.bind(macos.CF_ARRAY_CREATE)
    rectangle = graphics.bind(FunctionSpec("CGRectCreateDictionaryRepresentation", (macos.CGRect,), macos.CFTypeRef))
    with ExitStack() as stack:
        def own(pointer):
            if not pointer:
                raise NativeCallError("Synthetic metadata allocation")
            return stack.enter_context(OwnedReference(pointer, release)).pointer.value

        def numeric(value, *, floating=False):
            data = c.c_double(value) if floating else c.c_int64(value)
            return own(number(None, 6 if floating else 4, c.byref(data)))

        def text(value):
            data = value.encode("utf-8")
            buffer = (c.c_uint8 * len(data)).from_buffer_copy(data)
            return own(string(None, buffer, len(data), macos.UTF8, False))

        fields = {
            "kCGWindowNumber": numeric(7), "kCGWindowOwnerPID": numeric(42),
            "kCGWindowName": text("Fixture 👋\0tail"), "kCGWindowOwnerName": text("Synthetic"),
            "kCGWindowBounds": own(rectangle(macos.CGRect(macos.CGPoint(-20, 30), macos.CGSize(80, 60)))),
            "kCGWindowLayer": numeric(-1), "kCGWindowAlpha": numeric(0.5, floating=True),
            "kCGWindowIsOnscreen": library.variable("kCFBooleanTrue", macos.CFTypeRef).value,
        }
        keys = (macos.CFTypeRef * len(fields))(*(graphics.variable(name, macos.CFTypeRef).value for name in fields))
        values = (macos.CFTypeRef * len(fields))(*fields.values())
        row = own(dictionary(None, keys, values, len(fields), None, None))
        entries = (macos.CFTypeRef * 1)(row)
        rows = own(array(None, entries, 1, None))
        result = reader.parse(rows)
    expected = WindowInfo(WindowId(Backend.MACOS, 7), 42, Rect(-20, 30, 80, 60),
                          "Fixture 👋\0tail", "Synthetic", -1, True, 0.5)
    if result != (expected,):
        raise AssertionError("Synthetic window metadata did not decode correctly")
    print("Synthetic Quartz window metadata decoding and owned-buffer cleanup verified")


def main() -> None:
    if sys.platform != "darwin":
        print("macOS ABI check skipped on this platform")
        return
    print(f"macOS {platform.mac_ver()[0]} {platform.machine()}, Python {platform.python_version()}")
    check_layouts()
    check_synthetic_reference()
    check_synthetic_windows()


if __name__ == "__main__":
    main()
