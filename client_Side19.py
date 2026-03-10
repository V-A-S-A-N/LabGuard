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
import sys
import signal
import queue
import re
from collections import Counter
import face_detection  # Import the face detection package
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

SYSTEM_ID = 1
SERVER_IP = '192.168.137.1'  # Replace with your server's IP address
SERVER_PORT = 5000
CSV_FILENAME = 'anomalies.csv'
SHUTDOWN_PASSWORD = "nick"
SHUTDOWN_PORT = 6000
THROTTLE_INTERVAL = 1  # Seconds to throttle repeated events

### Global Variables (Thread-Safe)

csv_lock = threading.Lock()
last_logged_connection = {}
last_logged_removal = {}
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

def trigger_face_detection():
    """Trigger face detection in a separate thread."""
    def run_detection():
        try:
            face_detection.detect_faces()
        except Exception as e:
            logging.error(f"Error in face detection: {e}")
    threading.Thread(target=run_detection, daemon=True).start()

### Initial Status and Monitoring

def send_initial_status():
    """Send initial system status using the consolidated status function."""
    global initial_status_snapshot
    initial_status = get_system_status()
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
            err_str = str(e)
            if "Quota violation" in err_str:
                logging.error(f"Quota violation encountered in WMI event loop: {e}")
                time.sleep(30)
            else:
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
                r = "Device Removal"
                c = "Device Connected"
                event_description = r if event_type == "Deletion" else c
                anomaly = {
                    'SystemID': SYSTEM_ID,
                    'TimeGenerated': time.strftime("%Y-%m-%d %H:%M:%S"),
                    'DeviceName': device_name,
                    'DeviceID': device_id,
                    'Event': f"Anomaly {event_description}"
                }
                logging.info(f"Detected {event_description}: {anomaly}")
                trigger_face_detection()  # Trigger face detection for USB anomaly
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
    """Monitor and report changes in system status using the consolidated check."""
    status = initial_status_snapshot.copy() if initial_status_snapshot else get_system_status()
    while True:
        current_time = time.strftime("%Y-%m-%d %H:%M:%S")
        new_status = get_system_status()
        for component in new_status:
            if new_status[component] != status.get(component):
                anomaly = {
                    "SystemID": SYSTEM_ID,
                    "TimeGenerated": current_time,
                    "DeviceName": component,
                    "DeviceID": "",
                    "Event": f"Anomaly {component} changed from {status.get(component, 'Unknown')} to {new_status[component]}"
                }
                logging.info(f"Status change: {anomaly}")
                trigger_face_detection()  # Trigger face detection for status anomaly
                send_anomaly(anomaly)
                save_anomaly_csv(anomaly)
                status[component] = new_status[component]
        time.sleep(10)

def get_system_status():
    """Retrieve the current status of all monitored components, reporting only connected devices."""
    pythoncom.CoInitialize()
    status = {
        "USB Devices": "None",
        "GPU": "Missing",
        "Ethernet": "Disconnected",
        "Monitor": "Missing",
        "VGA": "Missing",
        "HDMI": "Missing"
    }
    try:
        c = wmi.WMI()
        pnp_devices = c.Win32_PnPEntity()
        usb_devices = []
        vga_monitor = False
        hdmi_monitor = False
        
        for dev in pnp_devices:
            dev_id = getattr(dev, "PNPDeviceID", "")
            dev_name = getattr(dev, "Name", "").lower()
            if dev_id.startswith("USB") and getattr(dev, "ConfigManagerErrorCode", -1) == 0:
                if "bluetooth" not in dev_name:
                    usb_devices.append(dev_name)
        
        counts = Counter(usb_devices)
        usb_summary = ", ".join(sorted(
            f"{name} ({count})" if count > 1 else name 
            for name, count in counts.items())) if counts else "None"
        status["USB Devices"] = usb_summary
        
        video_controllers = c.Win32_VideoController()
        for vc in video_controllers:
            if getattr(vc, "ConfigManagerErrorCode", -1) == 0:
                status["GPU"] = "Present"
                break
        
        monitors = c.Win32_DesktopMonitor()
        for mon in monitors:
            if getattr(mon, "Availability", 0) == 3:
                status["Monitor"] = "Present"
                mon_name = getattr(mon, "Name", "").lower()
                if "vga" in mon_name:
                    vga_monitor = True
                elif "hdmi" in mon_name:
                    hdmi_monitor = True
                break
        
        if not (vga_monitor or hdmi_monitor):
            for vc in video_controllers:
                vc_name = getattr(vc, "Name", "").lower()
                if "vga" in vc_name and status["Monitor"] == "Present":
                    vga_monitor = True
                elif "hdmi" in vc_name and status["Monitor"] == "Present":
                    hdmi_monitor = True
        
        status["VGA"] = "Present" if vga_monitor else "Missing"
        status["HDMI"] = "Present" if hdmi_monitor else "Missing"
        
        adapters = c.Win32_NetworkAdapter(NetConnectionID="Ethernet", PhysicalAdapter=True)
        for adapter in adapters:
            if getattr(adapter, "NetConnectionStatus", 0) == 2:
                status["Ethernet"] = "Connected"
                break
        
    except Exception as e:
        logging.error(f"Error retrieving system status: {e}")
    finally:
        pythoncom.CoUninitialize()
    return status

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
                            global listener
                            if listener is not None:
                                listener.stop()
                                listener = None
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
        global listener
        if listener is not None:
            listener.stop()
            listener = None
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
            if listener is not None:
                listener.stop()
                listener = None
        except Exception as ex:
            logging.error(f"Error in final listener stop: {ex}")
        cleanup()