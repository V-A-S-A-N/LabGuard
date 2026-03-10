import re
import time
import pythoncom
import wmi
from threading import Thread
from logger import logger
from anomaly_handler import process_anomaly

# Define constant locally
THROTTLE_INTERVAL = 1  # seconds

# Use correct keys matching event_type
last_events = {'Creation': {}, 'Deletion': {}}

def device_key(device_id):
    """Extract USB vendor/product ID"""
    match = re.search(r'USB\\VID_(\w+)&PID_(\w+)', device_id, re.I)
    return match.group(0) if match else device_id

def monitor_usb(event_type):
    """Monitor USB connections/removals"""
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
            key = device_key(device.PNPDeviceID)
            
            # Throttle repeated events
            if time.time() - last_events[event_type].get(key, 0) < THROTTLE_INTERVAL:
                continue
                
            last_events[event_type][key] = time.time()
            
            anomaly = {
                'TimeGenerated': time.strftime("%Y-%m-%d %H:%M:%S"),
                'DeviceName': device.Name,
                'DeviceID': device.PNPDeviceID,
                'Event': f'USB {event_type}'
            }
            
            process_anomaly(anomaly)
            logger.info(f"USB {event_type}: {device.Name}")

    finally:
        pythoncom.CoUninitialize()

def start_usb_monitoring():
    """Start monitoring threads"""
    Thread(target=monitor_usb, args=("Creation",), daemon=True).start()
    Thread(target=monitor_usb, args=("Deletion",), daemon=True).start()