"""Native identifiers qualified by the backend that issued them."""

from dataclasses import dataclass
from enum import StrEnum


class Backend(StrEnum):
    MACOS = "macos"
    WINDOWS = "windows"
    X11 = "x11"
    WAYLAND = "wayland"


def _validate(backend: Backend, value: int) -> None:
    if not isinstance(backend, Backend):
        raise TypeError("backend must be a Backend")
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("identifier value must be an integer")
    if value <= 0:
        raise ValueError("identifier value must be positive")


@dataclass(frozen=True, slots=True)
class DisplayId:
    """An opaque display ID, not a durable identity across topology changes."""

    backend: Backend
    value: int

    def __post_init__(self) -> None:
        _validate(self.backend, self.value)


@dataclass(frozen=True, slots=True)
class WindowId:
    """An opaque window ID; backends must still check for stale targets."""

    backend: Backend
    value: int

    def __post_init__(self) -> None:
        _validate(self.backend, self.value)
