"""
monitor_devices.py — Physical hardware listeners (USB, HID, Bluetooth, Displays).
"""
import ctypes
from typing import Optional

import objc
from Foundation import NSObject
from IOBluetooth import IOBluetoothDevice
import Quartz

from config import logger
from telemetry import make_anomaly, enqueue_anomaly, debounce
from ffi_bindings import (
    _iokit, _cf, _vp,
    _kIOMasterPortDefault, _kCFRunLoopDefaultMode,
    _kIOFirstMatch, _kIOTerminated, _KERN_SUCCESS,
    _IOMatchingCallback, _io_iterator_t,
    _cfstr_to_py, _cf_dict_str, _cf_dict_int
)

_gc_roots = []


def _register_iokit_notification(service_class: bytes, notif_type: bytes, drain_fn, label: str) -> None:
    matching = _iokit.IOServiceMatching(service_class)
    if not matching:
        return

    port = _iokit.IONotificationPortCreate(_kIOMasterPortDefault)
    source = _iokit.IONotificationPortGetRunLoopSource(port)
    _cf.CFRunLoopAddSource(_cf.CFRunLoopGetMain(), source, _kCFRunLoopDefaultMode)

    iterator = _io_iterator_t(0)

    def _make_cb(lbl=label, dfn=drain_fn) -> _IOMatchingCallback:
        def _cb(refcon, it):
            dfn(it, lbl)

        return _IOMatchingCallback(_cb)

    cb = _make_cb()
    _gc_roots.append(cb)

    ret = _iokit.IOServiceAddMatchingNotification(
        port, notif_type, matching, cb, None, ctypes.byref(iterator)
    )
    if ret == _KERN_SUCCESS:
        drain_fn(iterator.value, f"startup-{label}")
        _gc_roots.extend([port, source, iterator])


# ─────────────────────────────────────────────────────────────────────────────
# HID & USB Monitors
# ─────────────────────────────────────────────────────────────────────────────

def _drain_hardware(iterator: int, label: str, default_transport: str) -> None:
    is_startup = label.startswith("startup")

    while True:
        service = _iokit.IOIteratorNext(iterator)
        if not service:
            break
        try:
            # If this is just the startup drain to arm the listener, silently process it.
            # snapshot.py handles aggregating the initial baseline data.
            if is_startup:
                continue

            name_buf = ctypes.create_string_buffer(128)
            _iokit.IORegistryEntryGetName(service, name_buf)
            fallback = name_buf.value.decode("utf-8", errors="replace")

            props = _vp(0)
            ret = _iokit.IORegistryEntryCreateCFProperties(service, ctypes.byref(props), None, 0)

            product, device_id = fallback, ""
            transport = default_transport

            if ret == _KERN_SUCCESS and props.value:
                product = (_cf_dict_str(props.value, "kUSBProductString") or
                           _cf_dict_str(props.value, "Product") or fallback)
                transport = _cf_dict_str(props.value, "Transport") or default_transport

                vid = _cf_dict_int(props.value, "idVendor") or _cf_dict_int(props.value, "VendorID")
                pid = _cf_dict_int(props.value, "idProduct") or _cf_dict_int(props.value, "ProductID")
                if vid and pid:
                    device_id = f"VID:{vid:#06x} PID:{pid:#06x}"
                _cf.CFRelease(props.value)

            # GHOST FILTER: Ignore internal logic board components with no hardware ID
            if not device_id:
                continue

            dedup_key = f"{label}:{product}:{device_id}"
            if not debounce(dedup_key):
                enqueue_anomaly(make_anomaly(product, device_id, f"Anomaly {label}", Transport=transport))
                logger.info("Hardware %s: %s [%s]", label, product, transport)

        except Exception as exc:
            logger.error("Hardware drain error: %s", exc)
        finally:
            _iokit.IOObjectRelease(service)


def setup_hid_monitoring() -> None:
    for n_type, lbl in [(_kIOFirstMatch, "Device Connected"), (_kIOTerminated, "Device Removal")]:
        _register_iokit_notification(b"IOHIDDevice", n_type, lambda it, l: _drain_hardware(it, l, "Unknown"), lbl)
    logger.info("HID monitoring armed")


def setup_usb_monitoring() -> None:
    for n_type, lbl in [(_kIOFirstMatch, "Device Connected"), (_kIOTerminated, "Device Removal")]:
        _register_iokit_notification(b"IOUSBHostDevice", n_type, lambda it, l: _drain_hardware(it, l, "USB"), lbl)
    logger.info("USB monitoring armed")


# ─────────────────────────────────────────────────────────────────────────────
# Bluetooth Monitors
# ─────────────────────────────────────────────────────────────────────────────

class _BtDelegate(NSObject):
    def btConnected_device_(self, notification, device):
        self._handle_bt(device, "Device Connected")

    def btDisconnected_device_(self, notification, device):
        self._handle_bt(device, "Device Removal")

    def _handle_bt(self, device, label):
        try:
            name = device.nameOrAddress() if device else "Unknown"
            addr = device.addressString() if device else ""

            # GHOST FILTER: Ignore empty MAC_Client addresses
            if not addr: return

            if not debounce(f"BT:{label}:{name}:{addr}"):
                enqueue_anomaly(make_anomaly(name, addr, f"Anomaly {label}", Transport="Bluetooth"))
                logger.info("Classic BT %s: %s", label, name)

            if label == "Device Connected":
                device.registerForDisconnectNotification_selector_(self, objc.selector(self.btDisconnected_device_,
                                                                                       signature=b"v@:@@"))
        except Exception as exc:
            logger.error("BT error: %s", exc)


_bt_delegate: Optional[_BtDelegate] = None


def setup_bluetooth_monitoring() -> None:
    global _bt_delegate
    _bt_delegate = _BtDelegate.alloc().init()
    IOBluetoothDevice.registerForConnectNotifications_selector_(_bt_delegate,
                                                                objc.selector(_bt_delegate.btConnected_device_,
                                                                              signature=b"v@:@@"))
    logger.info("Classic BT monitoring armed")


# ─────────────────────────────────────────────────────────────────────────────
# Display Monitors
# ─────────────────────────────────────────────────────────────────────────────

def _display_callback(display_id, flags, userinfo) -> None:
    events = {
        Quartz.kCGDisplayAddFlag: "Display Connected",
        Quartz.kCGDisplayRemoveFlag: "Display Removed",
        Quartz.kCGDisplaySetModeFlag: "Display Mode Changed"
    }

    for flag, name in events.items():
        if flags & flag:
            if not debounce(f"Display:{display_id}:{name}"):
                enqueue_anomaly(make_anomaly("Display", str(display_id), f"Anomaly {name}"))
                logger.info("Display: %s (id=%s)", name, display_id)


def setup_display_monitoring() -> None:
    Quartz.CGDisplayRegisterReconfigurationCallback(_display_callback, None)
    logger.info("Display monitoring armed")