import wmi
import pythoncom
import socket
import json
import logging
import logging.handlers
import time
import os
import csv
import threading
import uuid
import sys
import signal
import queue
import re
from collections import Counter

### Logging Setup

log_queue = queue.Queue(-1)
queue_handler = logging.handlers.QueueHandler(log_queue)
file_handler = logging.FileHandler("client.log")
formatter = logging.Formatter("%(asctime)s %(levelname)s: %(message)s")
file_handler.setFormatter(formatter)
listener = logging.handlers.QueueListener(log_queue, file_handler)
listener.start()
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
logger = logging.getLogger()
logger.setLevel(logging.INFO)
logger.addHandler(queue_handler)
logger.addHandler(console_handler)

### Constants

SYSTEM_ID = hex(uuid.getnode())
SERVER_IP = '127.0.0.1'  # Replace with your server's IP address
SERVER_PORT = 5000
CSV_FILENAME = 'anomalies.csv'
SHUTDOWN_PASSWORD = "nick"
SHUTDOWN_PORT = 6000
THROTTLE_INTERVAL = 1  # Seconds to throttle repeated events

### Global Variables (Thread-Safe)

csv_lock = threading.Lock()
last_logged_connection = {}
last_logged_removal = {}
# Global snapshot to hold initial status so that repeated anomalies (e.g., VGA and HDMI) are not logged twice.
initial_status_snapshot = {}

### Helper Functions

def extract_device_key(device_id):
    """Extract a unique key from the device ID."""
    match = re.search(r'(USB\\VID_[0-9A-F]+&PID_[0-9A-F]+)', device_id, re.IGNORECASE)
    return match.group(1) if match else device_id

def send_anomaly(anomaly):
    """Send anomaly data to the server."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(10)
            sock.connect((SERVER_IP, SERVER_PORT))
            sock.sendall(json.dumps(anomaly).encode('utf-8'))
    except Exception as e:
        logging.error(f"Error sending anomaly to server: {e}")

def save_anomaly_csv(anomaly, filename=CSV_FILENAME):
    """Save anomaly data to a CSV file."""
    file_exists = os.path.isfile(filename)
    try:
        with csv_lock:
            with open(filename, mode='a', newline='') as csv_file:
                writer = csv.writer(csv_file)
                if not file_exists:
                    writer.writerow(["Time", "SystemID", "DeviceName", "DeviceID", "Event"])
                writer.writerow([
                    anomaly.get('TimeGenerated'),
                    anomaly.get('SystemID'),
                    anomaly.get('DeviceName'),
                    anomaly.get('DeviceID'),
                    anomaly.get('Event')
                ])
    except Exception as e:
        logging.error(f"Error saving anomaly to CSV: {e}")

def get_active_usb_devices():
    """
    Perform one WMI query to retrieve active USB devices.
    A device is considered active if its Status property (if available) is "OK"
    and its Name does not contain unwanted keywords such as "bluetooth".
    """
    pythoncom.CoInitialize()
    active_devices = []
    try:
        c = wmi.WMI()
        usb_devices = list(c.query("SELECT * FROM Win32_PnPEntity WHERE PNPDeviceID LIKE 'USB%'"))
        for dev in usb_devices:
            if hasattr(dev, "Status") and dev.Status != "OK":
                continue
            device_name = getattr(dev, "Name", "Unknown Device")
            if "bluetooth" in device_name.lower():
                continue
            active_devices.append(dev)
    except Exception as e:
        logging.error("Error retrieving active USB devices: %s", e)
    finally:
        try:
            pythoncom.CoUninitialize()
        except Exception:
            pass
    return active_devices

def get_gpu_status():
    """Retrieve GPU status using Win32_VideoController."""
    status = "Missing"
    pythoncom.CoInitialize()
    try:
        c = wmi.WMI()
        video_controllers = c.Win32_VideoController()
        if video_controllers:
            status = "Present"
    except Exception as e:
        logging.error("Error retrieving GPU status: %s", e)
    finally:
        try:
            pythoncom.CoUninitialize()
        except Exception:
            pass
    return status

def get_ethernet_status():
    """Retrieve Ethernet connection status."""
    status = "Disconnected"
    pythoncom.CoInitialize()
    try:
        c = wmi.WMI()
        adapters = c.Win32_NetworkAdapter()
        for adapter in adapters:
            adapter_name = (adapter.Name or "").lower()
            if "ethernet" in adapter_name or (hasattr(adapter, "AdapterType") and adapter.AdapterType == "Ethernet 802.3"):
                if getattr(adapter, "NetConnectionStatus", None) == 2:
                    status = "Connected"
                    break
    except Exception as e:
        logging.error("Error retrieving Ethernet status: %s", e)
    finally:
        try:
            pythoncom.CoUninitialize()
        except Exception:
            pass
    return status

def get_monitor_status():
    """Retrieve Monitor status using Win32_DesktopMonitor."""
    status = "Missing"
    pythoncom.CoInitialize()
    try:
        c = wmi.WMI()
        monitors = c.Win32_DesktopMonitor()
        if monitors:
            status = "Present"
    except Exception as e:
        logging.error("Error retrieving Monitor status: %s", e)
    finally:
        try:
            pythoncom.CoUninitialize()
        except Exception:
            pass
    return status

def get_vga_status():
    """Check for VGA cable connection using a WMI query with a name filter."""
    status = "Missing"
    pythoncom.CoInitialize()
    try:
        c = wmi.WMI()
        vga_devices = c.query("SELECT * FROM Win32_PnPEntity WHERE Name LIKE '%VGA%'")
        if vga_devices:
            status = "Present"
    except Exception as e:
        logging.error("Error retrieving VGA status: %s", e)
    finally:
        try:
            pythoncom.CoUninitialize()
        except Exception:
            pass
    return status

def get_hdmi_status():
    """Check for HDMI connection using a WMI query with a name filter."""
    status = "Missing"
    pythoncom.CoInitialize()
    try:
        c = wmi.WMI()
        hdmi_devices = c.query("SELECT * FROM Win32_PnPEntity WHERE Name LIKE '%HDMI%'")
        if hdmi_devices:
            status = "Present"
    except Exception as e:
        logging.error("Error retrieving HDMI status: %s", e)
    finally:
        try:
            pythoncom.CoUninitialize()
        except Exception:
            pass
    return status

### Initial Status and Monitoring

def send_initial_status():
    """
    Send a summary of currently connected and active devices (USB, GPU, Ethernet, Monitor, VGA, HDMI) at startup.
    This sends a single initial anomaly.
    """
    global initial_status_snapshot
    # USB Devices
    active_devices = get_active_usb_devices()
    device_names = [getattr(dev, "Name", "Unknown Device") for dev in active_devices]
    counts = Counter(device_names)
    usb_summary = ", ".join(sorted(
        f"{name} ({count})" if count > 1 else name 
        for name, count in counts.items())) if counts else "None"

    # Retrieve statuses for other components
    gpu_status = get_gpu_status()
    ethernet_status = get_ethernet_status()
    monitor_status = get_monitor_status()
    vga_status = get_vga_status()
    hdmi_status = get_hdmi_status()

    # Build a combined status details dictionary
    initial_status = {
        "USB Devices": usb_summary,
        "GPU": gpu_status,
        "Ethernet": ethernet_status,
        "Monitor": monitor_status,
        "VGA": vga_status,
        "HDMI": hdmi_status
    }
    
    # Save initial snapshot for later comparisons
    initial_status_snapshot = initial_status.copy()
    
    anomaly = {
        "SystemID": SYSTEM_ID,
        "TimeGenerated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "DeviceName": "Initial Status",
        "DeviceID": "",
        "Event": "Initial Status",
        "StatusDetails": initial_status
    }
    logging.info(f"Sending initial status: {initial_status}")
    send_anomaly(anomaly)
    save_anomaly_csv(anomaly)

def usb_event_generator(query):
    """Generate USB events using WMI notifications."""
    while True:
        try:
            c = wmi.WMI()
            watcher = c.ExecNotificationQuery(query)
            while True:
                event = watcher.NextEvent()
                yield event
        except Exception as e:
            logging.error(f"Error in WMI event loop: {e}")
            time.sleep(5)

def monitor_usb_events(event_type):
    """Monitor USB device connection or removal events."""
    pythoncom.CoInitialize()
    try:
        query = (f"SELECT * FROM __Instance{event_type}Event WITHIN 2 "
                 f"WHERE TargetInstance ISA 'Win32_PnPEntity' AND TargetInstance.PNPDeviceID LIKE 'USB%'")
        logging.info(f"Starting USB {event_type} monitor with query: {query}")
        for event in usb_event_generator(query):
            try:
                target_instance = event.Properties_("TargetInstance").Value
                device_name = getattr(target_instance, "Name", "Unknown Device")
                device_id = getattr(target_instance, "PNPDeviceID", "Unknown ID")
                device_key = extract_device_key(device_id)
                current_time = time.time()
                last_times = last_logged_removal if event_type == "Deletion" else last_logged_connection
                if current_time - last_times.get(device_key, 0) < THROTTLE_INTERVAL:
                    continue
                last_times[device_key] = current_time
                anomaly = {
                    'SystemID': SYSTEM_ID,
                    'TimeGenerated': time.strftime("%Y-%m-%d %H:%M:%S"),
                    'DeviceName': device_name,
                    'DeviceID': device_id,
                    'Event': f"Anomaly {event_type}"
                }
                logging.info(f"Detected {event_type}: {anomaly}")
                send_anomaly(anomaly)
                save_anomaly_csv(anomaly)
            except Exception as inner_e:
                logging.error(f"Error processing {event_type} event: {inner_e}")
    finally:
        try:
            pythoncom.CoUninitialize()
        except Exception:
            pass

def monitor_system_status():
    """
    Monitor system component status periodically.
    Logs changes in USB, GPU, Ethernet, Monitor, VGA, and HDMI statuses.
    Uses the initial snapshot to avoid logging duplicate events.
    """
    # Initialize status with the snapshot from the initial status
    status = initial_status_snapshot.copy() if initial_status_snapshot else {
        "USB Devices": None,
        "GPU": None,
        "Ethernet": None,
        "Monitor": None,
        "VGA": None,
        "HDMI": None
    }
    while True:
        current_time = time.strftime("%Y-%m-%d %H:%M:%S")
        # USB devices summary
        active_devices = get_active_usb_devices()
        device_names = [getattr(dev, "Name", "Unknown Device") for dev in active_devices]
        counts = Counter(device_names)
        usb_summary = ", ".join(sorted(
            f"{name} ({count})" if count > 1 else name 
            for name, count in counts.items())) if counts else "None"
        
        # Retrieve statuses for other components
        gpu_status = get_gpu_status()
        ethernet_status = get_ethernet_status()
        monitor_status = get_monitor_status()
        vga_status = get_vga_status()
        hdmi_status = get_hdmi_status()
        
        new_status = {
            "USB Devices": usb_summary,
            "GPU": gpu_status,
            "Ethernet": ethernet_status,
            "Monitor": monitor_status,
            "VGA": vga_status,
            "HDMI": hdmi_status
        }
        
        for component, state in new_status.items():
            if state != status.get(component):
                anomaly = {
                    "SystemID": SYSTEM_ID,
                    "TimeGenerated": current_time,
                    "DeviceName": component,
                    "DeviceID": "",
                    "Event": f"Anomaly {component} changed from {status.get(component, 'Unknown')} to {state}"
                }
                logging.info(f"Status change: {anomaly}")
                send_anomaly(anomaly)
                save_anomaly_csv(anomaly)
                status[component] = state
        time.sleep(10)

def heartbeat_sender():
    """Send periodic heartbeat signals to the server."""
    while True:
        anomaly = {
            'SystemID': SYSTEM_ID,
            'TimeGenerated': time.strftime("%Y-%m-%d %H:%M:%S"),
            'DeviceName': 'Heartbeat',
            'DeviceID': '',
            'Event': 'Heartbeat'
        }
        send_anomaly(anomaly)
        time.sleep(10)

def shutdown_listener():
    """Listen for shutdown commands with password verification."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('0.0.0.0', SHUTDOWN_PORT))
        s.listen(1)
        logging.info(f"Client shutdown listener active on port {SHUTDOWN_PORT}")
        while True:
            conn, addr = s.accept()
            with conn:
                data = conn.recv(1024).decode('utf-8').strip()
                if data.startswith("shutdown"):
                    parts = data.split()
                    if len(parts) == 2 and parts[1] == SHUTDOWN_PASSWORD:
                        logging.info("Shutdown command accepted. Shutting down client...")
                        cleanup()
                        try:
                            if listener:
                                listener.stop()
                        except Exception as ex:
                            logging.error(f"Error stopping listener: {ex}")
                        os._exit(0)
                    else:
                        logging.warning("Incorrect shutdown password received.")
                        conn.sendall(b"Incorrect password")
                else:
                    conn.sendall(b"Invalid command")

### Cleanup and Signal Handling

def cleanup():
    """Clean up caches and resources before exiting."""
    logging.info("Cleaning up caches before exit.")
    last_logged_connection.clear()
    last_logged_removal.clear()

def signal_handler(sig, frame):
    """Handle termination signals."""
    logging.info("Signal received. Cleaning up and exiting.")
    cleanup()
    try:
        if listener:
            listener.stop()
    except Exception as ex:
        logging.error(f"Error stopping listener during signal handling: {ex}")
    sys.exit(0)

### Main Execution

if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        send_initial_status()
    
        threading.Thread(target=shutdown_listener, daemon=True).start()
        threading.Thread(target=heartbeat_sender, daemon=True).start()
        threading.Thread(target=monitor_usb_events, args=("Creation",), daemon=True).start()
        threading.Thread(target=monitor_usb_events, args=("Deletion",), daemon=True).start()
        threading.Thread(target=monitor_system_status, daemon=True).start()
    
        while True:
            time.sleep(1)
    finally:
        try:
            if listener:
                listener.stop()
        except Exception as ex:
            logging.error(f"Error in final listener stop: {ex}")
        cleanup()
