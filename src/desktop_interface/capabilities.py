"""Separate backend support from permission state without probing the OS."""

from dataclasses import dataclass
from enum import StrEnum

from .identifiers import Backend


class Feature(StrEnum):
    DISPLAY_INFO = "display_info"
    WINDOW_INFO = "window_info"
    WINDOW_CONTROL = "window_control"
    KEYBOARD_INPUT = "keyboard_input"
    MOUSE_INPUT = "mouse_input"
    INPUT_EVENTS = "input_events"
    ACCESSIBILITY = "accessibility"
    SCREEN_CAPTURE = "screen_capture"


class Support(StrEnum):
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    UNKNOWN = "unknown"


class PermissionState(StrEnum):
    GRANTED = "granted"
    DENIED = "denied"
    NOT_REQUESTED = "not_requested"
    NOT_REQUIRED = "not_required"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class Capability:
    """An immutable report, not a guarantee of later action delivery.

    `usable` is conservative: support must be known and permission must be
    granted or unnecessary. This record never loads libraries or requests access.
    """

    backend: Backend
    feature: Feature
    support: Support
    permission: PermissionState = PermissionState.UNKNOWN
    detail: str | None = None

    def __post_init__(self) -> None:
        for name, expected in (
            ("backend", Backend), ("feature", Feature),
            ("support", Support), ("permission", PermissionState),
        ):
            if not isinstance(getattr(self, name), expected):
                raise TypeError(f"{name} must be a {expected.__name__}")
        if self.detail is not None and not isinstance(self.detail, str):
            raise TypeError("detail must be a string or None")

    @property
    def usable(self) -> bool:
        return self.support is Support.SUPPORTED and self.permission in (
            PermissionState.GRANTED, PermissionState.NOT_REQUIRED,
        )
