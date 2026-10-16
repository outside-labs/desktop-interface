"""Bounded Quartz window metadata, copied before native arrays are released."""

import ctypes as c

from ..._native import macos as native
from ..._native.collections import CFReader
from ..._native.ownership import OwnedReference
from ...errors import NativeCallError, TargetNotFoundError
from ...geometry import Rect
from ...identifiers import Backend, WindowId
from ...windows import WindowInfo


_MAX_WINDOWS = 4096


class MacOSWindows:
    def __init__(self) -> None:
        self.cg = native.core_graphics()
        self.cf = CFReader()
        self._keys = {}

    def _value(self, row, name: str):
        if name not in self._keys:
            key = self.cg.variable(name, native.CFTypeRef).value
            if not key:
                raise NativeCallError("Quartz window metadata key")
            self._keys[name] = key
        return self.cf.value(row, self._keys[name])

    def parse(self, pointer, *, process_id: int | None = None,
              window_id: WindowId | None = None) -> tuple[WindowInfo, ...]:
        results, seen = [], set()
        for row in self.cf.array(pointer, limit=_MAX_WINDOWS):
            self.cf.expect(row, native.CF_DICTIONARY_TYPE, "Window metadata dictionary type")
            identifier = self.cf.number(self._value(row, "kCGWindowNumber"))
            if identifier is None or not -(1 << 31) <= identifier <= 0xFFFFFFFF:
                raise NativeCallError("Quartz window identifier")
            identifier &= 0xFFFFFFFF
            if not identifier or identifier in seen:
                raise NativeCallError("Quartz window identifier")
            seen.add(identifier)
            owner = self.cf.number(self._value(row, "kCGWindowOwnerPID"))
            if owner is not None and not 0 <= owner <= 0x7FFFFFFF:
                raise NativeCallError("Quartz window process identity")
            if (window_id is not None and identifier != window_id.value) or (process_id is not None and owner != process_id):
                continue
            rectangle = self._value(row, "kCGWindowBounds")
            bounds = None
            if rectangle:
                self.cf.expect(rectangle, native.CF_DICTIONARY_TYPE, "Window bounds dictionary type")
                result = native.CGRect()
                if not self.cg.bind(native.CG_RECT_FROM_DICTIONARY)(rectangle, c.byref(result)):
                    raise NativeCallError("CGRectMakeWithDictionaryRepresentation")
                try:
                    bounds = Rect(result.origin.x, result.origin.y, result.size.width, result.size.height)
                except ValueError as error:
                    raise NativeCallError("Quartz window bounds") from error
            try:
                results.append(WindowInfo(
                    WindowId(Backend.MACOS, identifier), owner, bounds,
                    self.cf.text(self._value(row, "kCGWindowName")),
                    self.cf.text(self._value(row, "kCGWindowOwnerName")),
                    self.cf.number(self._value(row, "kCGWindowLayer")),
                    self.cf.boolean(self._value(row, "kCGWindowIsOnscreen")) or False,
                    self.cf.number(self._value(row, "kCGWindowAlpha"), floating=True),
                ))
            except ValueError as error:
                raise NativeCallError("Quartz window metadata") from error
        return tuple(results)

    def _query(self, *, process_id: int | None, onscreen_only: bool,
               window_id: WindowId | None = None) -> tuple[WindowInfo, ...]:
        release = self.cf.library.bind(native.CF_RELEASE)
        if window_id is None:
            copy = self.cg.bind(native.CG_WINDOW_LIST)
            pointer = copy(16 | (1 if onscreen_only else 0), 0)
            operation = "CGWindowListCopyWindowInfo"
        else:
            if window_id.backend is not Backend.MACOS or window_id.value > 0xFFFFFFFF:
                raise ValueError("Window ID does not fit the macOS native identifier")
            copy = self.cg.bind(native.CG_WINDOW_DESCRIPTIONS)
            create = self.cf.library.bind(native.CF_ARRAY_CREATE)
            # Quartz window-ID arrays store raw CGWindowID values, not CF objects.
            # NULL callbacks leave these integer values unretained.
            values = (native.CFTypeRef * 1)(window_id.value)
            array = create(None, values, 1, None)
            if not array:
                raise NativeCallError("CFArrayCreate window identifiers")
            with OwnedReference(array, release) as identifiers:
                pointer = copy(identifiers.pointer)
            operation = "CGWindowListCreateDescriptionFromArray"
        if not pointer:
            raise NativeCallError(operation)
        with OwnedReference(pointer, release) as owned:
            return self.parse(owned.pointer, process_id=process_id, window_id=window_id)

    def list(self, *, process_id: int | None, onscreen_only: bool) -> tuple[WindowInfo, ...]:
        return self._query(process_id=process_id, onscreen_only=onscreen_only)

    def get(self, window_id: WindowId, *, expected_process_id: int | None = None) -> WindowInfo:
        # Validate before loading a framework or allocating the input ID array.
        if not isinstance(window_id, WindowId):
            raise TypeError("window_id must be a WindowId")
        if window_id.backend is not Backend.MACOS or window_id.value > 0xFFFFFFFF:
            raise ValueError("Window ID does not fit the macOS native identifier")
        rows = self._query(process_id=expected_process_id, onscreen_only=False, window_id=window_id)
        if not rows:
            raise TargetNotFoundError("Window is not present with the expected identity")
        return rows[0]
