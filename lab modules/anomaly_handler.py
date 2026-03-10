import socket
import csv
import threading
import json
import os
import cv2
import base64
from logger import logger
from face_detection import detect_faces
import time

# Define constants locally
SYSTEM_ID = 1
SERVER_IP = '192.168.137.1'
SERVER_PORT = 5000
CSV_FILENAME = 'anomalies.csv'

csv_lock = threading.Lock()

def send_anomaly(anomaly_data):
    """Send anomaly data to the server."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(10)
            sock.connect((SERVER_IP, SERVER_PORT))
            sock.sendall(json.dumps(anomaly_data).encode())
            logger.info(f"Anomaly sent to server: {anomaly_data['Event']}")
    except Exception as e:
        logger.error(f"Server communication error: {e}")

def save_anomaly(anomaly_data):
    """Save anomaly data to CSV and store face image if present."""
    try:
        with csv_lock:
            file_exists = os.path.isfile(CSV_FILENAME)
            with open(CSV_FILENAME, 'a', newline='') as f:
                writer = csv.writer(f)
                if not file_exists:
                    writer.writerow(["Time", "SystemID", "Device", "Event", "ImageFile"])
                image_file = None
                if 'Image' in anomaly_data and anomaly_data['Image'] is not None:
                    timestamp = int(time.time() * 1000)
                    image_file = f"face_{timestamp}.jpg"
                    save_dir = "captured_faces"
                    os.makedirs(save_dir, exist_ok=True)
                    with open(os.path.join(save_dir, image_file), 'wb') as img_f:
                        img_f.write(base64.b64decode(anomaly_data['Image']))
                    logger.info(f"Face image saved: {image_file}")
                writer.writerow([
                    anomaly_data['TimeGenerated'],
                    SYSTEM_ID,
                    anomaly_data['DeviceName'],
                    anomaly_data['Event'],
                    image_file if image_file else ''
                ])
    except Exception as e:
        logger.error(f"CSV save error: {e}")

def process_anomaly(anomaly_data):
    """Handle the full anomaly workflow."""
    # Capture face only for USB-related anomalies
    if anomaly_data['Event'].startswith('USB'):
        face_image = detect_faces()
        if face_image is not None:
            _, buffer = cv2.imencode('.jpg', face_image)
            image_base64 = base64.b64encode(buffer).decode('utf-8')
            anomaly_data['Image'] = image_base64
        else:
            anomaly_data['Image'] = None
            logger.warning("No face captured for USB anomaly.")
    else:
        anomaly_data['Image'] = None
    
    send_anomaly(anomaly_data)
    save_anomaly(anomaly_data)