"""
ffi_bindings.py — ctypes bindings for macOS IOKit, CoreFoundation, and SystemConfiguration.
"""
import ctypes
import ctypes.util
import sys
from typing import Optional, List

# ─────────────────────────────────────────────────────────────────────────────
# Load C frameworks via ctypes
# ─────────────────────────────────────────────────────────────────────────────

_IOKIT_PATH = "/System/Library/Frameworks/IOKit.framework/IOKit"
_CF_PATH    = "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
_SC_PATH    = "/System/Library/Frameworks/SystemConfiguration.framework/SystemConfiguration"

try:
    _iokit = ctypes.CDLL(_IOKIT_PATH)
    _cf    = ctypes.CDLL(_CF_PATH)
    _sc    = ctypes.CDLL(_SC_PATH)
except OSError as _load_err:
    sys.exit("[FATAL] Cannot load system framework: {}".format(_load_err))

# ── C type aliases ────────────────────────────────────────────────────────────
_vp  = ctypes.c_void_p
_u32 = ctypes.c_uint32
_i32 = ctypes.c_int32
_i   = ctypes.c_int
_b   = ctypes.c_bool
_l   = ctypes.c_long
_u8p = ctypes.c_char_p

# IOKit types
_io_object_t    = _u32
_io_iterator_t  = _u32
_kern_return_t  = _i
_NotifyPort     = _vp
_RunLoopSource  = _vp

# IOKit notification type constants
_kIOMasterPortDefault       = 0
_kIOFirstMatch              = b"IOServiceFirstMatch"
_kIOTerminated              = b"IOServiceTerminate"
_KERN_SUCCESS               = 0

# ── CFArrayCallBacks struct (needed for CFArrayCreate) ────────────────────────
# Layout: version(8) + 4 × function-pointer(8) = 40 bytes on 64-bit macOS
class _CFArrayCallBacks(ctypes.Structure):
    _fields_ = [
        ("version",         ctypes.c_long),
        ("retain",          _vp),
        ("release",         _vp),
        ("copyDescription", _vp),
        ("equal",           _vp),
    ]

# kCFTypeArrayCallBacks is a global struct exported from CoreFoundation
_kCFTypeArrayCallBacks = _CFArrayCallBacks.in_dll(_cf, "kCFTypeArrayCallBacks")

# ── kCFRunLoopDefaultMode ─────────────────────────────────────────────────────
# kCFRunLoopDefaultMode is a global CFStringRef* in CoreFoundation.
# c_void_p.in_dll gives a ctypes object whose .value is the pointer stored there.
_kCFRunLoopDefaultMode: int = ctypes.c_void_p.in_dll(_cf, "kCFRunLoopDefaultMode").value

# ─────────────────────────────────────────────────────────────────────────────
# CoreFoundation function signatures
# ─────────────────────────────────────────────────────────────────────────────

# Run loop
_cf.CFRunLoopGetMain.restype  = _vp
_cf.CFRunLoopGetMain.argtypes = []

_cf.CFRunLoopAddSource.restype  = None
_cf.CFRunLoopAddSource.argtypes = [_vp, _RunLoopSource, _vp]

_cf.CFRunLoopStop.restype  = None
_cf.CFRunLoopStop.argtypes = [_vp]

# String
_cf.CFStringCreateWithCString.restype  = _vp
_cf.CFStringCreateWithCString.argtypes = [_vp, _u8p, _u32]

_cf.CFStringGetCString.restype  = _b
_cf.CFStringGetCString.argtypes = [_vp, ctypes.c_char_p, _l, _u32]

# Dictionary
_cf.CFDictionaryGetValue.restype  = _vp
_cf.CFDictionaryGetValue.argtypes = [_vp, _vp]

# Type checks
_cf.CFGetTypeID.restype  = ctypes.c_ulong
_cf.CFGetTypeID.argtypes = [_vp]

_cf.CFStringGetTypeID.restype  = ctypes.c_ulong
_cf.CFStringGetTypeID.argtypes = []

_cf.CFNumberGetTypeID.restype  = ctypes.c_ulong
_cf.CFNumberGetTypeID.argtypes = []

_cf.CFNumberGetValue.restype  = _b
_cf.CFNumberGetValue.argtypes = [_vp, _i, _vp]

# Array
_cf.CFArrayCreate.restype  = _vp
_cf.CFArrayCreate.argtypes = [_vp, ctypes.POINTER(_vp), _l, ctypes.c_void_p]

_cf.CFArrayGetCount.restype  = _l
_cf.CFArrayGetCount.argtypes = [_vp]

_cf.CFArrayGetValueAtIndex.restype  = _vp
_cf.CFArrayGetValueAtIndex.argtypes = [_vp, _l]

# Release
_cf.CFRelease.restype  = None
_cf.CFRelease.argtypes = [_vp]

_kCFStringEncodingUTF8 = 0x08000100
_kCFNumberSInt32Type   = 3

# ─────────────────────────────────────────────────────────────────────────────
# IOKit function signatures
# ─────────────────────────────────────────────────────────────────────────────

_iokit.IONotificationPortCreate.restype  = _NotifyPort
_iokit.IONotificationPortCreate.argtypes = [_u32]

_iokit.IONotificationPortGetRunLoopSource.restype  = _RunLoopSource
_iokit.IONotificationPortGetRunLoopSource.argtypes = [_NotifyPort]

_iokit.IOServiceMatching.restype  = _vp   # CFMutableDictionaryRef
_iokit.IOServiceMatching.argtypes = [_u8p]

# Callback: void cb(void* refcon, io_iterator_t iterator)
_IOMatchingCallback = ctypes.CFUNCTYPE(None, _vp, _io_iterator_t)

_iokit.IOServiceAddMatchingNotification.restype  = _kern_return_t
_iokit.IOServiceAddMatchingNotification.argtypes = [
    _NotifyPort,                      # notifyPort
    _u8p,                             # notificationType
    _vp,                              # matching  (ownership transferred, no CFRelease)
    _IOMatchingCallback,              # callback
    _vp,                              # refCon
    ctypes.POINTER(_io_iterator_t),   # notification (out)
]

_iokit.IOIteratorNext.restype  = _io_object_t
_iokit.IOIteratorNext.argtypes = [_io_iterator_t]

_iokit.IOObjectRelease.restype  = _kern_return_t
_iokit.IOObjectRelease.argtypes = [_io_object_t]

_iokit.IORegistryEntryGetName.restype  = _kern_return_t
_iokit.IORegistryEntryGetName.argtypes = [_io_object_t, ctypes.c_char_p]

_iokit.IORegistryEntryCreateCFProperties.restype  = _kern_return_t
_iokit.IORegistryEntryCreateCFProperties.argtypes = [
    _io_object_t,
    ctypes.POINTER(_vp),   # properties (out) — caller must CFRelease
    _vp,                   # allocator
    _u32,                  # options
]

# ─────────────────────────────────────────────────────────────────────────────
# SystemConfiguration function signatures
# ─────────────────────────────────────────────────────────────────────────────

# SCDynamicStore callback: void cb(SCDynamicStoreRef, CFArrayRef changedKeys, void* info)
_SCCallback = ctypes.CFUNCTYPE(None, _vp, _vp, _vp)

_sc.SCDynamicStoreCreate.restype  = _vp
_sc.SCDynamicStoreCreate.argtypes = [
    _vp,          # allocator
    _vp,          # name (CFStringRef)
    _SCCallback,  # callout
    _vp,          # context (NULL = no user info)
]

_sc.SCDynamicStoreSetNotificationKeys.restype  = _b
_sc.SCDynamicStoreSetNotificationKeys.argtypes = [
    _vp,   # store
    _vp,   # keys (CFArrayRef or NULL)
    _vp,   # patterns (CFArrayRef or NULL)
]

_sc.SCDynamicStoreCreateRunLoopSource.restype  = _RunLoopSource
_sc.SCDynamicStoreCreateRunLoopSource.argtypes = [
    _vp,   # allocator
    _vp,   # store
    _l,    # order
]

_sc.SCDynamicStoreCopyValue.restype  = _vp   # CFPropertyListRef — caller must CFRelease
_sc.SCDynamicStoreCopyValue.argtypes = [_vp, _vp]

# ─────────────────────────────────────────────────────────────────────────────
# CoreFoundation helpers
# ─────────────────────────────────────────────────────────────────────────────

def _cfstr(py_str: str) -> int:
    """Create a CFStringRef from a Python str. Caller MUST _cf.CFRelease() it."""
    return _cf.CFStringCreateWithCString(None, py_str.encode("utf-8"), _kCFStringEncodingUTF8)

def _cfstr_to_py(cf_ptr: int) -> str:
    """Read a CFStringRef into a Python str. Does NOT release the pointer."""
    if not cf_ptr:
        return ""
    buf = ctypes.create_string_buffer(512)
    if _cf.CFStringGetCString(cf_ptr, buf, 512, _kCFStringEncodingUTF8):
        return buf.value.decode("utf-8", errors="replace")
    return ""

def _cf_dict_str(cf_dict: int, key: str) -> str:
    """Read a string value from a CFDictionaryRef by key."""
    k = _cfstr(key)
    v = _cf.CFDictionaryGetValue(cf_dict, k)
    _cf.CFRelease(k)
    if v and _cf.CFGetTypeID(v) == _cf.CFStringGetTypeID():
        return _cfstr_to_py(v)
    return ""

def _cf_dict_int(cf_dict: int, key: str) -> Optional[int]:
    """Read an integer value from a CFDictionaryRef by key."""
    k = _cfstr(key)
    v = _cf.CFDictionaryGetValue(cf_dict, k)
    _cf.CFRelease(k)
    if v and _cf.CFGetTypeID(v) == _cf.CFNumberGetTypeID():
        out = _i32(0)
        _cf.CFNumberGetValue(v, _kCFNumberSInt32Type, ctypes.byref(out))
        return out.value
    return None

def _cf_array_strings(cf_array: int) -> List[str]:
    """Convert a CFArrayRef of CFStringRefs to a Python list of strings."""
    if not cf_array:
        return []
    result = []
    for i in range(_cf.CFArrayGetCount(cf_array)):
        v = _cf.CFArrayGetValueAtIndex(cf_array, i)
        if v:
            result.append(_cfstr_to_py(v))
    return result

def _make_cf_string_array(strings: List[str]) -> int:
    """
    Build a CFArrayRef from a list of Python strings.
    Caller MUST _cf.CFRelease() the returned value.
    """
    refs = [_cfstr(s) for s in strings]
    arr_type = _vp * len(refs)
    c_refs = arr_type(*refs)
    arr = _cf.CFArrayCreate(
        None, c_refs, len(refs),
        ctypes.byref(_kCFTypeArrayCallBacks)
    )
    for r in refs:
        _cf.CFRelease(r)
    return arr