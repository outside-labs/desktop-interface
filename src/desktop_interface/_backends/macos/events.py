"""Exact Quartz event construction; posting reports submission, never delivery."""

import ctypes as c
from contextlib import contextmanager

from ..._native import macos as n
from ..._native.ownership import OwnedReference
from ...errors import NativeCallError
from ...keyboard import Key
from ...geometry import Point
from ...mouse import MouseButton, ScrollUnit


KEY_CODES = dict(zip(
    (Key.A, Key.S, Key.D, Key.F, Key.H, Key.G, Key.Z, Key.X, Key.C, Key.V, Key.B,
     Key.Q, Key.W, Key.E, Key.R, Key.Y, Key.T, Key.DIGIT_1, Key.DIGIT_2, Key.DIGIT_3,
     Key.DIGIT_4, Key.DIGIT_6, Key.DIGIT_5, Key.EQUAL, Key.DIGIT_9, Key.DIGIT_7,
     Key.MINUS, Key.DIGIT_8, Key.DIGIT_0, Key.RIGHT_BRACKET, Key.O, Key.U,
     Key.LEFT_BRACKET, Key.I, Key.P, Key.RETURN, Key.L, Key.J, Key.QUOTE, Key.K,
     Key.SEMICOLON, Key.BACKSLASH, Key.COMMA, Key.SLASH, Key.N, Key.M, Key.PERIOD,
     Key.TAB, Key.SPACE, Key.BACKTICK, Key.BACKSPACE, Key.ESCAPE, Key.RIGHT_COMMAND,
     Key.COMMAND, Key.SHIFT, Key.OPTION, Key.CONTROL, Key.RIGHT_SHIFT, Key.RIGHT_OPTION,
     Key.RIGHT_CONTROL, Key.F1, Key.F2, Key.F3, Key.F4, Key.F5, Key.F6, Key.F7, Key.F8,
     Key.F9, Key.F10, Key.F11, Key.F12, Key.HOME, Key.END, Key.PAGE_UP, Key.PAGE_DOWN,
     Key.DELETE, Key.LEFT, Key.RIGHT, Key.DOWN, Key.UP),
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21,
     22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40,
     41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 53, 54, 55, 56, 58, 59, 60, 61,
     62, 122, 120, 99, 118, 96, 97, 98, 100, 101, 109, 103, 111, 115, 119, 116,
     121, 117, 123, 124, 125, 126), strict=True))
MODIFIER_FLAGS = ((1 << 17, (Key.SHIFT, Key.RIGHT_SHIFT)),
                  (1 << 18, (Key.CONTROL, Key.RIGHT_CONTROL)),
                  (1 << 19, (Key.OPTION, Key.RIGHT_OPTION)),
                  (1 << 20, (Key.COMMAND, Key.RIGHT_COMMAND)))


class MacOSEvents:
    def __init__(self):
        self.cg = n.core_graphics()
        self.cf = n.core_foundation()

    def key_state(self, key):
        return bool(self.cg.bind(n.CG_KEY_STATE)(0, KEY_CODES[key]))

    def flags(self, owned, releasing=None):
        flags = self.cg.bind(n.CG_FLAGS_STATE)(0)
        state = self.cg.bind(n.CG_KEY_STATE)
        for mask, keys in MODIFIER_FLAGS:
            flags &= ~mask
            if any(key in owned or state(1 if key == releasing else 0, KEY_CODES[key]) for key in keys):
                flags |= mask
        return flags

    def key_event(self, key, down, owned):
        post = self.cg.bind(n.CG_EVENT_POST)
        with self._keyboard(KEY_CODES[key], down, owned, releasing=None if down else key) as event:
            post(0, event)

    def text_pair(self, payload, owned):
        post = self.cg.bind(n.CG_EVENT_POST)
        # Prepare the release event before the first submission.
        with self._keyboard(0, True, owned, payload=payload) as down, \
             self._keyboard(0, False, owned, payload=payload) as up:
            try:
                post(0, down)
            finally:
                post(0, up)

    @contextmanager
    def _keyboard(self, code, down, owned, *, releasing=None, payload=None):
        release = self.cf.bind(n.CF_RELEASE)
        create = self.cg.bind(n.CG_KEY_EVENT)
        # Resolve all required symbols before allocating/posting this event.
        set_flags = self.cg.bind(n.CG_EVENT_FLAGS)
        set_text = self.cg.bind(n.CG_EVENT_UNICODE) if payload is not None else None
        flags = self.flags(owned, releasing)
        pointer = create(None, code, down)
        if not pointer:
            raise NativeCallError("CGEventCreateKeyboardEvent")
        with OwnedReference(pointer, release) as event:
            set_flags(event.pointer, flags)
            if payload is not None:
                count = len(payload) // 2
                buffer = (c.c_uint16 * count).from_buffer_copy(payload)
                set_text(event.pointer, count, buffer)
            yield event.pointer

    def pointer_position(self):
        release = self.cf.bind(n.CF_RELEASE)
        get = self.cg.bind(n.CG_POINTER_LOCATION)
        pointer = self.cg.bind(n.CG_POINTER_EVENT)(None)
        if not pointer:
            raise NativeCallError("CGEventCreate")
        with OwnedReference(pointer, release) as event:
            location = get(event.pointer)
            try:
                return Point(location.x, location.y)
            except (TypeError, ValueError):
                raise NativeCallError("CGEventGetLocation") from None

    def button_state(self, button):
        return bool(self.cg.bind(n.CG_BUTTON_STATE)(0, _BUTTONS[button]))

    def _pointer(self, factory, owned_keys, *, click_count=None):
        release = self.cf.bind(n.CF_RELEASE)
        post, flags = self.cg.bind(n.CG_EVENT_POST), self.cg.bind(n.CG_EVENT_FLAGS)
        integer = self.cg.bind(n.CG_EVENT_INTEGER) if click_count is not None else None
        current = self.flags(owned_keys)
        pointer = factory()
        if not pointer:
            raise NativeCallError("Quartz pointer event allocation")
        with OwnedReference(pointer, release) as event:
            flags(event.pointer, current)
            if click_count is not None:
                integer(event.pointer, 1, click_count)  # kCGMouseEventClickState
            post(0, event.pointer)

    def button_event(self, button, down, point, owned_keys, click_count):
        code = _BUTTONS[button]
        kind = ((1, 2) if code == 0 else (3, 4) if code == 1 else (25, 26))[not down]
        create = self.cg.bind(n.CG_MOUSE_EVENT)
        self._pointer(lambda: create(None, kind, n.CGPoint(point.x, point.y), code),
                      owned_keys, click_count=click_count)

    def pointer_move(self, point, button, owned_keys):
        kind = 5 if button is None else {MouseButton.LEFT: 6, MouseButton.RIGHT: 7, MouseButton.MIDDLE: 27}[button]
        code = 0 if button is None else _BUTTONS[button]
        create = self.cg.bind(n.CG_MOUSE_EVENT)
        self._pointer(lambda: create(None, kind, n.CGPoint(point.x, point.y), code), owned_keys)

    def scroll_event(self, vertical, horizontal, unit, owned_keys):
        create = self.cg.bind(n.CG_SCROLL_EVENT)
        self._pointer(lambda: create(None, 1 if unit is ScrollUnit.LINE else 0,
                                     2, vertical, horizontal, 0), owned_keys)


_BUTTONS = {MouseButton.LEFT: 0, MouseButton.RIGHT: 1, MouseButton.MIDDLE: 2}
