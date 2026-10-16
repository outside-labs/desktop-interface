"""Immutable geometry in logical desktop coordinates."""

from dataclasses import dataclass
import math
from numbers import Real


def _finite(value: Real, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be a real number")
    try:
        number = float(value)
    except OverflowError as error:
        raise ValueError(f"{name} must be finite") from error
    if not math.isfinite(number):
        raise ValueError(f"{name} must be finite")
    return number


def _extent(value: Real, name: str) -> float:
    number = _finite(value, name)
    if number < 0:
        raise ValueError(f"{name} must not be negative")
    return number


@dataclass(frozen=True, slots=True)
class Point:
    """A position in logical desktop coordinates; negative origins are valid."""

    x: float
    y: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "x", _finite(self.x, "x"))
        object.__setattr__(self, "y", _finite(self.y, "y"))


@dataclass(frozen=True, slots=True)
class Size:
    """Nonnegative logical extents, separate from physical pixel dimensions."""

    width: float
    height: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "width", _extent(self.width, "width"))
        object.__setattr__(self, "height", _extent(self.height, "height"))


@dataclass(frozen=True, slots=True)
class Rect:
    """A logical rectangle with inclusive left/top and exclusive right/bottom."""

    x: float
    y: float
    width: float
    height: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "x", _finite(self.x, "x"))
        object.__setattr__(self, "y", _finite(self.y, "y"))
        object.__setattr__(self, "width", _extent(self.width, "width"))
        object.__setattr__(self, "height", _extent(self.height, "height"))
        if not math.isfinite(self.right) or not math.isfinite(self.bottom):
            raise ValueError("Rectangle boundaries must be finite")

    @property
    def origin(self) -> Point:
        return Point(self.x, self.y)

    @property
    def size(self) -> Size:
        return Size(self.width, self.height)

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height

    def contains(self, point: Point) -> bool:
        if not isinstance(point, Point):
            raise TypeError("point must be a Point")
        return self.x <= point.x < self.right and self.y <= point.y < self.bottom

    def intersection(self, other: "Rect") -> "Rect | None":
        """Return the shared area, or None for disjoint or touching bounds."""
        if not isinstance(other, Rect):
            raise TypeError("other must be a Rect")
        left, top = max(self.x, other.x), max(self.y, other.y)
        right, bottom = min(self.right, other.right), min(self.bottom, other.bottom)
        if right <= left or bottom <= top:
            return None
        return Rect(left, top, right - left, bottom - top)
