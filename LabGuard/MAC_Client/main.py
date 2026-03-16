"""
main.py — Application entry point and orchestrator.
Manages thread lifecycles, signal handling, and the main macOS run loop.
"""
import signal
import socket
import threading
import time

from Foundation import NSAutoreleasePool, NSRunLoop, NSDate, NSDefaultRunLoopMode

from config import logger, HEARTBEAT_SECS, SHUTDOWN_PORT, SHUTDOWN_PASSWORD, log_listener
from telemetry import sender_thread, make_anomaly, enqueue_anomaly, stop_telemetry
from snapshot import send_initial_status

from monitor_devices import (
    setup_hid_monitoring,
    setup_usb_monitoring,
    setup_bluetooth_monitoring,
    setup_display_monitoring,
)
from monitor_system import (
    setup_network_monitoring,
    setup_screen_lock_monitoring,
    setup_power_monitoring,
)
from ffi_bindings import _cf  # Needed to stop the C-level run loop on exit

# Controls the main run-loop — cleared by _graceful_exit
_running = threading.Event()
_running.set()


# ─────────────────────────────────────────────────────────────────────────────
# Background Threads (Non-blocking tasks)
# ─────────────────────────────────────────────────────────────────────────────

def _heartbeat_thread() -> None:
    """Periodically sends a heartbeat event to the server."""
    while _running.is_set():
        time.sleep(HEARTBEAT_SECS)
        if _running.is_set():
            enqueue_anomaly(make_anomaly("Heartbeat", "", "Heartbeat"))


def _shutdown_listener_thread() -> None:
    """Listens on a specific port for a secure shutdown command."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("0.0.0.0", SHUTDOWN_PORT))
        s.listen(1)
        logger.info("Shutdown listener running on port %d", SHUTDOWN_PORT)

        while _running.is_set():
            try:
                conn, _ = s.accept()
                with conn:
                    data = conn.recv(1024).decode("utf-8").strip()
                    parts = data.split()
                    if parts[:1] == ["shutdown"] and len(parts) == 2:
                        if parts[1] == SHUTDOWN_PASSWORD:
                            logger.info("Shutdown command accepted")
                            _graceful_exit()
                            break
                        else:
                            conn.sendall(b"Incorrect password")
                    else:
                        conn.sendall(b"Invalid command")
            except Exception as exc:
                if _running.is_set():
                    logger.error("Shutdown listener error: %s", exc)


# ─────────────────────────────────────────────────────────────────────────────
# Lifecycle Management
# ─────────────────────────────────────────────────────────────────────────────

def _graceful_exit(*_) -> None:
    """Cleans up threads, queues, and stops the main run loop safely."""
    logger.info("Shutting down...")
    enqueue_anomaly(make_anomaly("System", "", "System Shutting Down"))
    time.sleep(1)  # Brief window to let the final message flush

    _running.clear()  # Stop heartbeat and main loop
    stop_telemetry()  # Poison pill for the sender thread

    try:
        log_listener.stop()
    except Exception:
        pass

    # Stop the underlying CFRunLoop which breaks runMode_beforeDate_ iteration
    _cf.CFRunLoopStop(_cf.CFRunLoopGetMain())


# ─────────────────────────────────────────────────────────────────────────────
# Application Entry Point
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    # 1. Setup Signal Handlers (Ctrl+C or kill commands)
    signal.signal(signal.SIGINT, _graceful_exit)
    signal.signal(signal.SIGTERM, _graceful_exit)

    # 2. NSAutoreleasePool for ObjC memory management on the main thread
    pool = NSAutoreleasePool.alloc().init()

    # 3. Start Background Threads
    threading.Thread(target=sender_thread, daemon=True, name="sender").start()
    threading.Thread(target=_heartbeat_thread, daemon=True, name="heartbeat").start()
    threading.Thread(target=_shutdown_listener_thread, daemon=True, name="shutdown").start()

    # 4. Gather Initial Blocking Snapshot
    send_initial_status()

    # 5. Arm Event Listeners (Zero-polling hardware monitors)
    setup_hid_monitoring()  # Keyboards, mice (USB + BT Classic + BLE)
    setup_usb_monitoring()  # USB storage, cameras, audio interfaces
    setup_bluetooth_monitoring()  # Classic BT audio/speakers
    setup_display_monitoring()  # Displays / GPU
    setup_network_monitoring()  # Ethernet / Wi-Fi
    setup_screen_lock_monitoring()  # Screen lock / Screensaver
    setup_power_monitoring()  # Sleep / Wake

    logger.info("All monitors armed. Entering run loop — zero polling.")

    # 6. Main Run Loop
    # Processes events for up to 0.5s or until CFRunLoopStop is called.
    while _running.is_set():
        NSRunLoop.mainRunLoop().runMode_beforeDate_(
            NSDefaultRunLoopMode,
            NSDate.dateWithTimeIntervalSinceNow_(0.5)
        )

    # Clean up ObjC memory pool
    del pool
    logger.info("Run loop exited — shutdown complete.")


if __name__ == "__main__":
    main()