import wmi
import pythoncom
import logging

# Setup basic logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

def get_filtered_usb_devices():
    """
    Retrieve the list of connected USB devices whose Name contains
    "composite" or "unknown". This filtering is case-insensitive.
    """
    pythoncom.CoInitialize()
    filtered_devices = []
    try:
        c = wmi.WMI()
        # Query for USB devices using a wildcard for PNPDeviceID.
        devices = c.query("SELECT * FROM Win32_PnPEntity WHERE PNPDeviceID LIKE 'USB%'")
        for dev in devices:
            name = getattr(dev, "Name", "Unknown Device")
            device_id = getattr(dev, "PNPDeviceID", "Unknown ID")
            lower_name = name.lower()
            # Filter for devices that include "composite" or "unknown" in the name.
            if "composite" in lower_name or "unknown" in lower_name:
                filtered_devices.append({"Name": name, "ID": device_id})
    except Exception as e:
        logging.error("Error retrieving USB devices: %s", e)
    finally:
        pythoncom.CoUninitialize()
    return filtered_devices

if __name__ == "__main__":
    devices = get_filtered_usb_devices()
    logging.info("Found %d matching USB device(s).", len(devices))
    for dev in devices:
        print("Name: {}".format(dev["Name"]))
        print("ID: {}".format(dev["ID"]))
        print("")
