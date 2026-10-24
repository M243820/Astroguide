"""
Fine-tunes YOLOv8 on the custom AstroGuide object dataset.

Run with:
    python src/detection/train_yolo.py
"""

from ultralytics import YOLO


def train():
    model = YOLO("yolov8n.pt")  # start from pretrained weights (transfer learning)

    model.train(
        data="configs/data.yaml",
        epochs=50,
        imgsz=640,
        degrees=180,     # rotation augmentation — important for tumbling/floating objects
        flipud=0.5,
        fliplr=0.5,
        mosaic=1.0,
        hsv_v=0.6,       # exaggerated brightness/exposure variation — station lighting
                         # swings from bright window glare to deep shadow, more extreme
                         # than typical training data assumes (default is 0.4)
        hsv_s=0.5,       # saturation variation, helps with washed-out overexposed frames
        patience=10,     # stop early if it's not improving, saves time
    )

    # Trained weights get saved automatically under runs/detect/train/weights/best.pt
    print("Training complete. Copy runs/detect/train/weights/best.pt into models/yolo/")


if __name__ == "__main__":
    train()
