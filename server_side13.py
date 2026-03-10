import socketserver
import json
import csv
import os
import logging
import threading
import time
import socket
from flask import Flask, render_template, redirect, url_for, flash
import signal
import sys
import winsound

logging.basicConfig(level=logging.INFO)

# Constants
ANOMALY_CSV_FILENAME = "anomalies_server.csv"
LISTEN_HOST, LISTEN_PORT = "0.0.0.0", 5000
HEARTBEAT_THRESHOLD = 10
SHUTDOWN_PASSWORD, SHUTDOWN_PORT = "nick", 6000
AUDIO_FILE, COOLDOWN_PERIOD = 'alert.wav', 5

# Global data with locks
last_seen, last_seen_lock = {}, threading.Lock()
client_status, client_status_lock = {}, threading.Lock()
shutdowned_clients, shutdowned_clients_lock = set(), threading.Lock()
last_sound_time, sound_lock = 0, threading.Lock()

def log_anomaly_to_csv(timestamp, system_id, device_name, device_id, event, sender_ip):
    """Log anomaly to CSV and console."""
    with open(ANOMALY_CSV_FILENAME, mode='a', newline='') as file:
        csv.writer(file).writerow([timestamp, system_id, device_name, device_id, event, sender_ip])
    logging.info("Logged anomaly from system '%s': %s", system_id, event)

def play_alert_sound():
    """Play alert sound with cooldown."""
    global last_sound_time
    with sound_lock:
        if time.time() - last_sound_time > COOLDOWN_PERIOD and os.path.exists(AUDIO_FILE):
            try:
                winsound.PlaySound(AUDIO_FILE, winsound.SND_FILENAME | winsound.SND_ASYNC)
                last_sound_time = time.time()
            except Exception as e:
                logging.error("Failed to play alert sound: %s", e)

def init_csv():
    """Initialize CSV if it doesn't exist."""
    if not os.path.exists(ANOMALY_CSV_FILENAME):
        with open(ANOMALY_CSV_FILENAME, mode='w', newline='') as file:
            csv.writer(file).writerow(["Timestamp", "SystemID", "DeviceName", "DeviceID", "Event", "SenderIP"])

class AnomalyTCPHandler(socketserver.BaseRequestHandler):
    def handle(self):
        sender_ip = self.client_address[0]
        try:
            data = self.request.recv(4096).strip()
            if not data: return
            anomaly = json.loads(data.decode('utf-8'))
            system_id = anomaly.get("SystemID", sender_ip)
            timestamp = anomaly.get("TimeGenerated", time.strftime("%Y-%m-%d %H:%M:%S"))
            event = anomaly.get("Event", "")
            
            with shutdowned_clients_lock, last_seen_lock:
                if event == "System Shutting Down":
                    if system_id in last_seen: del last_seen[system_id]
                    shutdowned_clients.add(system_id)
                    logging.info("System '%s' shut down.", system_id)
                elif system_id not in shutdowned_clients:
                    last_seen[system_id] = (time.time(), sender_ip)
            
            if "StatusDetails" in anomaly:
                with client_status_lock:
                    client_status[system_id] = anomaly
                if event == "Initial Status": return
            
            if event != "Heartbeat":
                log_anomaly_to_csv(timestamp, system_id, anomaly.get("DeviceName", ""), 
                                 anomaly.get("DeviceID", ""), event, sender_ip)
                play_alert_sound()
        except Exception as e:
            logging.error("Error processing data from %s: %s", sender_ip, e)

class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True

def heartbeat_check():
    """Monitor heartbeats and log anomalies."""
    while True:
        with last_seen_lock, shutdowned_clients_lock:
            current_time = time.time()
            for system_id in list(last_seen):
                if system_id in shutdowned_clients: continue
                if current_time - last_seen[system_id][0] > HEARTBEAT_THRESHOLD:
                    log_anomaly_to_csv(time.strftime("%Y-%m-%d %H:%M:%S"), system_id, "Heartbeat", 
                                     "", "No heartbeat received – system not responding", "N/A")
                    del last_seen[system_id]
        time.sleep(10)

# Flask Interface
app = Flask(__name__)
app.secret_key = "supersecretkey"

@app.route("/", methods=["GET"])
def index():
    current_time = time.time()
    with last_seen_lock, client_status_lock:
        systems = [
            {"system_id": sid, "ip": ip, "last_seen": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(lt)),
             "status": "Online" if current_time - lt <= HEARTBEAT_THRESHOLD else "Offline",
             "status_details": client_status.get(sid, {}).get("StatusDetails", {})}
            for sid, (lt, ip) in last_seen.items()
        ]
    systems.sort(key=lambda x: (x["status"] != "Online", -time.mktime(time.strptime(x["last_seen"], "%Y-%m-%d %H:%M:%S"))))
    
    anomalies = []
    try:
        with open(ANOMALY_CSV_FILENAME, 'r') as f:
            rows = list(csv.DictReader(f))
            for row in rows[-20:][::-1]:
                anomalies.append({
                    "timestamp": row["Timestamp"],
                    "system_id": row["SystemID"],
                    "event": row["Event"]
                })
    except FileNotFoundError:
        pass

    return render_template("dashboard_new.html", systems=systems, anomalies=anomalies)

@app.route("/shutdown/<int:index>", methods=["POST"])
def shutdown_system(index):
    with last_seen_lock:
        systems = list(last_seen.items())
    if not 0 <= index < len(systems):
        flash("Invalid system index.")
        return redirect(url_for("index"))
    system_id, (_, target_ip) = systems[index]
    try:
        with socket.create_connection((target_ip, SHUTDOWN_PORT), timeout=10) as s:
            s.sendall(f"shutdown {SHUTDOWN_PASSWORD}".encode('utf-8'))
            flash(f"Shutdown command sent to {target_ip}: {s.recv(1024).decode('utf-8')}")
        with last_seen_lock, shutdowned_clients_lock:
            if system_id in last_seen: del last_seen[system_id]
            shutdowned_clients.add(system_id)
    except Exception as e:
        flash(f"Error sending shutdown command to {target_ip}: {e}")
    return redirect(url_for("index"))

def cleanup_server(server):
    """Cleanup and shutdown server."""
    with last_seen_lock, client_status_lock, shutdowned_clients_lock:
        last_seen.clear(); client_status.clear(); shutdowned_clients.clear()
    if server: server.shutdown(); server.server_close()

def main():
    init_csv()
    server = ThreadedTCPServer((LISTEN_HOST, LISTEN_PORT), AnomalyTCPHandler)
    logging.info("Server started on %s:%s", server.server_address[0] or "0.0.0.0", LISTEN_PORT)
    
    for target in (server.serve_forever, heartbeat_check, lambda: app.run(host="0.0.0.0", port=8000)):
        threading.Thread(target=target, daemon=True).start()
    
    signal.signal(signal.SIGINT, lambda s, f: (cleanup_server(server), sys.exit(0)))
    signal.signal(signal.SIGTERM, lambda s, f: (cleanup_server(server), sys.exit(0)))
    try:
        while True: time.sleep(1)
    except KeyboardInterrupt:
        cleanup_server(server)

if __name__ == "__main__":
    main()