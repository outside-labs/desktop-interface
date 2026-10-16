"""Explicit macOS session operations and feature support."""

from ...capabilities import Capability, Feature, PermissionState, Support
from ...identifiers import Backend
from ...permissions import Permission, PermissionStatus
from ...displays import DisplayTopology
from .displays import MacOSDisplays
from .permissions import MacOSPermissions


class MacOSBackend:
    def __init__(self) -> None:
        self._permissions = MacOSPermissions()
        self._displays = MacOSDisplays()

    def capabilities(self) -> tuple[Capability, ...]:
        return tuple(
            Capability(Backend.MACOS, feature,
                       Support.SUPPORTED if feature is Feature.DISPLAY_INFO else Support.UNSUPPORTED,
                       PermissionState.NOT_REQUIRED if feature is Feature.DISPLAY_INFO else PermissionState.UNKNOWN,
                       "Active drawable display metadata." if feature is Feature.DISPLAY_INFO
                       else "This desktop feature is not implemented yet.")
            for feature in Feature
        )

    def check_permission(self, permission: Permission) -> PermissionStatus:
        return self._permissions.check(permission)

    def request_permission(self, permission: Permission) -> PermissionStatus:
        return self._permissions.request(permission)

    def display_snapshot(self) -> DisplayTopology:
        return self._displays.snapshot()
