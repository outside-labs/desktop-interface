"""Expected desktop operation failures, independent of native implementation."""


class DesktopError(Exception):
    """Base class for expected desktop operation failures."""


class ClosedSessionError(DesktopError):
    """The operation belongs to a desktop session that has been closed."""


class UnsupportedPlatformError(DesktopError):
    """The selected native backend cannot run on this system."""


class UnsupportedFeatureError(DesktopError):
    """The backend or target does not implement the requested operation."""


class PermissionRequiredError(DesktopError):
    """The operation needs system access that has not been established."""


class PermissionDeniedError(PermissionRequiredError):
    """The required system access was explicitly denied."""


class NativeLibraryError(DesktopError):
    """A required system library could not be loaded."""


class NativeSymbolError(DesktopError):
    """The loaded system library does not expose a required function."""


class NativeCallError(DesktopError):
    """A native operation failed; its original status code is retained."""

    def __init__(self, operation: str, *, code: int | None = None) -> None:
        self.operation = operation
        self.code = code
        suffix = "" if code is None else f" (native code {code})"
        super().__init__(f"{operation} failed{suffix}")


class StaleTargetError(DesktopError):
    """The referenced window or UI element no longer identifies a live target."""


class TargetNotFoundError(DesktopError):
    """No current target matches the requested identity or filters."""


class AmbiguousTargetError(DesktopError):
    """More than one target matches and an explicit selection is required."""


class DisplayTopologyChangedError(DesktopError):
    """Display state changed throughout a bounded snapshot attempt."""


class OperationTimeoutError(DesktopError):
    """A bounded wait expired before the requested condition was observed."""
