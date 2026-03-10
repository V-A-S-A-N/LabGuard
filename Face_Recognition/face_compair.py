import cv2
import time
from deepface import DeepFace

def capture_image(save_path="captured.jpg"):
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Error: Could not open camera.")
        return None

    time.sleep(2)  # Let camera warm up
    ret, frame = cap.read()
    cap.release()

    if not ret:
        print("Error: Failed to capture image.")
        return None

    cv2.imwrite(save_path, frame)
    print(f"Captured image saved to {save_path}")
    return save_path

def compare_faces(reference_path, captured_path):
    try:
        result = DeepFace.verify(img1_path=reference_path, img2_path=captured_path)
        print("Comparison Result:")
        print(f" - Verified: {result['verified']}")
        print(f" - Distance: {result['distance']:.4f}")
        print(f" - Model Used: {result['model']}")
        
        if result["verified"]:
            print("✅ It's the same person!")
        else:
            print("❌ Different people.")
    except Exception as e:
        print("Error during comparison:", e)

if __name__ == "__main__":
    reference_img = "Face_Recognition\messi.jpg"  # <-- Replace with your reference image path
    captured_img = capture_image()

    if captured_img:
        compare_faces(reference_img, captured_img)
