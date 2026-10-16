"""Explicit macOS session operations and feature support."""

from ...capabilities import Capability, Feature, PermissionState, Support
from ...identifiers import Backend
from ...permissions import Permission, PermissionStatus
from .permissions import MacOSPermissions


class MacOSBackend:
    def __init__(self) -> None:
        self._permissions = MacOSPermissions()

    def capabilities(self) -> tuple[Capability, ...]:
        return tuple(
            Capability(Backend.MACOS, feature, Support.UNSUPPORTED,
                       PermissionState.UNKNOWN, "This desktop feature is not implemented yet.")
            for feature in Feature
        )

    def check_permission(self, permission: Permission) -> PermissionStatus:
        return self._permissions.check(permission)

    def request_permission(self, permission: Permission) -> PermissionStatus:
        return self._permissions.request(permission)
