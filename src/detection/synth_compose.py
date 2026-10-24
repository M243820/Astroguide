"""
Synthetic data generator for AstroGuide.

Takes:
  - object photos shot against a plain background (data/raw/<object>/*.jpg)
  - real NASA station interior background photos (data/backgrounds/*.jpg)
    -> download these yourself from images.nasa.gov (public domain, free to use/download)

Produces:
  - composite images with the object pasted at a random rotation, scale, and
    position onto a real station background
  - a matching YOLO-format .txt label file for each composite, generated
    automatically from where the object was pasted

This is how we get "object floating at any orientation, in a real space
station" training data without ever filming inside a space station.

Usage:
    python src/detection/synth_compose.py
"""

import cv2
import numpy as np
import os
import random
import glob

OBJECT_DIR = "data/raw"              # data/raw/<class_name>/*.jpg
BACKGROUND_DIR = "data/backgrounds"  # NASA station interior photos
OUTPUT_IMG_DIR = "data/processed/synthetic/images"
OUTPUT_LABEL_DIR = "data/processed/synthetic/labels"
COMPOSITES_PER_OBJECT_IMAGE = 6       # how many synthetic scenes per source object photo

CLASS_NAMES = ["container", "switch", "tool", "lid"]  # must match configs/data.yaml order


def segment_object(obj_img):
    """
    Rough foreground extraction assuming the object was shot against a
    plain, fairly uniform background (a wall, a sheet of paper, a desk).
    Not perfect — good enough for synthetic training data.
    """
    gray = cv2.cvtColor(obj_img, cv2.COLOR_BGR2GRAY)
    _, mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    # clean up small noise in the mask
    kernel = np.ones((5, 5), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    return mask


def rotate_and_scale(obj_img, mask, angle, scale):
    h, w = obj_img.shape[:2]
    center = (w // 2, h // 2)
    M = cv2.getRotationMatrix2D(center, angle, scale)
    rotated_obj = cv2.warpAffine(obj_img, M, (w, h), borderMode=cv2.BORDER_CONSTANT)
    rotated_mask = cv2.warpAffine(mask, M, (w, h), borderMode=cv2.BORDER_CONSTANT)
    return rotated_obj, rotated_mask


def paste_on_background(bg_img, obj_img, mask, top_left):
    bg = bg_img.copy()
    x, y = top_left
    h, w = obj_img.shape[:2]

    # clip to background bounds
    if y + h > bg.shape[0] or x + w > bg.shape[1] or x < 0 or y < 0:
        return None, None

    roi = bg[y:y+h, x:x+w]
    mask_3ch = cv2.merge([mask, mask, mask]) / 255.0
    blended = (obj_img * mask_3ch + roi * (1 - mask_3ch)).astype(np.uint8)
    bg[y:y+h, x:x+w] = blended

    # bounding box of the pasted object, for the YOLO label
    ys, xs = np.where(mask > 0)
    if len(xs) == 0:
        return None, None
    box = (x + xs.min(), y + ys.min(), x + xs.max(), y + ys.max())
    return bg, box


def write_yolo_label(label_path, box, class_id, img_w, img_h):
    x1, y1, x2, y2 = box
    cx = ((x1 + x2) / 2) / img_w
    cy = ((y1 + y2) / 2) / img_h
    bw = (x2 - x1) / img_w
    bh = (y2 - y1) / img_h
    with open(label_path, "w") as f:
        f.write(f"{class_id} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}\n")


def main():
    os.makedirs(OUTPUT_IMG_DIR, exist_ok=True)
    os.makedirs(OUTPUT_LABEL_DIR, exist_ok=True)

    backgrounds = glob.glob(os.path.join(BACKGROUND_DIR, "*.jpg")) + \
                  glob.glob(os.path.join(BACKGROUND_DIR, "*.png"))

    if not backgrounds:
        print(f"No background images found in {BACKGROUND_DIR}. "
              f"Download some ISS/station interior photos from images.nasa.gov first.")
        return

    counter = 0
    for class_id, class_name in enumerate(CLASS_NAMES):
        obj_images = glob.glob(os.path.join(OBJECT_DIR, class_name, "*.jpg"))
        for obj_path in obj_images:
            obj_img = cv2.imread(obj_path)
            if obj_img is None:
                continue
            mask = segment_object(obj_img)

            for _ in range(COMPOSITES_PER_OBJECT_IMAGE):
                angle = random.uniform(0, 360)      # any orientation — no "resting" angle
                scale = random.uniform(0.4, 1.0)     # varies distance from camera
                rotated_obj, rotated_mask = rotate_and_scale(obj_img, mask, angle, scale)

                bg_path = random.choice(backgrounds)
                bg_img = cv2.imread(bg_path)
                bg_img = cv2.resize(bg_img, (1280, 720))
                rotated_obj = cv2.resize(rotated_obj, (300, 300))
                rotated_mask = cv2.resize(rotated_mask, (300, 300))

                max_x = 1280 - 300
                max_y = 720 - 300
                top_left = (random.randint(0, max_x), random.randint(0, max_y))

                composite, box = paste_on_background(bg_img, rotated_obj, rotated_mask, top_left)
                if composite is None:
                    continue

                img_name = f"{class_name}_{counter}.jpg"
                label_name = f"{class_name}_{counter}.txt"
                cv2.imwrite(os.path.join(OUTPUT_IMG_DIR, img_name), composite)
                write_yolo_label(os.path.join(OUTPUT_LABEL_DIR, label_name),
                                  box, class_id, 1280, 720)
                counter += 1

    print(f"Generated {counter} synthetic training images in {OUTPUT_IMG_DIR}")


if __name__ == "__main__":
    main()
