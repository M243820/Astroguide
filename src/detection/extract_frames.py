"""
Extracts still frames from raw videos for labeling.
Run once per video (or loop over a folder).

Usage:
    python src/detection/extract_frames.py data/raw/container/vid1.mp4 data/processed/container
"""

import cv2
import os
import sys


def extract_frames(video_path, output_folder, every_n_frames=10):
    os.makedirs(output_folder, exist_ok=True)
    cap = cv2.VideoCapture(video_path)
    count = 0
    saved = 0

    if not cap.isOpened():
        print(f"Could not open video: {video_path}")
        return

    video_name = os.path.splitext(os.path.basename(video_path))[0]

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if count % every_n_frames == 0:
            filename = os.path.join(output_folder, f"{video_name}_frame{count}.jpg")
            cv2.imwrite(filename, frame)
            saved += 1
        count += 1

    cap.release()
    print(f"Done. Extracted {saved} frames from {video_path} -> {output_folder}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python extract_frames.py <video_path> <output_folder> [every_n_frames]")
        sys.exit(1)

    video_path = sys.argv[1]
    output_folder = sys.argv[2]
    every_n = int(sys.argv[3]) if len(sys.argv) > 3 else 10

    extract_frames(video_path, output_folder, every_n)
