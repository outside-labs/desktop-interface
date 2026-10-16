"""Deterministic cleanup for native references with an explicit owner."""

import ctypes
from threading import Lock
from typing import Callable


class OwnedReference:
    """Own one non-null reference and release it at most once.

    Borrowed references must not be wrapped unless first retained. Use a context
    manager or close explicitly; cleanup does not depend on a finalizer. The
    release path is concurrency-safe, but a caller must not use a borrowed
    pointer concurrently with close(). A returned pointer does not retain it.
    """

    def __init__(
        self, pointer: int | ctypes.c_void_p,
        release: Callable[[ctypes.c_void_p], object],
    ) -> None:
        address = pointer.value if isinstance(pointer, ctypes.c_void_p) else pointer
        if isinstance(address, bool) or (address is not None and not isinstance(address, int)):
            raise TypeError("pointer must be an integer address or c_void_p")
        if address is None or address <= 0 or address >= 1 << (ctypes.sizeof(ctypes.c_void_p) * 8):
            raise ValueError("pointer must be a non-null address that fits the native pointer size")
        if not callable(release):
            raise TypeError("release must be callable")
        self._address: int | None = address
        self._release = release
        self._lock = Lock()

    @property
    def closed(self) -> bool:
        with self._lock:
            return self._address is None

    @property
    def pointer(self) -> ctypes.c_void_p:
        with self._lock:
            if self._address is None:
                raise ReferenceError("Native reference is closed")
            return ctypes.c_void_p(self._address)

    def close(self) -> None:
        with self._lock:
            address, self._address = self._address, None
        if address is not None:
            self._release(ctypes.c_void_p(address))

    def __enter__(self) -> "OwnedReference":
        self.pointer
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()
