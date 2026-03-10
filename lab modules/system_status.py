import re
import time
import pythoncom
import wmi
from threading import Thread
from logger import logger
from anomaly_handler import process_anomaly

# Constants
THROTTLE_INTERVAL = 1  # seconds

# State variables
class HardwareState:
    usb_count = 0
    gpu_present = False
    connected_networks = set()  # Set of connected network adapter DeviceIDs

state = HardwareState()
last_events = {'Creation': {}, 'Deletion': {}, 'Modification': {}}

def device_key(device_id):
    """Extract USB vendor/product ID or return full ID."""
    match = re.search(r'USB\\VID_(\w+)&PID_(\w+)', device_id, re.I)
    return match.group(0) if match else device_id

def initialize_state():
    """Query initial hardware state."""
    pythoncom.CoInitialize()
    try:
        conn = wmi.WMI()
        # Initial USB count
        usb_devices = conn.Win32_PnPEntity(ConfigManagerErrorCode=0)
        state.usb_count = len([d for d in usb_devices if 'USB' in d.PNPDeviceID])
        # Initial GPU presence
        state.gpu_present = bool(conn.Win32_VideoController())
        # Initial network status
        for adapter in conn.Win32_NetworkAdapter(PhysicalAdapter=True):
            if adapter.NetConnectionStatus == 2:
                state.connected_networks.add(adapter.DeviceID)
        logger.info(f"Initial state - USB: {state.usb_count}, GPU: {state.gpu_present}, Network: {bool(state.connected_networks)}")
    finally:
        pythoncom.CoUninitialize()

def monitor_usb(event_type):
    """Monitor USB creation/deletion events."""
    pythoncom.CoInitialize()
    try:
        wmi_conn = wmi.WMI()
        watcher = wmi_conn.ExecNotificationQuery(
            f"SELECT * FROM __Instance{event_type}Event WITHIN 2 "
            "WHERE TargetInstance ISA 'Win32_PnPEntity'"
        )
        while True:
            event = watcher.NextEvent()
            device = event.TargetInstance
            if 'USB' not in device.PNPDeviceID:
                continue  # Skip non-USB devices
            key = device_key(device.PNPDeviceID)
            if time.time() - last_events[event_type].get(key, 0) < THROTTLE_INTERVAL:
                continue
            last_events[event_type][key] = time.time()
            # Update state
            if event_type == "Creation":
                state.usb_count += 1
            else:  # Deletion
                state.usb_count = max(0, state.usb_count - 1)  # Prevent negative count
            # Log event
            anomaly = {
                'TimeGenerated': time.strftime("%Y-%m-%d %H:%M:%S"),
                'DeviceName': device.Name,
                'DeviceID': device.PNPDeviceID,
                'Event': f'USB {event_type}',
                'USBCount': state.usb_count
            }
            process_anomaly(anomaly)
            logger.info(f"USB {event_type}: {device.Name}, Count: {state.usb_count}")
    finally:
        pythoncom.CoUninitialize()

def monitor_gpu(event_type):
    """Monitor GPU creation/deletion events."""
    pythoncom.CoInitialize()
    try:
        wmi_conn = wmi.WMI()
        watcher = wmi_conn.ExecNotificationQuery(
            f"SELECT * FROM __Instance{event_type}Event WITHIN 2 "
            "WHERE TargetInstance ISA 'Win32_VideoController'"
        )
        while True:
            event = watcher.NextEvent()
            device = event.TargetInstance
            prev_state = state.gpu_present
            # Update state (simplified: assumes at least one GPU matters)
            if event_type == "Creation":
                state.gpu_present = True
            else:  # Deletion
                # Check if any GPUs remain
                conn = wmi.WMI()
                state.gpu_present = bool(conn.Win32_VideoController())
            if prev_state != state.gpu_present:
                anomaly = {
                    'TimeGenerated': time.strftime("%Y-%m-%d %H:%M:%S"),
                    'DeviceName': device.Name,
                    'Event': f'GPU {event_type}',
                    'GPUStatus': state.gpu_present
                }
                process_anomaly(anomaly)
                logger.info(f"GPU {event_type}: {device.Name}, Present: {state.gpu_present}")
    finally:
        pythoncom.CoUninitialize()

def monitor_network():
    """Monitor network adapter status changes."""
    pythoncom.CoInitialize()
    try:
        wmi_conn = wmi.WMI()
        watcher = wmi_conn.ExecNotificationQuery(
            "SELECT * FROM __InstanceModificationEvent WITHIN 2 "
            "WHERE TargetInstance ISA 'Win32_NetworkAdapter' AND TargetInstance.PhysicalAdapter = TRUE"
        )
        while True:
            event = watcher.NextEvent()
            prev = event.PreviousInstance
            curr = event.TargetInstance
            if prev.NetConnectionStatus == curr.NetConnectionStatus:
                continue  # No status change
            device_id = curr.DeviceID
            prev_connected = bool(state.connected_networks)
            # Update state
            if curr.NetConnectionStatus == 2:
                state.connected_networks.add(device_id)
            elif prev.NetConnectionStatus == 2:
                state.connected_networks.discard(device_id)
            curr_connected = bool(state.connected_networks)
            if prev_connected != curr_connected:
                anomaly = {
                    'TimeGenerated': time.strftime("%Y-%m-%d %H:%M:%S"),
                    'DeviceName': curr.Name,
                    'Event': f'Network status change',
                    'NetworkStatus': curr_connected
                }
                process_anomaly(anomaly)
                logger.info(f"Network status changed: {curr.Name}, Connected: {curr_connected}")
    finally:
        pythoncom.CoUninitialize()

def start_hardware_monitoring():
    """Start all monitoring threads."""
    initialize_state()
    Thread(target=monitor_usb, args=("Creation",), daemon=True).start()
    Thread(target=monitor_usb, args=("Deletion",), daemon=True).start()
    Thread(target=monitor_gpu, args=("Creation",), daemon=True).start()
    Thread(target=monitor_gpu, args=("Deletion",), daemon=True).start()
    Thread(target=monitor_network, daemon=True).start()

if __name__ == "__main__":
    start_hardware_monitoring()
    try:
        while True:
            time.sleep(1)  # Keep main thread alive
    except KeyboardInterrupt:
        logger.info("Monitoring stopped.")