import cv2
import os
import time

def capture_image(save_folder="captured_images"):
    # Create the folder if it doesn't exist
    if not os.path.exists(save_folder):
        os.makedirs(save_folder)

    # Count existing images to determine the next filename
    existing_files = [f for f in os.listdir(save_folder) if f.startswith("image_") and f.endswith(".jpg")]
    next_index = len(existing_files) + 1
    filename = f"image_{next_index}.jpg"
    filepath = os.path.join(save_folder, filename)

    # Open the camera
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Error: Could not open camera.")
        return

    time.sleep(2)  # Let camera adjust
    ret, frame = cap.read()

    if ret:
        cv2.imwrite(filepath, frame)
        print(f"Image saved as {filepath}")
    else:
        print("Error: Failed to capture image.")

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    capture_image()
