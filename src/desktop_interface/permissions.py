"""Explicit permission operations, separate from feature implementation."""

from dataclasses import dataclass
from enum import StrEnum
from threading import current_thread, main_thread
from typing import TYPE_CHECKING

from .capabilities import PermissionState, Support
from .identifiers import Backend

if TYPE_CHECKING:
    from .desktop import Desktop


class Permission(StrEnum):
    ACCESSIBILITY = "accessibility"
    INPUT_MONITORING = "input_monitoring"
    POST_EVENTS = "post_events"
    SCREEN_CAPTURE = "screen_capture"


@dataclass(frozen=True, slots=True)
class PermissionStatus:
    """A current grant report; request_sent does not imply a visible prompt.

    A false macOS preflight cannot distinguish denial from an unrequested grant.
    restart_required remains None when the OS cannot determine that condition.
    """

    backend: Backend
    permission: Permission
    state: PermissionState
    support: Support = Support.SUPPORTED
    request_sent: bool = False
    restart_required: bool | None = None
    detail: str | None = None

    def __post_init__(self) -> None:
        for name, expected in (("backend", Backend), ("permission", Permission),
                               ("state", PermissionState), ("support", Support)):
            if not isinstance(getattr(self, name), expected):
                raise TypeError(f"{name} must be a {expected.__name__}")
        if not isinstance(self.request_sent, bool):
            raise TypeError("request_sent must be a bool")
        if self.restart_required is not None and not isinstance(self.restart_required, bool):
            raise TypeError("restart_required must be a bool or None")
        if self.detail is not None and not isinstance(self.detail, str):
            raise TypeError("detail must be a string or None")

    @property
    def granted(self) -> bool:
        return self.support is Support.SUPPORTED and self.state is PermissionState.GRANTED


class Permissions:
    """Permission checks never request access; request() is explicit."""

    def __init__(self, desktop: "Desktop") -> None:
        self._desktop = desktop

    @staticmethod
    def _validate(permission: Permission) -> None:
        if not isinstance(permission, Permission):
            raise TypeError("permission must be a Permission")

    def check(self, permission: Permission) -> PermissionStatus:
        self._validate(permission)
        with self._desktop._operation() as backend:
            return backend.check_permission(permission)

    def check_all(self) -> tuple[PermissionStatus, ...]:
        with self._desktop._operation() as backend:
            return tuple(backend.check_permission(permission) for permission in Permission)

    def request(self, permission: Permission) -> PermissionStatus:
        """Submit a system request on the main thread, without waiting for consent."""
        self._validate(permission)
        with self._desktop._operation() as backend:
            if current_thread() is not main_thread():
                raise RuntimeError("Permission requests must run on the main thread")
            return backend.request_permission(permission)
