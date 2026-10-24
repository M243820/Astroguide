"""
Preprocessing to handle harsh, uneven lighting (bright window glare vs deep
shadow) before frames go into YOLO/MediaPipe. Import and call this in
main_pipeline.py before running detection on each frame.
"""

import cv2
import numpy as np


def normalize_exposure(frame):
    """
    Applies CLAHE (Contrast Limited Adaptive Histogram Equalization) to
    even out lighting — brightens shadowed regions and tames blown-out
    highlights, without over-processing the whole image uniformly like a
    simple brightness slider would.
    """
    lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)

    clahe = cv2.createCLAHE(clipLimit=3.5, tileGridSize=(8, 8))
    l_eq = clahe.apply(l)

    merged = cv2.merge((l_eq, a, b))
    result = cv2.cvtColor(merged, cv2.COLOR_LAB2BGR)
    return result


if __name__ == "__main__":
    # quick visual test against your webcam
    cap = cv2.VideoCapture(0)
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        fixed = normalize_exposure(frame)
        combined = np.hstack((frame, fixed))
        cv2.imshow("Original (left) vs Exposure-Normalized (right)", combined)
        if cv2.waitKey(1) & 0xFF == 27:
            break
    cap.release()
    cv2.destroyAllWindows()
