"""Physical key positions, Unicode text and scoped ownership of submitted keys."""

from contextlib import contextmanager
from enum import StrEnum, auto
from typing import TYPE_CHECKING

from ._input import cancellation, cleanup, duration as _duration, pause

if TYPE_CHECKING:
    from .desktop import Desktop


class Key(StrEnum):
    """Physical positions named after a US keyboard; text follows the active layout."""

    A = auto()
    B = auto()
    C = auto()
    D = auto()
    E = auto()
    F = auto()
    G = auto()
    H = auto()
    I = auto()
    J = auto()
    K = auto()
    L = auto()
    M = auto()
    N = auto()
    O = auto()
    P = auto()
    Q = auto()
    R = auto()
    S = auto()
    T = auto()
    U = auto()
    V = auto()
    W = auto()
    X = auto()
    Y = auto()
    Z = auto()
    DIGIT_0 = auto()
    DIGIT_1 = auto()
    DIGIT_2 = auto()
    DIGIT_3 = auto()
    DIGIT_4 = auto()
    DIGIT_5 = auto()
    DIGIT_6 = auto()
    DIGIT_7 = auto()
    DIGIT_8 = auto()
    DIGIT_9 = auto()
    MINUS = auto()
    EQUAL = auto()
    LEFT_BRACKET = auto()
    RIGHT_BRACKET = auto()
    BACKSLASH = auto()
    SEMICOLON = auto()
    QUOTE = auto()
    COMMA = auto()
    PERIOD = auto()
    SLASH = auto()
    BACKTICK = auto()
    RETURN = auto()
    TAB = auto()
    SPACE = auto()
    BACKSPACE = auto()
    DELETE = auto()
    ESCAPE = auto()
    HOME = auto()
    END = auto()
    PAGE_UP = auto()
    PAGE_DOWN = auto()
    LEFT = auto()
    RIGHT = auto()
    UP = auto()
    DOWN = auto()
    SHIFT = auto()
    RIGHT_SHIFT = auto()
    CONTROL = auto()
    RIGHT_CONTROL = auto()
    OPTION = auto()
    RIGHT_OPTION = auto()
    COMMAND = auto()
    RIGHT_COMMAND = auto()
    F1 = auto()
    F2 = auto()
    F3 = auto()
    F4 = auto()
    F5 = auto()
    F6 = auto()
    F7 = auto()
    F8 = auto()
    F9 = auto()
    F10 = auto()
    F11 = auto()
    F12 = auto()


MODIFIERS = frozenset((Key.SHIFT, Key.RIGHT_SHIFT, Key.CONTROL, Key.RIGHT_CONTROL,
                       Key.OPTION, Key.RIGHT_OPTION, Key.COMMAND, Key.RIGHT_COMMAND))


def _key(value):
    if not isinstance(value, Key):
        raise TypeError("key must be a Key")
    return value


def _keys(values):
    if not 1 <= len(values) <= 32:
        raise ValueError("provide between one and 32 keys")
    for value in values:
        _key(value)
    if len(set(values)) != len(values):
        raise ValueError("keys must be unique")
    return values


class Keyboard:
    def __init__(self, desktop: "Desktop") -> None:
        self._desktop = desktop
        self._owned: dict[Key, object] = {}

    def is_pressed(self, key: Key) -> bool:
        _key(key)
        with self._desktop._operation() as backend:
            return key in self._owned or backend.key_state(key)

    def _release(self, backend, keys):
        def release(key, token):
            if key not in self._owned or self._owned[key] is not token:
                return
            try:
                backend.key_event(key, False, tuple(item for item in self._owned if item != key))
            finally:
                if self._owned.get(key) is token:
                    self._owned.pop(key, None)
        cleanup([lambda key=key, token=token: release(key, token)
                 for key, token in reversed(tuple(keys.items()))])

    def _acquire(self, backend, keys):
        backend.require_post_access()
        acquired = {}
        try:
            for key in keys:
                if key in self._owned or backend.key_state(key):
                    continue
                # Record intent before posting: an exception may follow partial delivery.
                token = object()
                self._owned[key] = token
                acquired[key] = token
                backend.key_event(key, True, tuple(self._owned))
        except BaseException:
            self._release(backend, acquired)
            raise
        return acquired

    def down(self, key: Key) -> bool:
        _key(key)
        with self._desktop._operation() as backend:
            return bool(self._acquire(backend, (key,)))

    def up(self, key: Key) -> bool:
        _key(key)
        with self._desktop._operation() as backend:
            owned = key in self._owned
            self._release(backend, {key: self._owned.get(key)})
            return owned

    @contextmanager
    def hold(self, *keys: Key):
        _keys(keys)
        with self._desktop._operation() as backend:
            acquired = self._acquire(backend, keys)
        try:
            yield self
        finally:
            # close() may have released these keys while the context body ran.
            with self._desktop._lock:
                self._release(backend, acquired)

    def press(self, key: Key, *, duration: float = 0, cancel=None) -> None:
        _key(key)
        seconds, cancel = _duration(duration), cancellation(cancel)
        pause(0, cancel)
        with self.hold(key):
            pause(seconds, cancel)

    def shortcut(self, *keys: Key, cancel=None) -> None:
        _keys(keys)
        cancel = cancellation(cancel)
        if keys[-1] in MODIFIERS or any(key not in MODIFIERS for key in keys[:-1]):
            raise ValueError("shortcut requires modifiers followed by one nonmodifier key")
        pause(0, cancel)
        if len(keys) == 1:
            self.press(keys[0], cancel=cancel)
        else:
            with self.hold(*keys[:-1]):
                self.press(keys[-1], cancel=cancel)

    def type_text(self, text: str, *, interval: float = 0, cancel=None) -> None:
        if not isinstance(text, str):
            raise TypeError("text must be str")
        try:
            encoded = text.encode("utf-16-le")
        except UnicodeEncodeError:
            raise ValueError("text must not contain unpaired surrogates") from None
        if len(encoded) > 32768:
            raise ValueError("text is limited to 16384 UTF-16 units")
        seconds, cancel = _duration(interval, "interval"), cancellation(cancel)
        if seconds * max(0, len(text) - 1) > 30:
            raise ValueError("text intervals exceed the 30-second wait budget")
        # Encode every scalar before the first submitted event, preserving surrogate pairs.
        chunks = tuple(character.encode("utf-16-le") for character in text)
        with self._desktop._operation() as backend:
            pause(0, cancel)
            if not chunks:
                return
            backend.require_post_access()
            for index, chunk in enumerate(chunks):
                pause(seconds if index else 0, cancel)
                backend.text_pair(chunk, tuple(self._owned))

    def _close(self, backend):
        self._release(backend, dict(self._owned))
