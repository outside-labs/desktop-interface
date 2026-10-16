"""Typed native desktop interfaces with passive imports.

Native desktop operations are introduced incrementally. Importing this package
does not load system libraries, request permission, or interact with the desktop.
"""

from .capabilities import Capability, Feature, PermissionState, Support
from .desktop import Desktop
from .errors import (
    ClosedSessionError,
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
from .permissions import Permission, Permissions, PermissionStatus

__version__ = "0.1.0"

__all__ = [
    "Backend", "Capability", "ClosedSessionError", "Desktop", "DesktopError", "DisplayId", "Feature",
    "NativeCallError", "NativeLibraryError", "NativeSymbolError",
    "OperationTimeoutError", "PermissionDeniedError", "PermissionRequiredError",
    "Permission", "Permissions", "PermissionState", "PermissionStatus", "Point", "Rect", "Size", "StaleTargetError", "Support",
    "UnsupportedFeatureError", "UnsupportedPlatformError", "WindowId", "__version__",
]
