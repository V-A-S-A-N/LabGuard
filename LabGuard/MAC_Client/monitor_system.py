"""
monitor_system.py — System environment listeners (Network, Screen Lock, Power).
"""
from typing import Optional
import objc
from Foundation import NSObject, NSDistributedNotificationCenter
from AppKit import NSWorkspace, NSWorkspaceWillSleepNotification, NSWorkspaceDidWakeNotification

from config import logger
from telemetry import make_anomaly, enqueue_anomaly, debounce
from ffi_bindings import (
    _cf, _sc, _kCFRunLoopDefaultMode, _SCCallback, _cfstr, _cf_array_strings, _make_cf_string_array
)

_gc_roots = []


# ─────────────────────────────────────────────────────────────────────────────
# Network Monitor
# ─────────────────────────────────────────────────────────────────────────────

def _network_callback(store_ref: int, changed_keys_ref: int, info: int) -> None:
    keys = _cf_array_strings(changed_keys_ref)
    for key in keys:
        iface_name = "Ethernet" if "en0" in key else "WiFi"
        iface_id = "en0" if "en0" in key else "en1"

        key_cf = _cfstr(key)
        val = _sc.SCDynamicStoreCopyValue(store_ref, key_cf)
        _cf.CFRelease(key_cf)

        connected = bool(val)
        if val: _cf.CFRelease(val)

        event = f"{iface_name} {'Link Up' if connected else 'Link Down'}" if "Link" in key else f"{iface_name} {'IP Assigned' if connected else 'IP Removed'}"

        if not debounce(f"Network:{iface_id}:{event}"):
            enqueue_anomaly(make_anomaly(iface_name, iface_id, f"Anomaly {event}"))
            logger.info("Network: %s", event)


_net_cb = _SCCallback(_network_callback)
_gc_roots.append(_net_cb)


def setup_network_monitoring() -> None:
    name_cf = _cfstr("HardwareMonitor")
    store = _sc.SCDynamicStoreCreate(None, name_cf, _net_cb, None)
    _cf.CFRelease(name_cf)

    keys_arr = _make_cf_string_array([
        "State:/Network/Interface/en0/Link", "State:/Network/Interface/en0/IPv4",
        "State:/Network/Interface/en1/Link", "State:/Network/Interface/en1/IPv4",
    ])
    _sc.SCDynamicStoreSetNotificationKeys(store, keys_arr, None)
    _cf.CFRelease(keys_arr)

    source = _sc.SCDynamicStoreCreateRunLoopSource(None, store, 0)
    if source:
        _cf.CFRunLoopAddSource(_cf.CFRunLoopGetMain(), source, _kCFRunLoopDefaultMode)
        _gc_roots.extend([store, source])
        logger.info("Network monitoring armed")


# ─────────────────────────────────────────────────────────────────────────────
# Screen Lock Monitor
# ─────────────────────────────────────────────────────────────────────────────

class _ScreenObserver(NSObject):
    def onLocked_(self, _n):
        if not debounce("Screen:Locked"):
            enqueue_anomaly(make_anomaly("Screen", "", "Anomaly Screen Locked"))

    def onUnlocked_(self, _n):
        if not debounce("Screen:Unlocked"):
            enqueue_anomaly(make_anomaly("Screen", "", "Anomaly Screen Unlocked"))

    def onSS_(self, _n):
        if not debounce("Screen:Screensaver"):
            enqueue_anomaly(make_anomaly("Screen", "", "Anomaly Screensaver Started"))


_screen_obs: Optional[_ScreenObserver] = None


def setup_screen_lock_monitoring() -> None:
    global _screen_obs
    _screen_obs = _ScreenObserver.alloc().init()
    dnc = NSDistributedNotificationCenter.defaultCenter()

    for notif, method in [("com.apple.screenIsLocked", _screen_obs.onLocked_),
                          ("com.apple.screenIsUnlocked", _screen_obs.onUnlocked_),
                          ("com.apple.screensaver.didstart", _screen_obs.onSS_)]:
        dnc.addObserver_selector_name_object_(_screen_obs, objc.selector(method, signature=b"v@:@"), notif, None)
    logger.info("Screen lock monitoring armed")


# ─────────────────────────────────────────────────────────────────────────────
# Power Monitor
# ─────────────────────────────────────────────────────────────────────────────

class _PowerObserver(NSObject):
    def willSleep_(self, _n):
        if not debounce("Power:Sleep"):
            enqueue_anomaly(make_anomaly("System Power", "", "Anomaly System Going to Sleep"))

    def didWake_(self, _n):
        if not debounce("Power:Wake"):
            enqueue_anomaly(make_anomaly("System Power", "", "Anomaly System Woke Up"))


_power_obs: Optional[_PowerObserver] = None


def setup_power_monitoring() -> None:
    global _power_obs
    _power_obs = _PowerObserver.alloc().init()
    nc = NSWorkspace.sharedWorkspace().notificationCenter()
    nc.addObserver_selector_name_object_(_power_obs, objc.selector(_power_obs.willSleep_, signature=b"v@:@"),
                                         NSWorkspaceWillSleepNotification, None)
    nc.addObserver_selector_name_object_(_power_obs, objc.selector(_power_obs.didWake_, signature=b"v@:@"),
                                         NSWorkspaceDidWakeNotification, None)
    logger.info("Sleep/wake monitoring armed")