"""
config.py — Configuration and centralized logging setup.
"""
import logging
import logging.handlers
import queue

# ── Configuration ────────────────────────────────────────────────────────────
SYSTEM_ID         = 1
SERVER_IP         = "172.16.61.11"
SERVER_PORT       = 5000
SHUTDOWN_PORT     = 6000
SHUTDOWN_PASSWORD = "nick"
CSV_FILENAME      = "anomalies_mac.csv"
HEARTBEAT_SECS    = 9.0

# ── Logging Setup ────────────────────────────────────────────────────────────
# Setup a thread-safe queue-based logger to avoid blocking the macOS run loop
_log_queue = queue.Queue(-1)
_q_handler = logging.handlers.QueueHandler(_log_queue)

_file_h = logging.FileHandler("client_mac.log")
_fmt = logging.Formatter("%(asctime)s %(levelname)s: %(message)s")
_file_h.setFormatter(_fmt)

# We expose log_listener so main.py can call log_listener.stop() on shutdown
log_listener = logging.handlers.QueueListener(_log_queue, _file_h)
log_listener.start()

_console_h = logging.StreamHandler()
_console_h.setFormatter(_fmt)

logger = logging.getLogger("MacMonitor")
logger.setLevel(logging.INFO)
logger.addHandler(_q_handler)
logger.addHandler(_console_h)