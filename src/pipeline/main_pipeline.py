"""
AstroGuide — Main Pipeline

This is the actual "tracking software" — it owns the camera, runs object
detection + hand tracking on every frame, checks progress against the
procedure via ProcedureTracker, fires voice alerts, saves video locally,
writes live status/log files, and streams the live video feed directly to
the Streamlit web frontend via HTTP MJPEG on port 5005.
"""

import os
import sys
import time
import datetime
import cv2
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from ultralytics import YOLO

import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision as mp_vision

sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))
from src.tracking.tracker import ProcedureTracker, load_settings
from src.detection.exposure_fix import normalize_exposure

PROCEDURE_PATH = "procedure.json"
FINE_TUNED_MODEL_PATH = "models/yolo/best.pt"
GENERIC_MODEL_PATH = "yolov8n.pt"
VIDEO_OUTPUT_DIR = "outputs/videos"
POSE_MODEL_PATH = "pose_landmarker.task"
HAND_MODEL_PATH = "hand_landmarker.task"

# Global frame buffer for live web streaming
latest_jpeg_bytes = None
frame_lock = threading.Lock()


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


class StreamHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return  # Suppress HTTP request logging

    def do_GET(self):
        if self.path.startswith("/video_feed"):
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            while True:
                with frame_lock:
                    frame = latest_jpeg_bytes
                if frame is not None:
                    try:
                        self.wfile.write(b"--frame\r\n")
                        self.send_header("Content-Type", "image/jpeg")
                        self.send_header("Content-Length", str(len(frame)))
                        self.end_headers()
                        self.wfile.write(frame)
                        self.wfile.write(b"\r\n")
                    except (OSError, ConnectionResetError, BrokenPipeError):
                        break
                time.sleep(0.033)
        elif self.path.startswith("/snapshot"):
            with frame_lock:
                frame = latest_jpeg_bytes
            if frame is not None:
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(len(frame)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(frame)
            else:
                self.send_error(404)
        else:
            self.send_error(404)


def start_stream_server(port=5005):
    try:
        server = ThreadedHTTPServer(("0.0.0.0", port), StreamHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        print(f"HTTP MJPEG Stream Server running on http://127.0.0.1:{port}/video_feed")
    except Exception as e:
        print(f"Stream server start notice ({e}); proceeding...")


def create_pose_landmarker():
    if not os.path.exists(POSE_MODEL_PATH):
        raise FileNotFoundError(
            f"{POSE_MODEL_PATH} not found. Download it first."
        )
    base_options = mp_python.BaseOptions(model_asset_path=POSE_MODEL_PATH)
    options = mp_vision.PoseLandmarkerOptions(
        base_options=base_options,
        running_mode=mp_vision.RunningMode.VIDEO,
    )
    return mp_vision.PoseLandmarker.create_from_options(options)


def create_hand_landmarker():
    if not os.path.exists(HAND_MODEL_PATH):
        raise FileNotFoundError(
            f"{HAND_MODEL_PATH} not found. Download it first."
        )
    base_options = mp_python.BaseOptions(model_asset_path=HAND_MODEL_PATH)
    options = mp_vision.HandLandmarkerOptions(
        base_options=base_options,
        running_mode=mp_vision.RunningMode.VIDEO,
        num_hands=2,
    )
    return mp_vision.HandLandmarker.create_from_options(options)


def get_hand_points_from_hand_model(hand_result, frame_shape):
    points = []
    if hand_result.hand_landmarks:
        h, w = frame_shape[:2]
        for hand_landmarks in hand_result.hand_landmarks:
            xs = [lm.x * w for lm in hand_landmarks]
            ys = [lm.y * h for lm in hand_landmarks]
            points.append((sum(xs) / len(xs), sum(ys) / len(ys)))
    return points


def draw_hand_landmarks(frame, hand_result):
    if not hand_result.hand_landmarks:
        return frame
    h, w = frame.shape[:2]
    for hand_landmarks in hand_result.hand_landmarks:
        for lm in hand_landmarks:
            cx, cy = int(lm.x * w), int(lm.y * h)
            cv2.circle(frame, (cx, cy), 3, (255, 0, 255), -1)
    return frame


def draw_landmarks(frame, pose_result):
    if not pose_result.pose_landmarks:
        return frame
    h, w = frame.shape[:2]
    for landmarks in pose_result.pose_landmarks:
        for lm in landmarks:
            cx, cy = int(lm.x * w), int(lm.y * h)
            cv2.circle(frame, (cx, cy), 4, (0, 255, 0), -1)
    return frame


def draw_debug_overlay(frame, detections, hand_points, tracker):
    hud_lines = []
    for det in detections:
        x1, y1, x2, y2 = [int(v) for v in det["box"]]
        box_center = ((x1 + x2) // 2, (y1 + y2) // 2)
        threshold = tracker._distance_threshold_for_box(det["box"])
        cv2.circle(frame, box_center, int(threshold), (255, 200, 0), 2)
        cv2.putText(frame, det["label"], (x1, max(y1 - 8, 15)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 200, 0), 2)

        closest_dist = None
        for hand in hand_points:
            hx, hy = int(hand[0]), int(hand[1])
            dist = tracker._hand_object_distance(hand, det["box"])
            color = (0, 255, 0) if dist < threshold else (0, 0, 255)
            cv2.line(frame, (hx, hy), box_center, color, 2)
            if closest_dist is None or dist < closest_dist:
                closest_dist = dist

        if closest_dist is not None:
            status = "TOUCHING" if closest_dist < threshold else "too far"
            hud_lines.append(f"{det['label']}: {int(closest_dist)}/{int(threshold)}px ({status})")

    for i, line in enumerate(hud_lines):
        y = 30 + i * 28
        cv2.rectangle(frame, (10, y - 20), (10 + 9 * len(line), y + 6), (0, 0, 0), -1)
        color = (0, 255, 0) if "TOUCHING" in line else (0, 165, 255)
        cv2.putText(frame, line, (15, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

    return frame


def run_pipeline():
    global latest_jpeg_bytes

    show_window = "--no-window" not in sys.argv
    start_stream_server(port=5005)

    settings = load_settings()

    model_path = FINE_TUNED_MODEL_PATH if os.path.exists(FINE_TUNED_MODEL_PATH) else GENERIC_MODEL_PATH
    print(f"Loading detection model: {model_path}")
    model = YOLO(model_path)

    pose_landmarker = create_pose_landmarker()
    hand_landmarker = create_hand_landmarker()
    pipeline_start_time = time.time()

    if not os.path.exists(PROCEDURE_PATH):
        print(f"ERROR: {PROCEDURE_PATH} not found.")
        return
    tracker = ProcedureTracker(PROCEDURE_PATH)

    try:
        import pyttsx3
        tts = pyttsx3.init()
    except Exception as e:
        print(f"Voice alerts unavailable ({e}); continuing without audio.")
        tts = None

    cam_index = settings.get("camera_index", 0)
    cap = cv2.VideoCapture(cam_index)
    if not cap.isOpened():
        print(f"ERROR: could not open camera at index {cam_index}.")
        return

    os.makedirs(VIDEO_OUTPUT_DIR, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    video_path = os.path.join(VIDEO_OUTPUT_DIR, f"session_{timestamp}.mp4")

    res_w, res_h = settings.get("video_resolution", [1280, 720])
    fps = settings.get("video_fps", 20)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(video_path, fourcc, fps, (res_w, res_h))

    print(f"Recording locally to: {video_path}")
    conf_threshold = settings.get("confidence_threshold", 0.5)
    apply_exposure = settings.get("apply_exposure_fix", True)
    completion_start_time = None

    while True:
        ret, frame = cap.read()
        if not ret:
            print("Camera feed ended or unavailable.")
            break

        frame = cv2.resize(frame, (res_w, res_h))

        if apply_exposure:
            frame = normalize_exposure(frame)

        # --- Object detection ---
        results = model(frame, verbose=False, conf=conf_threshold)
        annotated = results[0].plot()

        detections = []
        for box in results[0].boxes:
            conf = float(box.conf[0])
            if conf < conf_threshold:
                continue
            cls_id = int(box.cls[0])
            label = model.names[cls_id]
            xyxy = box.xyxy[0].tolist()
            detections.append({"label": label, "box": xyxy, "confidence": conf})

        # --- Pose & Hand tracking ---
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        frame_timestamp_ms = int((time.time() - pipeline_start_time) * 1000)

        pose_result = pose_landmarker.detect_for_video(mp_image, frame_timestamp_ms)
        hand_result = hand_landmarker.detect_for_video(mp_image, frame_timestamp_ms)

        annotated = draw_landmarks(annotated, pose_result)
        annotated = draw_hand_landmarks(annotated, hand_result)
        hand_points = get_hand_points_from_hand_model(hand_result, frame.shape)

        if settings.get("show_debug_overlay", True):
            annotated = draw_debug_overlay(annotated, detections, hand_points, tracker)

        # --- Tracking / validation ---
        event = tracker.process_frame(detections, hand_points)
        if event:
            if event["event"] == "step_complete":
                msg = f"Step {event['step']['step_id']} confirmed: {event['step']['description']}"
                print(f"[OK] {msg}")
                next_step = (tracker.procedure[tracker.current_index]
                             if tracker.current_index < len(tracker.procedure) else None)
                if next_step and tts:
                    try:
                        tts.say(f"Next: {next_step['description']}")
                        tts.runAndWait()
                    except Exception:
                        pass
            elif event["event"] == "alert":
                print(f"[ALERT] {event['message']}")
                cv2.putText(annotated, "WRONG STEP: " + event["message"][:60], (20, 40),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

        # --- Termination & Banner Overlay ---
        if tracker.current_index >= len(tracker.procedure):
            if completion_start_time is None:
                completion_start_time = time.time()
                print("[COMPLETE] Experiment complete — all procedure steps verified.")
                if tts:
                    try:
                        tts.say("Procedure complete. All steps verified.")
                        tts.runAndWait()
                    except Exception:
                        pass

            banner_text = "EXPERIMENT COMPLETE - ALL STEPS VERIFIED"
            cv2.rectangle(annotated, (0, annotated.shape[0] - 50), (annotated.shape[1], annotated.shape[0]),
                          (20, 120, 30), -1)
            cv2.putText(annotated, banner_text, (15, annotated.shape[0] - 15),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)

            # Update MJPEG stream buffer
            _, jpeg_buf = cv2.imencode('.jpg', annotated)
            with frame_lock:
                latest_jpeg_bytes = jpeg_buf.tobytes()

            writer.write(annotated)

            if show_window:
                cv2.imshow("AstroGuide - Live Monitoring (ESC to stop)", annotated)
                cv2.waitKey(1)

            if time.time() - completion_start_time > 2.5:
                print("Execution complete. Automatically closing camera window and terminating process.")
                break
        else:
            current_step = tracker.procedure[tracker.current_index]
            banner_text = f"NOW: Step {current_step['step_id']} - {current_step['description']}"
            cv2.rectangle(annotated, (0, annotated.shape[0] - 50), (annotated.shape[1], annotated.shape[0]),
                          (40, 40, 40), -1)
            cv2.putText(annotated, banner_text, (15, annotated.shape[0] - 15),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)

            # Update MJPEG stream buffer for web frontend
            _, jpeg_buf = cv2.imencode('.jpg', annotated)
            with frame_lock:
                latest_jpeg_bytes = jpeg_buf.tobytes()

            writer.write(annotated)

            if show_window:
                cv2.imshow("AstroGuide - Live Monitoring (ESC to stop)", annotated)
                if cv2.waitKey(1) & 0xFF == 27:  # ESC manual stop
                    break

    cap.release()
    writer.release()
    cv2.destroyAllWindows()
    pose_landmarker.close()
    hand_landmarker.close()
    print(f"Session ended cleanly. Video saved to {video_path}")
    print(f"Log saved to outputs/logs/run_log.jsonl")


if __name__ == "__main__":
    run_pipeline()
