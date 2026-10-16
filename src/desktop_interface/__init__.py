"""Typed native desktop interfaces with passive imports.

Native desktop operations are introduced incrementally. Importing this package
does not load system libraries, request permission, or interact with the desktop.
"""

from .capabilities import Capability, Feature, PermissionState, Support
from .desktop import Desktop
from .displays import Display, Displays, DisplayTopology, PixelLocation, PixelPoint, PixelSize
from .errors import (
    AmbiguousTargetError,
    ClosedSessionError,
    DesktopError,
    DisplayTopologyChangedError,
    InputCancelledError,
    NativeCallError,
    NativeLibraryError,
    NativeSymbolError,
    OperationTimeoutError,
    PermissionDeniedError,
    PermissionRequiredError,
    StaleTargetError,
    TargetNotFoundError,
    UnsupportedFeatureError,
    UnsupportedPlatformError,
)
from .geometry import Point, Rect, Size
from .identifiers import Backend, DisplayId, WindowId
from .keyboard import Key, Keyboard
from .permissions import Permission, Permissions, PermissionStatus
from .windows import Window, WindowInfo, Windows, WindowState

__version__ = "0.1.0"

__all__ = [
    "AmbiguousTargetError", "Backend", "Capability", "ClosedSessionError", "Desktop", "DesktopError",
    "Display", "DisplayId", "Displays", "DisplayTopology", "DisplayTopologyChangedError", "Feature",
    "InputCancelledError", "Key", "Keyboard", "NativeCallError", "NativeLibraryError", "NativeSymbolError",
    "OperationTimeoutError", "PermissionDeniedError", "PermissionRequiredError",
    "Permission", "Permissions", "PermissionState", "PermissionStatus", "PixelLocation", "PixelPoint", "PixelSize",
    "Point", "Rect", "Size", "StaleTargetError", "Support", "TargetNotFoundError",
    "UnsupportedFeatureError", "UnsupportedPlatformError", "Window", "WindowId", "WindowInfo", "Windows", "WindowState", "__version__",
]
