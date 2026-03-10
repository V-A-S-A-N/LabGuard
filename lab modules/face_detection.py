import cv2
import mediapipe as mp
import threading
import time
from logger import logger

camera_lock = threading.Lock()

def detect_faces():
    """Capture and return a face image from the camera."""
    with camera_lock:
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            logger.error("Error: Could not open camera.")
            return None
        start_time = time.time()
        timeout = 10  # seconds
        mp_face_detection = mp.solutions.face_detection
        with mp_face_detection.FaceDetection(model_selection=0, min_detection_confidence=0.5) as face_detection:
            while cap.isOpened() and (time.time() - start_time < timeout):
                success, image = cap.read()
                if not success:
                    logger.warning("Failed to read frame from camera.")
                    continue
                image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
                image_rgb.flags.writeable = False
                results = face_detection.process(image_rgb)
                image_rgb.flags.writeable = True
                if results.detections:
                    detection = results.detections[0]  # Take the first detected face
                    bbox = detection.location_data.relative_bounding_box
                    img_height, img_width = image.shape[:2]
                    # Calculate bounding box coordinates
                    x_left = int(bbox.xmin * img_width)
                    y_top = int(bbox.ymin * img_height)
                    width = int(bbox.width * img_width)
                    height = int(bbox.height * img_height)
                    x_right = x_left + width
                    y_bottom = y_top + height
                    # Add 50% margin
                    margin_factor = 0.5
                    margin_x = int(width * margin_factor)
                    margin_y = int(height * margin_factor)
                    x_left = max(0, x_left - margin_x)
                    y_top = max(0, y_top - margin_y)
                    x_right = min(img_width, x_right + margin_x)
                    y_bottom = min(img_height, y_bottom + margin_y)
                    if x_right > x_left and y_bottom > y_top:
                        face = image[y_top:y_bottom, x_left:x_right]
                        cap.release()
                        logger.info("Face detected and captured.")
                        return face
                else:
                    logger.debug("No face detected in current frame.")
            cap.release()
            logger.info("No face detected within timeout period.")
            return None