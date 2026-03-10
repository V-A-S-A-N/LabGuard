import cv2
import os
import time
from skimage.metrics import structural_similarity as ssim
import numpy as np

def capture_image(save_path="Face_Recognition\lionel-messi.jpg"):
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Error: Could not open camera.")
        return None

    time.sleep(2)  # Let camera adjust
    ret, frame = cap.read()
    cap.release()

    if not ret:
        print("Error: Failed to capture image.")
        return None

    cv2.imwrite(save_path, frame)
    return save_path

def compare_images(img1_path, img2_path):
    img1 = cv2.imread(img1_path)
    img2 = cv2.imread(img2_path)

    if img1 is None or img2 is None:
        print("Error: One or both images could not be loaded.")
        return

    # Resize to same dimensions
    img1 = cv2.resize(img1, (300, 300))
    img2 = cv2.resize(img2, (300, 300))

    # Convert to grayscale
    gray1 = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY)
    gray2 = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY)

    # Compute SSIM
    score, _ = ssim(gray1, gray2, full=True)

    print(f"Similarity Score: {score:.2f}")
    if score > 0.8:
        print("✅ Images are likely of the same person.")
    else:
        print("❌ Images are different.")

if __name__ == "__main__":
    reference_image = "Face_Recognition\lionel-messi.jpg"  # Change to your image path

    captured_path = capture_image()
    if captured_path:
        compare_images(reference_image, captured_path)
