import time
from threading import Thread
from anomaly_handler import process_anomaly

def send_heartbeat():
    while True:
        process_anomaly({
            'TimeGenerated': time.strftime("%Y-%m-%d %H:%M:%S"),
            'DeviceName': 'System',
            'Event': 'Heartbeat'
        })
        time.sleep(60)

def start_heartbeat():
    Thread(target=send_heartbeat, daemon=True).start()