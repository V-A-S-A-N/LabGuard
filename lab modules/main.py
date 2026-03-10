import signal
import sys
from logger import logger
from usb_handler import start_usb_monitoring
from system_status import start_status_monitoring
from heartbeat import start_heartbeat
from shutdown_listener import listen_for_shutdown
# Ensure anomaly_handler and face_detection are imported by dependent modules

def cleanup(signum, frame):
    """Handle cleanup on shutdown."""
    logger.info("Performing cleanup...")
    sys.exit(0)

if __name__ == "__main__":
    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)
    
    logger.info("Starting application...")
    start_usb_monitoring()
    start_status_monitoring()
    start_heartbeat()
    
    # Start shutdown listener in main thread
    listen_for_shutdown()