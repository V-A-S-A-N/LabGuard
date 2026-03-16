"""
snapshot.py — Gathers the initial blocking snapshot of the system state.
"""
import json
import subprocess
from typing import Dict, List

from config import logger
from telemetry import make_anomaly, enqueue_anomaly


def _get_initial_status() -> Dict[str, str]:
    status = {
        "HID Devices": "None",
        "USB Devices": "None",
        "Bluetooth": "None",
        "GPU": "Unknown",
        "Displays": "None",
        "Ethernet": "Disconnected",
        "WiFi": "Disconnected",
    }

    # USB and Bluetooth device lists via system_profiler
    for dtype, key in [("SPUSBDataType", "USB Devices"),
                       ("SPBluetoothDataType", "Bluetooth")]:
        try:
            raw = subprocess.run(
                ["system_profiler", dtype, "-json"],
                capture_output=True, timeout=10
            )
            data = json.loads(raw.stdout)
            items = data.get(dtype, [])
            names: List[str] = []

            # FIX [16]: _walk captures `names` via default argument to avoid
            # closure-over-loop-variable bug when called across iterations.
            def _walk(nodes: list, _names: list = names) -> None:
                for n in nodes:
                    n_name = n.get("_name", "")
                    low = n_name.lower()
                    if "host_controller" in low or "hub" in low:
                        _walk(n.get("_items", []), _names)
                    else:
                        _names.append(n_name)
                        _walk(n.get("_items", []), _names)

            _walk(items)
            status[key] = ", ".join(names) if names else "None"
        except Exception as exc:
            logger.warning("%s snapshot failed: %s", dtype, exc)

    # GPU and displays
    try:
        raw = subprocess.run(
            ["system_profiler", "SPDisplaysDataType", "-json"],
            capture_output=True, timeout=10
        )
        data = json.loads(raw.stdout)
        gpus = data.get("SPDisplaysDataType", [])

        gpu_names = [g.get("sppci_model", "Unknown GPU") for g in gpus]
        status["GPU"] = ", ".join(gpu_names) if gpu_names else "None"

        displays = []
        for g in gpus:
            for d in g.get("spdisplays_ndrvs", []):
                conn = d.get("spdisplays_connection_type", "unknown port")
                displays.append(f"{d.get('_name', 'Display')} ({conn})")
        status["Displays"] = ", ".join(displays) if displays else "None"
    except Exception as exc:
        logger.warning("Display snapshot failed: %s", exc)

    # Ethernet
    try:
        out = subprocess.run(["ifconfig", "en0"], capture_output=True, timeout=5)
        if b"status: active" in out.stdout:
            status["Ethernet"] = "Connected"
    except Exception:
        pass

    # Wi-Fi
    try:
        airport = (
            "/System/Library/PrivateFrameworks/Apple80211.framework"
            "/Versions/Current/Resources/airport"
        )
        out = subprocess.run([airport, "-I"], capture_output=True, timeout=5)
        if b"SSID" in out.stdout:
            status["WiFi"] = "Connected"
    except Exception:
        pass

    return status


def send_initial_status() -> None:
    """Gathers initial hardware state and queues it for telemetry."""
    snap = _get_initial_status()

    enqueue_anomaly(make_anomaly(
        device_name="Initial Status",
        device_id="",
        event="Initial Status",
        StatusDetails=snap,
    ))

    logger.info("Initial status snapshot completed: %s", snap)