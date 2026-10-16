"""Explicit macOS session operations and feature support."""

from ...capabilities import Capability, Feature, PermissionState, Support
from ...displays import DisplayTopology
from ...identifiers import Backend, WindowId
from ...permissions import Permission, PermissionStatus
from ...errors import PermissionRequiredError
from ...windows import WindowInfo
from .displays import MacOSDisplays
from .permissions import MacOSPermissions
from .windows import MacOSWindows
from .window_control import MacOSWindowControl
from .events import MacOSEvents


class MacOSBackend:
    def __init__(self) -> None:
        self._permissions = MacOSPermissions()
        self._displays = MacOSDisplays()
        self._windows = MacOSWindows()
        self._window_control = MacOSWindowControl(self._windows)
        self._events = MacOSEvents()

    def capabilities(self) -> tuple[Capability, ...]:
        descriptions = {
            Feature.DISPLAY_INFO: "Active drawable display metadata.",
            Feature.WINDOW_INFO: "Read-only window metadata; individual fields may be redacted.",
            Feature.WINDOW_CONTROL: "Accessibility window control; requires a unique metadata match and access.",
            Feature.KEYBOARD_INPUT: "Physical key and Unicode event posting; submission is not delivery.",
            Feature.MOUSE_INPUT: "Logical pointer, button and scroll event posting; submission is not delivery.",
        }
        return tuple(
            Capability(Backend.MACOS, feature,
                       Support.SUPPORTED if feature in descriptions else Support.UNSUPPORTED,
                       PermissionState.NOT_REQUIRED if feature in (Feature.DISPLAY_INFO, Feature.WINDOW_INFO) else PermissionState.UNKNOWN,
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

    def window_control(self, window_id, process_id, action, value, timeout):
        if not self.check_permission(Permission.ACCESSIBILITY).granted:
            raise PermissionRequiredError("Window control requires Accessibility access")
        info = self._windows.get(window_id, expected_process_id=process_id)
        return self._window_control.run(info, action, value, timeout)

    def require_post_access(self):
        if not self.check_permission(Permission.POST_EVENTS).granted:
            raise PermissionRequiredError("Input posting requires macOS event-posting access")

    def key_state(self, key):
        return self._events.key_state(key)

    def key_event(self, key, down, owned):
        self._events.key_event(key, down, owned)

    def text_pair(self, payload, owned):
        self._events.text_pair(payload, owned)

    def pointer_position(self):
        return self._events.pointer_position()

    def button_state(self, button):
        return self._events.button_state(button)

    def pointer_move(self, point, button, owned_keys):
        self._events.pointer_move(point, button, owned_keys)

    def button_event(self, button, down, point, owned_keys, click_count):
        self._events.button_event(button, down, point, owned_keys, click_count)

    def scroll_event(self, vertical, horizontal, unit, owned_keys):
        self._events.scroll_event(vertical, horizontal, unit, owned_keys)
