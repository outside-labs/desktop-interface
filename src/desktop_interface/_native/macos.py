"""C declarations for the documented 64-bit macOS ABI, without native calls."""

import ctypes as c

from .binding import FunctionSpec, NativeLibrary


CGFloat = c.c_double
CGDirectDisplayID = c.c_uint32
CGError = c.c_int32
Boolean = c.c_uint8
CFIndex = c.c_int64
CFTypeID = c.c_uint64
CFTypeRef = c.c_void_p
CFStringRef = c.c_void_p
CFStringEncoding = c.c_uint32
UTF8 = 0x08000100


class CGPoint(c.Structure):
    _fields_ = [("x", CGFloat), ("y", CGFloat)]


class CGSize(c.Structure):
    _fields_ = [("width", CGFloat), ("height", CGFloat)]


class CGRect(c.Structure):
    _fields_ = [("origin", CGPoint), ("size", CGSize)]


class CFRange(c.Structure):
    _fields_ = [("location", CFIndex), ("length", CFIndex)]


CF_RELEASE = FunctionSpec("CFRelease", (CFTypeRef,), None)
CF_RETAIN = FunctionSpec("CFRetain", (CFTypeRef,), CFTypeRef)
CF_STRING_CREATE = FunctionSpec(
    "CFStringCreateWithBytes",
    (CFTypeRef, c.POINTER(c.c_uint8), CFIndex, CFStringEncoding, Boolean), CFStringRef,
)
CF_STRING_LENGTH = FunctionSpec("CFStringGetLength", (CFStringRef,), CFIndex)
CF_STRING_BYTES = FunctionSpec(
    "CFStringGetBytes",
    (CFStringRef, CFRange, CFStringEncoding, c.c_uint8, Boolean,
     c.POINTER(c.c_uint8), CFIndex, c.POINTER(CFIndex)), CFIndex,
)


def core_foundation() -> NativeLibrary:
    return NativeLibrary(
        "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation",
        platform="darwin",
    )


def core_graphics() -> NativeLibrary:
    return NativeLibrary(
        "/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics",
        platform="darwin",
    )
