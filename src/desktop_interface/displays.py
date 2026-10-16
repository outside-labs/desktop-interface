"""Immutable active-display snapshots with explicit logical and pixel units."""

from dataclasses import dataclass, field
import math
import sys
from time import monotonic
from typing import TYPE_CHECKING

from .errors import AmbiguousTargetError, StaleTargetError
from .geometry import Point, Rect, _finite
from .identifiers import Backend, DisplayId

if TYPE_CHECKING:
    from .desktop import Desktop


@dataclass(frozen=True, slots=True)
class PixelPoint:
    """Continuous display-local backing-pixel coordinates, without rounding."""

    x: float
    y: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "x", _finite(self.x, "x"))
        object.__setattr__(self, "y", _finite(self.y, "y"))


@dataclass(frozen=True, slots=True)
class PixelSize:
    """Integer backing-pixel dimensions, distinct from logical Size."""

    width: int
    height: int

    def __post_init__(self) -> None:
        for name in ("width", "height"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer pixel count")
            if value < 0 or value > sys.maxsize:
                raise ValueError(f"{name} must be a nonnegative process-sized pixel count")


@dataclass(frozen=True, slots=True)
class PixelLocation:
    """A pixel point qualified by the display and snapshot used to convert it."""

    display_id: DisplayId
    point: PixelPoint
    topology: "DisplayTopology" = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.display_id, DisplayId) or not isinstance(self.point, PixelPoint):
            raise TypeError("A pixel location requires a DisplayId and PixelPoint")
        if not isinstance(self.topology, DisplayTopology):
            raise TypeError("topology must be the DisplayTopology used for conversion")
        self.topology.get(self.display_id)


@dataclass(frozen=True, slots=True)
class Display:
    """One active drawable display, normalized to desktop orientation.

    bounds uses global logical coordinates; pixel_size uses backing pixels in
    that same orientation. Rotation is metadata and is not applied twice during
    conversion. These dimensions describe the current mode, not panel hardware.
    """

    id: DisplayId
    bounds: Rect
    pixel_size: PixelSize
    rotation: float = 0.0
    is_main: bool = False
    mirror_of: DisplayId | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.id, DisplayId) or not isinstance(self.bounds, Rect):
            raise TypeError("Display requires a DisplayId and logical Rect")
        if not isinstance(self.pixel_size, PixelSize):
            raise TypeError("pixel_size must be a PixelSize")
        if not isinstance(self.is_main, bool):
            raise TypeError("is_main must be a bool")
        if self.bounds.width <= 0 or self.bounds.height <= 0 or self.pixel_size.width <= 0 or self.pixel_size.height <= 0:
            raise ValueError("An active display must have positive logical and pixel dimensions")
        object.__setattr__(self, "rotation", _finite(self.rotation, "rotation") % 360)
        if not all(math.isfinite(scale) and scale > 0 for scale in (self.scale_x, self.scale_y)):
            raise ValueError("Display scales must be finite and positive")
        if self.mirror_of is not None:
            if not isinstance(self.mirror_of, DisplayId):
                raise TypeError("mirror_of must be a DisplayId or None")
            if self.mirror_of.backend is not self.id.backend or self.mirror_of == self.id:
                raise ValueError("A mirror must reference a different display on the same backend")

    @property
    def scale_x(self) -> float:
        return self.pixel_size.width / self.bounds.width

    @property
    def scale_y(self) -> float:
        return self.pixel_size.height / self.bounds.height

    def logical_to_pixel(self, point: Point) -> PixelPoint:
        if not self.bounds.contains(point):
            raise ValueError("Logical point is outside this display")
        return PixelPoint((point.x - self.bounds.x) * self.scale_x,
                          (point.y - self.bounds.y) * self.scale_y)

    def pixel_to_logical(self, point: PixelPoint) -> Point:
        if not isinstance(point, PixelPoint):
            raise TypeError("point must be a PixelPoint")
        if not (0 <= point.x < self.pixel_size.width and 0 <= point.y < self.pixel_size.height):
            raise ValueError("Pixel point is outside this display")
        return Point(self.bounds.x + point.x / self.scale_x,
                     self.bounds.y + point.y / self.scale_y)


@dataclass(frozen=True, slots=True)
class DisplayTopology:
    """A stable observed layout; it is not a live or atomic OS transaction."""

    backend: Backend
    displays: tuple[Display, ...]
    captured_at: float = field(default_factory=monotonic)

    def __post_init__(self) -> None:
        if not isinstance(self.backend, Backend):
            raise TypeError("backend must be a Backend")
        if not isinstance(self.displays, tuple) or not all(isinstance(item, Display) for item in self.displays):
            raise TypeError("displays must be an immutable tuple of Display records")
        if any(item.id.backend is not self.backend for item in self.displays):
            raise ValueError("All displays must belong to the topology's backend")
        if len({item.id for item in self.displays}) != len(self.displays):
            raise ValueError("Display IDs must be unique within a topology")
        if sum(item.is_main for item in self.displays) > 1:
            raise ValueError("A topology cannot have more than one main display")
        object.__setattr__(self, "captured_at", _finite(self.captured_at, "captured_at"))
        if self.captured_at < 0:
            raise ValueError("captured_at must be a nonnegative monotonic timestamp")

    @property
    def main(self) -> Display | None:
        return next((item for item in self.displays if item.is_main), None)

    def get(self, display_id: DisplayId) -> Display:
        if not isinstance(display_id, DisplayId):
            raise TypeError("display_id must be a DisplayId")
        if display_id.backend is not self.backend:
            raise ValueError("Display ID belongs to a different backend")
        for item in self.displays:
            if item.id == display_id:
                return item
        raise StaleTargetError("Display is not present in this topology snapshot")

    def logical_to_pixel(self, point: Point, *, display_id: DisplayId | None = None) -> PixelLocation:
        if not isinstance(point, Point):
            raise TypeError("point must be a logical Point")
        if display_id is not None:
            display = self.get(display_id)
        else:
            matches = [item for item in self.displays if item.bounds.contains(point)]
            if len(matches) > 1:
                raise AmbiguousTargetError("Overlapping displays require an explicit display_id")
            if not matches:
                raise ValueError("Logical point is outside this topology")
            display = matches[0]
        return PixelLocation(display.id, display.logical_to_pixel(point), self)

    def pixel_to_logical(self, location: PixelLocation) -> Point:
        if not isinstance(location, PixelLocation):
            raise TypeError("location must be a PixelLocation")
        if location.topology is not self:
            raise StaleTargetError("Pixel location belongs to a different topology snapshot")
        return self.get(location.display_id).pixel_to_logical(location.point)


class Displays:
    def __init__(self, desktop: "Desktop") -> None:
        self._desktop = desktop

    def snapshot(self) -> DisplayTopology:
        with self._desktop._operation() as backend:
            return backend.display_snapshot()

    def list(self) -> tuple[Display, ...]:
        """List active drawable displays, excluding sleeping/online-only outputs."""
        return self.snapshot().displays

    def get(self, display_id: DisplayId) -> Display:
        if not isinstance(display_id, DisplayId):
            raise TypeError("display_id must be a DisplayId")
        if display_id.backend is not self._desktop.backend:
            raise ValueError("Display ID belongs to a different backend")
        return self.snapshot().get(display_id)
