"""Logical pointer motion and scoped ownership of mouse buttons."""

from contextlib import contextmanager
from enum import StrEnum
import math
from typing import TYPE_CHECKING

from ._input import cancellation, cleanup, duration as _duration, pause
from .errors import DisplayTopologyChangedError, UnsupportedFeatureError
from .geometry import Point

if TYPE_CHECKING:
    from .desktop import Desktop


class MouseButton(StrEnum):
    LEFT = "left"
    RIGHT = "right"
    MIDDLE = "middle"


class ScrollUnit(StrEnum):
    LINE = "line"
    PIXEL = "pixel"


def _button(value):
    if not isinstance(value, MouseButton):
        raise TypeError("button must be a MouseButton")


def _point(value):
    if not isinstance(value, Point):
        raise TypeError("position must be a Point in logical coordinates")


class Mouse:
    def __init__(self, desktop: "Desktop"):
        self._desktop = desktop
        self._owned: dict[MouseButton, tuple[int, Point]] = {}

    def position(self) -> Point:
        with self._desktop._operation() as backend:
            return backend.pointer_position()

    def is_pressed(self, button: MouseButton) -> bool:
        _button(button)
        with self._desktop._operation() as backend:
            return button in self._owned or backend.button_state(button)

    def _keys(self):
        return tuple(self._desktop.keyboard._owned)

    @staticmethod
    def _inside(topology, point):
        if not any(display.bounds.contains(point) for display in topology.displays):
            raise ValueError("pointer position must be on an active display")

    def _path(self, backend, position, seconds):
        topology = backend.display_snapshot()
        self._inside(topology, position)
        count = max(1, math.ceil(seconds * 60))
        origin = backend.pointer_position() if seconds else position
        path = tuple(Point(origin.x + (position.x - origin.x) * i / count,
                           origin.y + (position.y - origin.y) * i / count) for i in range(1, count + 1))
        for point in path:
            self._inside(topology, point)
        return topology, path

    def _motion_button(self, backend):
        pressed = tuple(button for button in MouseButton
                        if button in self._owned or backend.button_state(button))
        if len(pressed) > 1:
            raise UnsupportedFeatureError("Motion with multiple held buttons is not supported")
        return pressed[0] if pressed else None

    def _move_path(self, backend, topology, path, seconds, cancel):
        for index, point in enumerate(path):
            pause(seconds / len(path) if seconds else 0, cancel)
            if backend.display_snapshot().displays != topology.displays:
                raise DisplayTopologyChangedError("Display topology changed during pointer motion")
            button = self._motion_button(backend)
            backend.pointer_move(point, button, self._keys())
            if button in self._owned:
                count, _ = self._owned[button]
                self._owned[button] = (count, point)

    def move(self, position: Point, *, duration: float = 0, cancel=None):
        _point(position)
        seconds, cancel = _duration(duration), cancellation(cancel)
        pause(0, cancel)
        with self._desktop._operation() as backend:
            backend.require_post_access()
            topology, path = self._path(backend, position, seconds)
            self._move_path(backend, topology, path, seconds, cancel)

    def _acquire(self, backend, button, *, click_count=1):
        backend.require_post_access()
        if button in self._owned or backend.button_state(button):
            return False
        if any(other in self._owned or backend.button_state(other)
               for other in MouseButton if other != button):
            raise UnsupportedFeatureError("Multiple held mouse buttons are not supported")
        point = backend.pointer_position()
        self._inside(backend.display_snapshot(), point)
        self._owned[button] = (click_count, point)
        try:
            backend.button_event(button, True, point, self._keys(), click_count)
        except BaseException:
            self._release(backend, (button,))
            raise
        return True

    def _release(self, backend, buttons):
        def release(button):
            if button not in self._owned:
                return
            count, point = self._owned[button]
            try:
                try:
                    point = backend.pointer_position()
                except Exception:
                    pass  # last known point still permits a cleanup event
                backend.button_event(button, False, point, self._keys(), count)
            finally:
                self._owned.pop(button, None)
        cleanup([lambda button=button: release(button) for button in reversed(tuple(buttons))])

    def down(self, button: MouseButton = MouseButton.LEFT) -> bool:
        _button(button)
        with self._desktop._operation() as backend:
            return self._acquire(backend, button)

    def up(self, button: MouseButton = MouseButton.LEFT) -> bool:
        _button(button)
        with self._desktop._operation() as backend:
            owned = button in self._owned
            self._release(backend, (button,))
            return owned

    @contextmanager
    def hold(self, button: MouseButton = MouseButton.LEFT):
        _button(button)
        with self._desktop._operation() as backend:
            acquired = self._acquire(backend, button)
        try:
            yield self
        finally:
            if acquired:
                with self._desktop._lock:
                    self._release(backend, (button,))

    def click(self, button: MouseButton = MouseButton.LEFT, *, count: int = 1,
              interval: float = 0.1, cancel=None):
        _button(button)
        if isinstance(count, bool) or not isinstance(count, int):
            raise TypeError("count must be an integer")
        if not 1 <= count <= 3:
            raise ValueError("count must be between one and three")
        seconds, cancel = _duration(interval, "interval"), cancellation(cancel)
        if seconds * (count - 1) > 30:
            raise ValueError("click intervals exceed the 30-second wait budget")
        pause(0, cancel)
        with self._desktop._operation() as backend:
            for index in range(count):
                pause(seconds if index else 0, cancel)
                acquired = self._acquire(backend, button, click_count=index + 1)
                if not acquired:
                    return
                self._release(backend, (button,))

    def scroll(self, vertical: int, horizontal: int = 0, *, unit: ScrollUnit = ScrollUnit.LINE):
        for value in (vertical, horizontal):
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError("scroll deltas must be integers")
            if not -(1 << 31) <= value < 1 << 31:
                raise ValueError("scroll deltas must fit signed 32-bit values")
        if not isinstance(unit, ScrollUnit):
            raise TypeError("unit must be a ScrollUnit")
        with self._desktop._operation() as backend:
            if vertical or horizontal:
                backend.require_post_access()
                backend.scroll_event(vertical, horizontal, unit, self._keys())

    def drag(self, position: Point, *, button: MouseButton = MouseButton.LEFT,
             duration: float = 0.5, cancel=None):
        _point(position)
        _button(button)
        seconds, cancel = _duration(duration), cancellation(cancel)
        pause(0, cancel)
        with self._desktop._operation() as backend:
            backend.require_post_access()
            topology, path = self._path(backend, position, seconds)
            if button not in self._owned and backend.button_state(button):
                raise UnsupportedFeatureError("Cannot acquire a button already held outside this session")
            acquired = self._acquire(backend, button)
            try:
                self._move_path(backend, topology, path, seconds, cancel)
            finally:
                if acquired:
                    self._release(backend, (button,))

    def _close(self, backend):
        self._release(backend, tuple(self._owned))
