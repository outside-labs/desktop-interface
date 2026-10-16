"""An explicit desktop session with passive construction and bounded lifetime."""

from contextlib import contextmanager
import sys
from threading import RLock
from typing import Iterator

from ._backends.macos.backend import MacOSBackend
from .capabilities import Capability
from .displays import Displays
from .errors import ClosedSessionError, UnsupportedPlatformError
from .identifiers import Backend
from .permissions import Permissions
from .windows import Windows


class Desktop:
    """Own a native backend; construction does not load libraries or ask for access."""

    def __init__(self, backend: Backend | str | None = None) -> None:
        if isinstance(backend, str):
            backend = Backend(backend)
        if backend is not None and not isinstance(backend, Backend):
            raise TypeError("backend must be a Backend, its name, or None")
        selected = Backend.MACOS if backend is None and sys.platform == "darwin" else backend
        if selected is not Backend.MACOS or sys.platform != "darwin":
            raise UnsupportedPlatformError("Only the macOS native backend is implemented")
        self._backend = MacOSBackend()
        self._lock = RLock()
        self._closed = False
        self._permissions = Permissions(self)
        self._displays = Displays(self)
        self._windows = Windows(self)

    @property
    def backend(self) -> Backend:
        return Backend.MACOS

    @property
    def permissions(self) -> Permissions:
        return self._permissions

    @property
    def displays(self) -> Displays:
        return self._displays

    @property
    def windows(self) -> Windows:
        return self._windows

    @property
    def closed(self) -> bool:
        with self._lock:
            return self._closed

    @contextmanager
    def _operation(self) -> Iterator[MacOSBackend]:
        with self._lock:
            if self._closed:
                raise ClosedSessionError("Desktop session is closed")
            yield self._backend

    def capabilities(self) -> tuple[Capability, ...]:
        with self._operation() as backend:
            return backend.capabilities()

    def close(self) -> None:
        with self._lock:
            self._closed = True

    def __enter__(self) -> "Desktop":
        with self._operation():
            return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()
