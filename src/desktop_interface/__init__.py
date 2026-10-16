"""Typed native desktop interfaces with passive imports.

Native desktop operations are introduced incrementally. Importing this package
does not load system libraries, request permission, or interact with the desktop.
"""

from .capabilities import Capability, Feature, PermissionState, Support
from .errors import (
    DesktopError,
    NativeCallError,
    NativeLibraryError,
    NativeSymbolError,
    OperationTimeoutError,
    PermissionDeniedError,
    PermissionRequiredError,
    StaleTargetError,
    UnsupportedFeatureError,
    UnsupportedPlatformError,
)
from .geometry import Point, Rect, Size
from .identifiers import Backend, DisplayId, WindowId

__version__ = "0.1.0"

__all__ = [
    "Backend", "Capability", "DesktopError", "DisplayId", "Feature",
    "NativeCallError", "NativeLibraryError", "NativeSymbolError",
    "OperationTimeoutError", "PermissionDeniedError", "PermissionRequiredError",
    "PermissionState", "Point", "Rect", "Size", "StaleTargetError", "Support",
    "UnsupportedFeatureError", "UnsupportedPlatformError", "WindowId", "__version__",
]
