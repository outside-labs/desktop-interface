"""Window metadata and explicit references that revalidate owner identity."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .errors import AmbiguousTargetError, StaleTargetError, TargetNotFoundError, UnsupportedFeatureError
from .geometry import Point, Rect, Size, _finite
from .identifiers import WindowId

if TYPE_CHECKING:
    from .desktop import Desktop


def _process_id(value: int | None) -> None:
    if value is not None:
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError("process_id must be an integer or None")
        if not 0 <= value <= 0xFFFFFFFF:
            raise ValueError("process_id must be a nonnegative 32-bit process identifier")


@dataclass(frozen=True, slots=True)
class WindowInfo:
    """Copied metadata; missing fields remain None rather than guessed values."""

    id: WindowId
    process_id: int | None
    bounds: Rect | None = None
    title: str | None = None
    owner_name: str | None = None
    layer: int | None = None
    is_on_screen: bool | None = None
    alpha: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.id, WindowId):
            raise TypeError("id must be a WindowId")
        _process_id(self.process_id)
        if self.bounds is not None and not isinstance(self.bounds, Rect):
            raise TypeError("bounds must be a Rect or None")
        for name in ("title", "owner_name"):
            if getattr(self, name) is not None and not isinstance(getattr(self, name), str):
                raise TypeError(f"{name} must be a string or None")
        if self.layer is not None and (isinstance(self.layer, bool) or not isinstance(self.layer, int)):
            raise TypeError("layer must be an integer or None")
        if self.is_on_screen is not None and not isinstance(self.is_on_screen, bool):
            raise TypeError("is_on_screen must be a bool or None")
        if self.alpha is not None:
            object.__setattr__(self, "alpha", _finite(self.alpha, "alpha"))
            if not 0 <= self.alpha <= 1:
                raise ValueError("alpha must be between zero and one")


@dataclass(frozen=True, slots=True)
class WindowState:
    """Accessibility state copied from a uniquely matched window."""

    bounds: Rect | None
    minimized: bool | None
    focused: bool | None

    def __post_init__(self):
        if self.bounds is not None and not isinstance(self.bounds, Rect):
            raise TypeError("bounds must be a Rect or None")
        for name in ("minimized", "focused"):
            if getattr(self, name) is not None and not isinstance(getattr(self, name), bool):
                raise TypeError(f"{name} must be bool or None")


class Window:
    """A session-local ID/owner pair, revalidated on each read.

    Native IDs and PIDs can both be recycled. This pair detects ordinary owner
    changes and disappearance; it is not a durable identity across sessions.
    """

    def __init__(self, desktop: "Desktop", initial: WindowInfo) -> None:
        if not isinstance(initial, WindowInfo):
            raise TypeError("initial must be WindowInfo")
        if initial.id.backend is not desktop.backend:
            raise ValueError("Window ID belongs to a different backend")
        if initial.process_id is None:
            raise UnsupportedFeatureError("Window owner identity is unavailable")
        self._desktop = desktop
        self._initial = initial
        self._process_id = initial.process_id

    @property
    def id(self) -> WindowId:
        return self._initial.id

    @property
    def process_id(self) -> int:
        return self._process_id

    @property
    def initial(self) -> WindowInfo:
        return self._initial

    def read(self) -> WindowInfo:
        with self._desktop._operation() as backend:
            try:
                info = backend.window_info(self.id, expected_process_id=self.process_id)
            except TargetNotFoundError as error:
                raise StaleTargetError("Window disappeared or its owner identity changed") from error
            if info.id != self.id or info.process_id != self.process_id:
                raise StaleTargetError("Window identity no longer matches this reference")
            return info

    def _control(self, action=None, value=None, timeout=None):
        if timeout is not None:
            timeout = _finite(timeout, "timeout")
            if not 0 <= timeout <= 30:
                raise ValueError("timeout must be between zero and 30 seconds")
        with self._desktop._operation() as backend:
            try:
                return backend.window_control(self.id, self.process_id, action, value, timeout)
            except TargetNotFoundError as error:
                raise StaleTargetError("Window disappeared or its owner changed") from error

    def state(self) -> WindowState:
        return self._control()

    def move(self, position: Point, *, timeout: float | None = None) -> WindowState | None:
        if not isinstance(position, Point):
            raise TypeError("position must be a Point")
        return self._control("move", position, timeout)

    def resize(self, size: Size, *, timeout: float | None = None) -> WindowState | None:
        if not isinstance(size, Size):
            raise TypeError("size must be a Size")
        if size.width <= 0 or size.height <= 0:
            raise ValueError("window size must be positive")
        return self._control("resize", size, timeout)

    def focus(self, *, timeout: float | None = None) -> WindowState | None:
        return self._control("focus", timeout=timeout)

    def minimize(self, minimized: bool = True, *, timeout: float | None = None) -> WindowState | None:
        if not isinstance(minimized, bool):
            raise TypeError("minimized must be bool")
        return self._control("minimize", minimized, timeout)


class Windows:
    def __init__(self, desktop: "Desktop") -> None:
        self._desktop = desktop

    @staticmethod
    def _validate_options(process_id: int | None, onscreen_only: bool) -> None:
        _process_id(process_id)
        if not isinstance(onscreen_only, bool):
            raise TypeError("onscreen_only must be a bool")

    def list(self, *, process_id: int | None = None, onscreen_only: bool = True) -> tuple[WindowInfo, ...]:
        self._validate_options(process_id, onscreen_only)
        with self._desktop._operation() as backend:
            return backend.window_list(process_id=process_id, onscreen_only=onscreen_only)

    def get(self, window_id: WindowId) -> Window:
        if not isinstance(window_id, WindowId):
            raise TypeError("window_id must be a WindowId")
        if window_id.backend is not self._desktop.backend:
            raise ValueError("Window ID belongs to a different backend")
        with self._desktop._operation() as backend:
            info = backend.window_info(window_id)
            if info.id != window_id:
                raise StaleTargetError("Window identity changed during lookup")
            return Window(self._desktop, info)

    def find(self, *, process_id: int | None = None, title: str | None = None,
             owner_name: str | None = None, onscreen_only: bool = True) -> Window:
        self._validate_options(process_id, onscreen_only)
        for name, value in (("title", title), ("owner_name", owner_name)):
            if value is not None and not isinstance(value, str):
                raise TypeError(f"{name} must be a string or None")
        with self._desktop._operation() as backend:
            matches = [item for item in backend.window_list(process_id=process_id, onscreen_only=onscreen_only)
                       if (process_id is None or item.process_id == process_id)
                       and (title is None or item.title == title)
                       and (owner_name is None or item.owner_name == owner_name)]
            if not matches:
                raise TargetNotFoundError("No window matches the requested filters")
            if len(matches) != 1:
                raise AmbiguousTargetError("Multiple windows match; choose a process or window ID")
            return Window(self._desktop, matches[0])
