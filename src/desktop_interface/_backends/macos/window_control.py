"""Conservative public-API matching from Quartz metadata to Accessibility windows."""

from contextlib import ExitStack
import ctypes as c
import time

from ..._native import macos as n
from ..._native.collections import CFReader
from ..._native.ownership import OwnedReference
from ...errors import (AmbiguousTargetError, NativeCallError, OperationTimeoutError,
                       PermissionRequiredError, StaleTargetError, UnsupportedFeatureError)
from ...geometry import Point, Rect, Size
from ...windows import WindowInfo, WindowState


def _status(code: int, operation: str) -> None:
    if not code:
        return
    native = NativeCallError(operation, code=code)
    if code == -25211:  # kAXErrorAPIDisabled
        raise PermissionRequiredError("Accessibility access is unavailable") from native
    if code == -25202:
        raise StaleTargetError("Accessibility window is no longer valid") from native
    if code in (-25205, -25206, -25208):
        raise UnsupportedFeatureError("The application does not support this window operation") from native
    raise native


class _Access:
    def __init__(self, stack: ExitStack) -> None:
        self.stack = stack
        self.cf = CFReader()
        self.ax = n.application_services()
        self.release = self.cf.library.bind(n.CF_RELEASE)
        self.names = {}
        self.deadline = time.monotonic() + 5

    def own(self, pointer):
        if not pointer:
            raise NativeCallError("Accessibility allocation/copy")
        return self.stack.enter_context(OwnedReference(pointer, self.release)).pointer

    def name(self, text):
        if text not in self.names:
            data = text.encode("utf-8")
            buffer = (c.c_uint8 * len(data)).from_buffer_copy(data)
            self.names[text] = self.own(self.cf.library.bind(n.CF_STRING_CREATE)(
                None, buffer, len(data), n.UTF8, False))
        return self.names[text]

    def budget(self, element):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise OperationTimeoutError("Accessibility query budget expired")
        _status(self.ax.bind(n.AX_TIMEOUT)(element, min(0.25, remaining)), "AXUIElementSetMessagingTimeout")

    def copy(self, element, name, *, optional=False):
        self.budget(element)
        result = n.CFTypeRef()
        code = self.ax.bind(n.AX_COPY)(element, self.name(name), c.byref(result))
        # On failure the out parameter is not owned by the caller.
        if optional and code in (-25205, -25212):
            return None
        _status(code, "AXUIElementCopyAttributeValue")
        return self.own(result)

    def geometry(self, element):
        parts = []
        for name, kind, structure in (("AXPosition", 1, n.CGPoint), ("AXSize", 2, n.CGSize)):
            pointer = self.copy(element, name, optional=True)
            if pointer is None:
                return None
            self.expect(pointer, n.AX_VALUE_TYPE_ID)
            value = structure()
            if self.ax.bind(n.AX_VALUE_TYPE)(pointer) != kind or not self.ax.bind(n.AX_VALUE_GET)(pointer, kind, c.byref(value)):
                raise NativeCallError("AXValueGetValue geometry")
            parts.append(value)
        try:
            return Rect(parts[0].x, parts[0].y, parts[1].width, parts[1].height)
        except (TypeError, ValueError):
            raise NativeCallError("Accessibility geometry") from None

    def settable(self, element, name):
        self.budget(element)
        result = n.Boolean()
        _status(self.ax.bind(n.AX_SETTABLE)(element, self.name(name), c.byref(result)), "AXUIElementIsAttributeSettable")
        if not result.value:
            raise UnsupportedFeatureError("The window attribute is not writable")

    def expect(self, pointer, spec):
        if not pointer or self.cf.library.bind(n.CF_TYPE_ID)(pointer) != self.ax.bind(spec)():
            raise NativeCallError("Accessibility object type")

    def set(self, element, name, value):
        self.budget(element)
        _status(self.ax.bind(n.AX_SET)(element, self.name(name), value), "AXUIElementSetAttributeValue")

    def boolean(self, value):
        pointer = self.cf.library.variable("kCFBooleanTrue" if value else "kCFBooleanFalse", n.CFTypeRef)
        if not pointer.value:
            raise NativeCallError("CoreFoundation Boolean constant")
        return pointer

    def match(self, info):
        if info.bounds is None or not 0 < info.process_id < (1 << 31):
            raise UnsupportedFeatureError("Window control needs bounds and a positive native owner PID")
        app = self.own(self.ax.bind(n.AX_APPLICATION)(info.process_id))
        windows = self.copy(app, "AXWindows")
        matches = []
        for element in self.cf.array(windows, limit=128):
            self.expect(element, n.AX_ELEMENT_TYPE)
            self.budget(element)
            pid = n.pid_t()
            _status(self.ax.bind(n.AX_PID)(element, c.byref(pid)), "AXUIElementGetPid")
            if pid.value != info.process_id:
                continue
            bounds = self.geometry(element)
            if bounds is None or not _near(bounds, info.bounds):
                continue
            title = self.cf.text(self.copy(element, "AXTitle", optional=True))
            if info.title is not None and title != info.title:
                continue
            matches.append(element)
        if not matches:
            raise StaleTargetError("No Accessibility window matches the current Quartz metadata")
        if len(matches) != 1:
            raise AmbiguousTargetError("Accessibility windows have indistinguishable metadata")
        return app, matches[0]

    def state(self, app, element):
        bounds = self.geometry(element)
        minimized = self.cf.boolean(self.copy(element, "AXMinimized", optional=True))
        frontmost = self.cf.boolean(self.copy(app, "AXFrontmost", optional=True))
        focused = self.copy(app, "AXFocusedWindow", optional=True)
        is_focused = None if frontmost is None or focused is None else bool(
            frontmost and self.cf.library.bind(n.CF_EQUAL)(element, focused))
        return WindowState(bounds, minimized, is_focused)


def _near(left: Rect, right: Rect) -> bool:
    return all(abs(a - b) <= 0.5 for a, b in zip(
        (left.x, left.y, left.width, left.height), (right.x, right.y, right.width, right.height)))


class MacOSWindowControl:
    def __init__(self, windows) -> None:
        self.windows = windows

    def run(self, info: WindowInfo, action: str | None = None, value=None,
            timeout: float | None = None) -> WindowState | None:
        with ExitStack() as stack:
            access = _Access(stack)
            app, element = access.match(info)
            current = self.windows.get(info.id, expected_process_id=info.process_id)
            if current.bounds != info.bounds or current.title != info.title:
                raise StaleTargetError("Window metadata changed while matching Accessibility")
            if action is None:
                return access.state(app, element)
            if action == "focus":
                # Check every advertised operation before making the first change.
                access.settable(app, "AXFrontmost")
                access.settable(app, "AXFocusedWindow")
                result = n.CFTypeRef()
                access.budget(element)
                _status(access.ax.bind(n.AX_ACTIONS)(element, c.byref(result)), "AXUIElementCopyActionNames")
                names = access.own(result)
                if "AXRaise" not in tuple(access.cf.text(item) for item in access.cf.array(names, limit=32)):
                    raise UnsupportedFeatureError("The window does not advertise AXRaise")
                access.set(app, "AXFocusedWindow", element)
                access.set(app, "AXFrontmost", access.boolean(True))
                access.budget(element)
                _status(access.ax.bind(n.AX_ACTION)(element, access.name("AXRaise")), "AXUIElementPerformAction")
            else:
                name = {"move": "AXPosition", "resize": "AXSize", "minimize": "AXMinimized"}[action]
                access.settable(element, name)
                if action == "minimize":
                    pointer = access.boolean(value)
                else:
                    structure = n.CGPoint(value.x, value.y) if action == "move" else n.CGSize(value.width, value.height)
                    pointer = access.own(access.ax.bind(n.AX_VALUE_CREATE)(1 if action == "move" else 2, c.byref(structure)))
                access.set(element, name, pointer)
            if timeout is None:
                return None
            deadline = time.monotonic() + timeout
            # Confirmation has its own budget; individual IPC calls stay bounded.
            access.deadline = deadline + 1
            while True:
                self.windows.get(info.id, expected_process_id=info.process_id)
                state = access.state(app, element)
                matched = (state.focused is True if action == "focus" else
                           state.minimized is value if action == "minimize" else
                           state.bounds is not None and (
                               _near(state.bounds, Rect(value.x, value.y, state.bounds.width, state.bounds.height))
                               if action == "move" else
                               _near(state.bounds, Rect(state.bounds.x, state.bounds.y, value.width, value.height))))
                if matched:
                    return state
                if time.monotonic() >= deadline:
                    raise OperationTimeoutError("The application did not confirm the requested window state")
                time.sleep(min(0.02, max(0, deadline - time.monotonic())))
