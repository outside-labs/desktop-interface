"""Bounded, type-checked decoding of borrowed CoreFoundation metadata."""

import ctypes as c

from . import macos as native
from ..errors import NativeCallError


_MAX_TEXT_UNITS = 32768
_MAX_TEXT_BYTES = 65536


class CFReader:
    def __init__(self) -> None:
        self.library = native.core_foundation()

    def expect(self, pointer, type_spec, operation: str) -> None:
        if not pointer:
            raise NativeCallError(operation)
        actual = self.library.bind(native.CF_TYPE_ID)(pointer)
        expected = self.library.bind(type_spec)()
        if actual != expected:
            raise NativeCallError(operation)

    def array(self, pointer, *, limit: int) -> tuple[int, ...]:
        self.expect(pointer, native.CF_ARRAY_TYPE, "CFArray metadata type")
        count = self.library.bind(native.CF_ARRAY_COUNT)(pointer)
        if count < 0 or count > limit:
            raise NativeCallError("CFArray metadata entry limit")
        get = self.library.bind(native.CF_ARRAY_VALUE)
        values = tuple(get(pointer, index) for index in range(count))
        if not all(values):
            raise NativeCallError("CFArray metadata element")
        return values

    def value(self, dictionary, key):
        return self.library.bind(native.CF_DICTIONARY_VALUE)(dictionary, key)

    def number(self, pointer, *, floating: bool = False) -> int | float | None:
        if not pointer:
            return None
        self.expect(pointer, native.CF_NUMBER_TYPE, "CFNumber metadata type")
        value = c.c_double() if floating else c.c_int64()
        number_type = 6 if floating else 4  # kCFNumberFloat64Type / kCFNumberSInt64Type
        if not self.library.bind(native.CF_NUMBER_VALUE)(pointer, number_type, c.byref(value)):
            raise NativeCallError("CFNumberGetValue")
        return value.value

    def boolean(self, pointer) -> bool | None:
        if not pointer:
            return None
        self.expect(pointer, native.CF_BOOLEAN_TYPE, "CFBoolean metadata type")
        return bool(self.library.bind(native.CF_BOOLEAN_VALUE)(pointer))

    def text(self, pointer) -> str | None:
        if not pointer:
            return None
        self.expect(pointer, native.CF_STRING_TYPE, "CFString metadata type")
        length = self.library.bind(native.CF_STRING_LENGTH)(pointer)
        if length < 0 or length > _MAX_TEXT_UNITS:
            raise NativeCallError("CFString metadata length limit")
        if not length:
            return ""
        get = self.library.bind(native.CF_STRING_BYTES)
        used = native.CFIndex()
        span = native.CFRange(0, length)
        converted = get(pointer, span, native.UTF8, 0, False, None, 0, c.byref(used))
        if converted != length or not 0 <= used.value <= _MAX_TEXT_BYTES:
            raise NativeCallError("CFStringGetBytes size")
        capacity = used.value
        buffer = (c.c_uint8 * max(capacity, 1))()
        converted = get(pointer, span, native.UTF8, 0, False, buffer, capacity, c.byref(used))
        if converted != length or not 0 <= used.value <= capacity:
            raise NativeCallError("CFStringGetBytes conversion")
        try:
            return bytes(buffer[:used.value]).decode("utf-8")
        except UnicodeDecodeError:
            raise NativeCallError("CFStringGetBytes UTF-8 decoding") from None
