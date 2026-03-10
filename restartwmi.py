import subprocess
import logging
import time

def reset_wmi_service():
    try:
        # Attempt to stop the WMI service.
        stop_result = subprocess.run(["net", "stop", "winmgmt"], capture_output=True, text=True)
        logging.info("Stop WMI service output:\n%s", stop_result.stdout)
        if stop_result.returncode != 0:
            # If the service could not be stopped because it's in transition or already running,
            # check for common phrases.
            if ("could not be stopped" in stop_result.stdout or 
                "already been started" in stop_result.stdout or
                "service is stopping" in stop_result.stdout):
                logging.info("WMI service is already stopping or in transition. Waiting before attempting to start.")
            else:
                logging.error("Unexpected error stopping WMI service:\n%s", stop_result.stdout)
        
        # Wait a few seconds to allow the service state to change.
        time.sleep(5)

        # Attempt to start the WMI service.
        start_result = subprocess.run(["net", "start", "winmgmt"], capture_output=True, text=True)
        logging.info("Start WMI service output:\n%s", start_result.stdout)
        if start_result.returncode != 0:
            if "already been started" in start_result.stdout:
                logging.info("WMI service is already running.")
            else:
                logging.error("Unexpected error starting WMI service:\n%s", start_result.stdout)
        else:
            logging.info("WMI service restarted successfully.")
    except Exception as e:
        logging.error("Error resetting WMI service: %s", e)

if __name__ == "__main__":
    reset_wmi_service()
