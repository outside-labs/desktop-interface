"""Bounded active-display discovery through Quartz Display Services."""

import ctypes as c
import math

from ..._native import macos as native
from ..._native.ownership import OwnedReference
from ...displays import Display, DisplayTopology, PixelSize
from ...errors import DisplayTopologyChangedError, NativeCallError
from ...geometry import Rect
from ...identifiers import Backend, DisplayId


_MAX_DISPLAYS = 256
_ATTEMPTS = 3


class _Changed(Exception):
    pass


class MacOSDisplays:
    def __init__(self) -> None:
        self.cg = native.core_graphics()

    def _ids(self) -> tuple[int, ...]:
        enumerate_displays = self.cg.bind(native.CG_ACTIVE_DISPLAYS)
        count = c.c_uint32()
        code = enumerate_displays(0, None, c.byref(count))
        if code:
            raise NativeCallError("CGGetActiveDisplayList", code=code)
        if count.value > _MAX_DISPLAYS:
            raise NativeCallError("CGGetActiveDisplayList count limit")
        capacity = max(count.value, 1)
        identifiers = (native.CGDirectDisplayID * capacity)()
        written = c.c_uint32()
        code = enumerate_displays(capacity, identifiers, c.byref(written))
        if code:
            raise NativeCallError("CGGetActiveDisplayList", code=code)
        if written.value > capacity:
            raise _Changed
        code = enumerate_displays(0, None, c.byref(count))
        if code:
            raise NativeCallError("CGGetActiveDisplayList", code=code)
        if count.value != written.value:
            raise _Changed
        result = tuple(sorted(identifiers[:written.value]))
        if not all(result) or len(set(result)) != len(result):
            raise NativeCallError("CGGetActiveDisplayList identifiers")
        return result

    @staticmethod
    def _pixels(bounds: Rect, mode_width: int, mode_height: int,
                pixel_width: int, pixel_height: int, rotation: float) -> PixelSize:
        same = lambda a, b: math.isclose(a, b, rel_tol=0, abs_tol=1e-6)
        if same(bounds.width, mode_width) and same(bounds.height, mode_height):
            return PixelSize(pixel_width, pixel_height)
        if (same(rotation % 180, 90) and same(bounds.width, mode_height)
                and same(bounds.height, mode_width)):
            return PixelSize(pixel_height, pixel_width)
        raise _Changed

    def _read(self, identifier: int) -> Display:
        specs = (
            native.CG_DISPLAY_ACTIVE, native.CG_DISPLAY_ONLINE, native.CG_DISPLAY_BOUNDS,
            native.CG_DISPLAY_MAIN, native.CG_DISPLAY_ROTATION, native.CG_DISPLAY_MIRROR,
            native.CG_DISPLAY_MODE, native.CG_MODE_RELEASE, native.CG_MODE_WIDTH,
            native.CG_MODE_HEIGHT, native.CG_MODE_PIXEL_WIDTH, native.CG_MODE_PIXEL_HEIGHT,
        )
        functions = {spec.name: self.cg.bind(spec) for spec in specs}
        if not functions["CGDisplayIsActive"](identifier) or not functions["CGDisplayIsOnline"](identifier):
            raise _Changed
        rectangle = functions["CGDisplayBounds"](identifier)
        mode = functions["CGDisplayCopyDisplayMode"](identifier)
        if not mode:
            raise _Changed
        with OwnedReference(mode, functions["CGDisplayModeRelease"]) as owned:
            try:
                bounds = Rect(rectangle.origin.x, rectangle.origin.y, rectangle.size.width, rectangle.size.height)
                rotation = functions["CGDisplayRotation"](identifier)
                pixels = self._pixels(
                    bounds, functions["CGDisplayModeGetWidth"](owned.pointer),
                    functions["CGDisplayModeGetHeight"](owned.pointer),
                    functions["CGDisplayModeGetPixelWidth"](owned.pointer),
                    functions["CGDisplayModeGetPixelHeight"](owned.pointer), rotation,
                )
                mirrored = functions["CGDisplayMirrorsDisplay"](identifier)
                return Display(
                    DisplayId(Backend.MACOS, identifier), bounds, pixels, rotation,
                    bool(functions["CGDisplayIsMain"](identifier)),
                    DisplayId(Backend.MACOS, mirrored) if mirrored else None,
                )
            except ValueError as error:
                raise _Changed from error

    def snapshot(self) -> DisplayTopology:
        for _ in range(_ATTEMPTS):
            try:
                before = self._ids()
                first = tuple(self._read(identifier) for identifier in before)
                after = self._ids()
                if before != after:
                    continue
                second = tuple(self._read(identifier) for identifier in after)
                if first != second:
                    continue
                try:
                    return DisplayTopology(Backend.MACOS, second)
                except ValueError:
                    continue
            except _Changed:
                continue
        raise DisplayTopologyChangedError("Display topology did not stabilize after three attempts")
