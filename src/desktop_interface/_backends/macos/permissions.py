"""Documented nonprompting macOS checks and explicit request paths."""

from ..._native import macos as native
from ..._native.ownership import OwnedReference
from ...capabilities import PermissionState, Support
from ...errors import NativeCallError, NativeLibraryError, NativeSymbolError
from ...identifiers import Backend
from ...permissions import Permission, PermissionStatus


_CHECKS = {
    Permission.INPUT_MONITORING: native.CG_PREFLIGHT_LISTEN,
    Permission.POST_EVENTS: native.CG_PREFLIGHT_POST,
    Permission.SCREEN_CAPTURE: native.CG_PREFLIGHT_CAPTURE,
}
_REQUESTS = {
    Permission.INPUT_MONITORING: native.CG_REQUEST_LISTEN,
    Permission.POST_EVENTS: native.CG_REQUEST_POST,
    Permission.SCREEN_CAPTURE: native.CG_REQUEST_CAPTURE,
}
_NO_GRANT = "The OS reports no current grant; denial and an unrequested grant are indistinguishable."


class MacOSPermissions:
    def __init__(self) -> None:
        self.cg = native.core_graphics()
        self.app = native.application_services()
        self.cf = native.core_foundation()

    def check(self, permission: Permission) -> PermissionStatus:
        try:
            if permission is Permission.ACCESSIBILITY:
                granted = bool(self.app.bind(native.AX_TRUSTED)())
            else:
                granted = bool(self.cg.bind(_CHECKS[permission])())
        except (NativeLibraryError, NativeSymbolError):
            return PermissionStatus(
                Backend.MACOS, permission, PermissionState.UNKNOWN, Support.UNSUPPORTED,
                detail="The documented system permission check is unavailable.",
            )
        return PermissionStatus(
            Backend.MACOS, permission,
            PermissionState.GRANTED if granted else PermissionState.UNKNOWN,
            detail=None if granted else _NO_GRANT,
        )

    def request(self, permission: Permission) -> PermissionStatus:
        current = self.check(permission)
        if current.granted or current.support is not Support.SUPPORTED:
            return current
        try:
            if permission is Permission.ACCESSIBILITY:
                granted = self._request_accessibility()
            else:
                granted = bool(self.cg.bind(_REQUESTS[permission])())
        except (NativeLibraryError, NativeSymbolError):
            return PermissionStatus(
                Backend.MACOS, permission, current.state, Support.UNSUPPORTED,
                detail="The documented system permission request is unavailable.",
            )
        return PermissionStatus(
            Backend.MACOS, permission,
            PermissionState.GRANTED if granted else PermissionState.UNKNOWN,
            request_sent=True,
            detail=None if granted else "Access is not currently granted; consent may be pending or require System Settings or a restart.",
        )

    def _request_accessibility(self) -> bool:
        request = self.app.bind(native.AX_REQUEST)
        release = self.cf.bind(native.CF_RELEASE)
        create = self.cf.bind(native.CF_DICTIONARY_CREATE)
        key = self.app.variable("kAXTrustedCheckOptionPrompt", native.CFTypeRef).value
        value = self.cf.variable("kCFBooleanTrue", native.CFTypeRef).value
        if not key or not value:
            raise NativeCallError("Accessibility prompt constants")
        keys, values = (native.CFTypeRef * 1)(key), (native.CFTypeRef * 1)(value)
        # Both entries are borrowed global constants. NULL callbacks neither
        # retain nor release them; the same global key is used by the AX API.
        pointer = create(None, keys, values, 1, None, None)
        if not pointer:
            raise NativeCallError("CFDictionaryCreate")
        with OwnedReference(pointer, release) as options:
            return bool(request(options.pointer))
