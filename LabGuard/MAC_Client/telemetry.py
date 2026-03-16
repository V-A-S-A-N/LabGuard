"""
telemetry.py — Handles outbound queues, network I/O, and CSV logging.
"""
import csv
import json
import os
import queue
import socket
import threading
import time

from config import logger, SYSTEM_ID, SERVER_IP, SERVER_PORT, CSV_FILENAME

# ── State ────────────────────────────────────────────────────────────────────
_send_queue = queue.Queue()
_csv_lock = threading.Lock()


# ── Public API ───────────────────────────────────────────────────────────────

def make_anomaly(device_name: str, device_id: str, event: str, **extra: object) -> dict:
    """Builds a standardized anomaly dictionary."""
    a = {
        "SystemID": SYSTEM_ID,
        "TimeGenerated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "DeviceName": device_name,
        "DeviceID": device_id,
        "Event": event,
    }
    a.update(extra)
    return a


def enqueue_anomaly(anomaly: dict) -> None:
    """
    Thread-safe enqueue.
    Safe to call from any ctypes callback or ObjC method on the main run loop.
    """
    _send_queue.put(anomaly)


def stop_telemetry() -> None:
    """Injects a poison pill into the queue to cleanly exit the sender thread."""
    _send_queue.put(None)


def sender_thread() -> None:
    """Background worker: pulls from the queue, sends to server, and saves to CSV."""
    while True:
        item = _send_queue.get()
        if item is None:  # Poison pill caught — exit gracefully
            break

        _send_to_server(item)
        _save_csv(item)


# ── Private Implementation ───────────────────────────────────────────────────

def _send_to_server(anomaly: dict) -> None:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(10.0)  # Explicit float for timeout
            s.connect((SERVER_IP, SERVER_PORT))
            s.sendall(json.dumps(anomaly).encode("utf-8"))
    except Exception as exc:
        logger.error("Send error: %s", exc)


def _save_csv(anomaly: dict) -> None:
    exists = os.path.isfile(CSV_FILENAME)
    try:
        with _csv_lock:
            # Added encoding="utf-8" to prevent crashes on weird device names
            with open(CSV_FILENAME, "a", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                if not exists:
                    w.writerow(["Time", "SystemID", "DeviceName", "DeviceID", "Event"])

                w.writerow([
                    anomaly.get("TimeGenerated"),
                    anomaly.get("SystemID"),
                    anomaly.get("DeviceName"),
                    anomaly.get("DeviceID"),
                    anomaly.get("Event"),
                ])
    except Exception as exc:
        logger.error("CSV error: %s", exc)



_event_cache = {}

def debounce(event_key: str, window: float = 2.0) -> bool:
    """Returns True if the event is a duplicate within the time window."""
    now = time.time()
    if event_key in _event_cache and now - _event_cache[event_key] < window:
        _event_cache[event_key] = now
        return True

    _event_cache[event_key] = now

    # Cleanup old entries to prevent memory leaks over time
    keys_to_delete = [k for k, v in _event_cache.items() if now - v > window * 2]
    for k in keys_to_delete:
        del _event_cache[k]

    return False