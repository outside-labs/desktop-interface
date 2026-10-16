"""Explicit macOS session operations and feature support."""

from ...capabilities import Capability, Feature, PermissionState, Support
from ...displays import DisplayTopology
from ...identifiers import Backend, WindowId
from ...permissions import Permission, PermissionStatus
from ...windows import WindowInfo
from .displays import MacOSDisplays
from .permissions import MacOSPermissions
from .windows import MacOSWindows


class MacOSBackend:
    def __init__(self) -> None:
        self._permissions = MacOSPermissions()
        self._displays = MacOSDisplays()
        self._windows = MacOSWindows()

    def capabilities(self) -> tuple[Capability, ...]:
        descriptions = {
            Feature.DISPLAY_INFO: "Active drawable display metadata.",
            Feature.WINDOW_INFO: "Read-only window metadata; individual fields may be redacted.",
        }
        return tuple(
            Capability(Backend.MACOS, feature,
                       Support.SUPPORTED if feature in descriptions else Support.UNSUPPORTED,
                       PermissionState.NOT_REQUIRED if feature in descriptions else PermissionState.UNKNOWN,
                       descriptions.get(feature, "This desktop feature is not implemented yet."))
            for feature in Feature
        )

    def check_permission(self, permission: Permission) -> PermissionStatus:
        return self._permissions.check(permission)

    def request_permission(self, permission: Permission) -> PermissionStatus:
        return self._permissions.request(permission)

    def display_snapshot(self) -> DisplayTopology:
        return self._displays.snapshot()

    def window_list(self, *, process_id: int | None, onscreen_only: bool) -> tuple[WindowInfo, ...]:
        return self._windows.list(process_id=process_id, onscreen_only=onscreen_only)

    def window_info(self, window_id: WindowId, *, expected_process_id: int | None = None) -> WindowInfo:
        return self._windows.get(window_id, expected_process_id=expected_process_id)
