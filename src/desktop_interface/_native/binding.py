"""Explicit function signatures and lazy loading of known system libraries."""

from dataclasses import dataclass
import ctypes
from pathlib import PurePosixPath, PureWindowsPath
import sys
from threading import Lock
from typing import Callable

from ..errors import NativeLibraryError, NativeSymbolError, UnsupportedPlatformError


@dataclass(frozen=True, slots=True)
class FunctionSpec:
    """A complete C function declaration; None explicitly means a void result."""

    name: str
    argtypes: tuple[type, ...]
    restype: type | None

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.isidentifier():
            raise ValueError("A native function needs an explicit symbol name")
        if not isinstance(self.argtypes, tuple):
            raise TypeError("argtypes must be an immutable tuple")


class NativeLibrary:
    """Load one trusted absolute system path only when a function is bound.

    This is a private C-declaration helper, not a user-configurable library
    search mechanism. Binding never calls the resolved function. Result/error
    conventions remain the responsibility of each native operation.
    """

    def __init__(
        self, path: str, *, platform: str,
        loader: Callable[..., object] | None = None,
    ) -> None:
        if not isinstance(path, str):
            raise TypeError("path must be a string")
        if not (PurePosixPath(path).is_absolute() or PureWindowsPath(path).is_absolute()):
            raise ValueError("A system library requires an absolute path")
        self.path = path
        self.platform = platform
        self._loader = loader
        self._handle = None
        self._functions: dict[str, tuple[FunctionSpec, Callable]] = {}
        self._lock = Lock()

    def _check_platform(self) -> None:
        if sys.platform != self.platform:
            raise UnsupportedPlatformError(f"This system library requires {self.platform}")
        if self.platform == "darwin" and ctypes.sizeof(ctypes.c_void_p) != 8:
            raise UnsupportedPlatformError("The macOS backend requires a 64-bit process")

    def _library(self):
        """Return the handle while the caller holds the declaration lock."""
        if self._handle is None:
            loader = self._loader if self._loader is not None else ctypes.CDLL
            try:
                self._handle = loader(self.path)
            except OSError as error:
                raise NativeLibraryError(f"Cannot load system library {self.path}") from error
        return self._handle

    def variable(self, name: str, ctype: type):
        """Read an explicitly typed exported variable, borrowing its storage."""
        if not isinstance(name, str) or not name.isidentifier():
            raise ValueError("A native variable needs an explicit symbol name")
        if not callable(getattr(ctype, "in_dll", None)):
            raise TypeError("ctype must support in_dll")
        self._check_platform()
        with self._lock:
            try:
                return ctype.in_dll(self._library(), name)
            except ValueError as error:
                raise NativeSymbolError(f"System variable {name} is unavailable") from error

    def bind(self, spec: FunctionSpec) -> Callable:
        if not isinstance(spec, FunctionSpec):
            raise TypeError("spec must be a FunctionSpec")
        self._check_platform()
        with self._lock:
            if spec.name in self._functions:
                declaration, function = self._functions[spec.name]
                if declaration != spec:
                    raise ValueError(f"Conflicting native declaration for {spec.name}")
                return function
            try:
                function = getattr(self._library(), spec.name)
            except AttributeError as error:
                raise NativeSymbolError(f"System function {spec.name} is unavailable") from error
            function.argtypes = list(spec.argtypes)
            function.restype = spec.restype
            self._functions[spec.name] = (spec, function)
            return function
