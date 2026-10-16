"""C declarations for the documented 64-bit macOS ABI, without native calls."""

import ctypes as c

from .binding import FunctionSpec, NativeLibrary


CGFloat = c.c_double
CGDirectDisplayID = c.c_uint32
CGError = c.c_int32
Boolean = c.c_uint8
boolean_t = c.c_uint32
CFIndex = c.c_int64
CFTypeID = c.c_uint64
CFTypeRef = c.c_void_p
CFStringRef = c.c_void_p
CFStringEncoding = c.c_uint32
CFNumberType = CFIndex
CGWindowID = c.c_uint32
CGWindowListOption = c.c_uint32
UTF8 = 0x08000100
AXError = c.c_int32
AXValueType = c.c_uint32
pid_t = c.c_int32


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

CF_DICTIONARY_CREATE = FunctionSpec(
    "CFDictionaryCreate",
    (CFTypeRef, c.POINTER(CFTypeRef), c.POINTER(CFTypeRef), CFIndex, c.c_void_p, c.c_void_p),
    CFTypeRef,
)
CF_DICTIONARY_VALUE = FunctionSpec("CFDictionaryGetValue", (CFTypeRef, CFTypeRef), CFTypeRef)
CF_ARRAY_CREATE = FunctionSpec(
    "CFArrayCreate", (CFTypeRef, c.POINTER(CFTypeRef), CFIndex, c.c_void_p), CFTypeRef,
)
CF_ARRAY_COUNT = FunctionSpec("CFArrayGetCount", (CFTypeRef,), CFIndex)
CF_ARRAY_VALUE = FunctionSpec("CFArrayGetValueAtIndex", (CFTypeRef, CFIndex), CFTypeRef)
CF_TYPE_ID = FunctionSpec("CFGetTypeID", (CFTypeRef,), CFTypeID)
CF_ARRAY_TYPE = FunctionSpec("CFArrayGetTypeID", (), CFTypeID)
CF_DICTIONARY_TYPE = FunctionSpec("CFDictionaryGetTypeID", (), CFTypeID)
CF_NUMBER_TYPE = FunctionSpec("CFNumberGetTypeID", (), CFTypeID)
CF_STRING_TYPE = FunctionSpec("CFStringGetTypeID", (), CFTypeID)
CF_BOOLEAN_TYPE = FunctionSpec("CFBooleanGetTypeID", (), CFTypeID)
CF_NUMBER_VALUE = FunctionSpec("CFNumberGetValue", (CFTypeRef, CFNumberType, c.c_void_p), Boolean)
CF_BOOLEAN_VALUE = FunctionSpec("CFBooleanGetValue", (CFTypeRef,), Boolean)
AX_TRUSTED = FunctionSpec("AXIsProcessTrusted", (), Boolean)
AX_REQUEST = FunctionSpec("AXIsProcessTrustedWithOptions", (CFTypeRef,), Boolean)
AX_APPLICATION = FunctionSpec("AXUIElementCreateApplication", (pid_t,), CFTypeRef)
AX_ELEMENT_TYPE = FunctionSpec("AXUIElementGetTypeID", (), CFTypeID)
AX_PID = FunctionSpec("AXUIElementGetPid", (CFTypeRef, c.POINTER(pid_t)), AXError)
AX_COPY = FunctionSpec("AXUIElementCopyAttributeValue", (CFTypeRef, CFStringRef, c.POINTER(CFTypeRef)), AXError)
AX_SETTABLE = FunctionSpec("AXUIElementIsAttributeSettable", (CFTypeRef, CFStringRef, c.POINTER(Boolean)), AXError)
AX_SET = FunctionSpec("AXUIElementSetAttributeValue", (CFTypeRef, CFStringRef, CFTypeRef), AXError)
AX_ACTIONS = FunctionSpec("AXUIElementCopyActionNames", (CFTypeRef, c.POINTER(CFTypeRef)), AXError)
AX_ACTION = FunctionSpec("AXUIElementPerformAction", (CFTypeRef, CFStringRef), AXError)
AX_TIMEOUT = FunctionSpec("AXUIElementSetMessagingTimeout", (CFTypeRef, c.c_float), AXError)
AX_VALUE_TYPE_ID = FunctionSpec("AXValueGetTypeID", (), CFTypeID)
AX_VALUE_TYPE = FunctionSpec("AXValueGetType", (CFTypeRef,), AXValueType)
AX_VALUE_CREATE = FunctionSpec("AXValueCreate", (AXValueType, c.c_void_p), CFTypeRef)
AX_VALUE_GET = FunctionSpec("AXValueGetValue", (CFTypeRef, AXValueType, c.c_void_p), Boolean)
CF_EQUAL = FunctionSpec("CFEqual", (CFTypeRef, CFTypeRef), Boolean)
CG_PREFLIGHT_LISTEN = FunctionSpec("CGPreflightListenEventAccess", (), c.c_bool)
CG_PREFLIGHT_POST = FunctionSpec("CGPreflightPostEventAccess", (), c.c_bool)
CG_PREFLIGHT_CAPTURE = FunctionSpec("CGPreflightScreenCaptureAccess", (), c.c_bool)
CG_REQUEST_LISTEN = FunctionSpec("CGRequestListenEventAccess", (), c.c_bool)
CG_REQUEST_POST = FunctionSpec("CGRequestPostEventAccess", (), c.c_bool)
CG_REQUEST_CAPTURE = FunctionSpec("CGRequestScreenCaptureAccess", (), c.c_bool)

CG_ACTIVE_DISPLAYS = FunctionSpec(
    "CGGetActiveDisplayList", (c.c_uint32, c.POINTER(CGDirectDisplayID), c.POINTER(c.c_uint32)), CGError,
)
CG_DISPLAY_BOUNDS = FunctionSpec("CGDisplayBounds", (CGDirectDisplayID,), CGRect)
CG_DISPLAY_ACTIVE = FunctionSpec("CGDisplayIsActive", (CGDirectDisplayID,), boolean_t)
CG_DISPLAY_ONLINE = FunctionSpec("CGDisplayIsOnline", (CGDirectDisplayID,), boolean_t)
CG_DISPLAY_MAIN = FunctionSpec("CGDisplayIsMain", (CGDirectDisplayID,), boolean_t)
CG_DISPLAY_ROTATION = FunctionSpec("CGDisplayRotation", (CGDirectDisplayID,), c.c_double)
CG_DISPLAY_MIRROR = FunctionSpec("CGDisplayMirrorsDisplay", (CGDirectDisplayID,), CGDirectDisplayID)
CG_DISPLAY_MODE = FunctionSpec("CGDisplayCopyDisplayMode", (CGDirectDisplayID,), CFTypeRef)
CG_MODE_RELEASE = FunctionSpec("CGDisplayModeRelease", (CFTypeRef,), None)
CG_MODE_WIDTH = FunctionSpec("CGDisplayModeGetWidth", (CFTypeRef,), c.c_size_t)
CG_MODE_HEIGHT = FunctionSpec("CGDisplayModeGetHeight", (CFTypeRef,), c.c_size_t)
CG_MODE_PIXEL_WIDTH = FunctionSpec("CGDisplayModeGetPixelWidth", (CFTypeRef,), c.c_size_t)
CG_MODE_PIXEL_HEIGHT = FunctionSpec("CGDisplayModeGetPixelHeight", (CFTypeRef,), c.c_size_t)
CG_WINDOW_LIST = FunctionSpec("CGWindowListCopyWindowInfo", (CGWindowListOption, CGWindowID), CFTypeRef)
CG_WINDOW_DESCRIPTIONS = FunctionSpec("CGWindowListCreateDescriptionFromArray", (CFTypeRef,), CFTypeRef)
CG_RECT_FROM_DICTIONARY = FunctionSpec(
    "CGRectMakeWithDictionaryRepresentation", (CFTypeRef, c.POINTER(CGRect)), c.c_bool,
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


def application_services() -> NativeLibrary:
    return NativeLibrary(
        "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices",
        platform="darwin",
    )
