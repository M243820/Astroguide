import json
import os
import time
import datetime
from collections import deque
import numpy as np
import threading

STATUS_PATH = "outputs/logs/status.json"
LOG_PATH = "outputs/logs/run_log.jsonl"
SETTINGS_PATH = "configs/settings.json"

try:
    import pyttsx3
    engine = pyttsx3.init()
except Exception:
    engine = None


def load_settings():
    defaults = {
        "relative_distance_factor": 0.6,
        "confidence_threshold": 0.5,
        "required_consecutive_frames": 2,
        "min_approach_delta_px": 3.0,
        "min_motion_speed_px": 1.0,
        "min_proximity_px": 140.0,
        "close_proximity_px": 180.0,
    }
    if os.path.exists(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH, encoding="utf-8") as f:
                defaults.update(json.load(f))
        except (json.JSONDecodeError, OSError):
            pass
    return defaults


class ProcedureTracker:
    """
    Strict real-time procedure validation tracker for 4 steps:
    S1: Take container
    S2: Take item (picking up and holding are the same)
    S3: Insert item into container (fast detection with approach + proximity)
    S4: Close lid (instant confirmation when lid and container overlap or are close enough)
    """

    def __init__(self, procedure_path="procedure.json"):
        with open(procedure_path, encoding="utf-8") as f:
            self.procedure = json.load(f)

        settings = load_settings()

        self.default_min_duration = settings.get("default_min_duration_sec", 0.2)
        self.relative_distance_factor = settings.get("relative_distance_factor", 0.6)
        self.required_consecutive_frames = settings.get("required_consecutive_frames", 2)
        self.min_approach_delta_px = settings.get("min_approach_delta_px", 3.0)
        self.min_motion_speed_px = settings.get("min_motion_speed_px", 1.0)
        self.min_proximity_px = settings.get("min_proximity_px", 140.0)
        self.close_proximity_px = settings.get("close_proximity_px", 180.0)

        self.current_index = 0
        self._consecutive_matches = 0
        self._candidate_step_id = None

        self._completed_steps = set()
        self._active_violations = set()

        # Frame history for fast trajectory analysis (max 10 frames)
        self._history = deque(maxlen=10)

        os.makedirs(os.path.dirname(STATUS_PATH), exist_ok=True)
        try:
            open(LOG_PATH, "w", encoding="utf-8").close()
        except OSError:
            pass
        self._write_status(note="Tracker initialized")

    def _speak(self, text):
        """Sends voice alert as soon as the event occurs without blocking execution."""
        if engine is None:
            return

        def speak_task():
            try:
                engine.say(text)
                engine.runAndWait()
            except Exception:
                pass

        threading.Thread(target=speak_task, daemon=True).start()

    def _center(self, box):
        return ((box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0)

    def _box_area(self, box):
        return max(0.0, box[2] - box[0]) * max(0.0, box[3] - box[1])

    def _box_iou(self, box_a, box_b):
        inter_x1 = max(box_a[0], box_b[0])
        inter_y1 = max(box_a[1], box_b[1])
        inter_x2 = min(box_a[2], box_b[2])
        inter_y2 = min(box_a[3], box_b[3])

        if inter_x1 >= inter_x2 or inter_y1 >= inter_y2:
            return 0.0

        inter_area = (inter_x2 - inter_x1) * (inter_y2 - inter_y1)
        area_a = self._box_area(box_a)
        area_b = self._box_area(box_b)

        denom = area_a + area_b - inter_area
        return inter_area / float(denom) if denom > 0 else 0.0

    def _is_center_inside(self, box_inner, box_outer):
        cx, cy = self._center(box_inner)
        x1, y1, x2, y2 = box_outer
        return (x1 <= cx <= x2) and (y1 <= cy <= y2)

    def _distance_between_boxes(self, box_a, box_b):
        ca = self._center(box_a)
        cb = self._center(box_b)
        return float(np.hypot(ca[0] - cb[0], ca[1] - cb[1]))

    def _hand_object_distance(self, hand_point, box):
        x1, y1, x2, y2 = box
        cx = np.clip(hand_point[0], x1, x2)
        cy = np.clip(hand_point[1], y1, y2)
        return float(np.hypot(hand_point[0] - cx, hand_point[1] - cy))

    def _distance_threshold_for_box(self, box):
        x1, y1, x2, y2 = box
        diag = np.hypot(x2 - x1, y2 - y1)
        return diag * self.relative_distance_factor * 1.3

    def _hand_touching_object(self, hand_points, box):
        threshold = self._distance_threshold_for_box(box)
        for hand in hand_points:
            if self._hand_object_distance(hand, box) < threshold:
                return True
        return False

    def _record_frame_history(self, detections, hand_points):
        frame_data = {
            "timestamp": time.time(),
            "detections": detections,
            "hand_points": hand_points,
            "objects": {},
        }
        for det in detections:
            frame_data["objects"][det["label"]] = det["box"]
        self._history.append(frame_data)

    def _get_object_motion_speed(self, label, lookback=3):
        if len(self._history) < 2:
            return 0.0

        n = min(lookback, len(self._history))
        recent = list(self._history)[-n:]

        start_box = recent[0]["objects"].get(label)
        end_box = recent[-1]["objects"].get(label)

        if not start_box or not end_box:
            return 0.0

        c_start = self._center(start_box)
        c_end = self._center(end_box)
        disp = np.hypot(c_end[0] - c_start[0], c_end[1] - c_start[1])
        num_steps = max(1, n - 1)
        return disp / float(num_steps)

    def _check_approach_behavior(self, label_a, label_b, lookback=3):
        if len(self._history) < 2:
            return False, 0.0, 0.0

        n = min(lookback, len(self._history))
        recent = list(self._history)[-n:]

        distances = []
        for frame in recent:
            b_a = frame["objects"].get(label_a)
            b_b = frame["objects"].get(label_b)
            if b_a and b_b:
                distances.append(self._distance_between_boxes(b_a, b_b))

        if len(distances) < 2:
            return False, 0.0, 0.0

        start_dist = distances[0]
        end_dist = distances[-1]
        delta_dist = start_dist - end_dist

        speed = delta_dist / float(len(distances) - 1)
        is_approaching = delta_dist >= self.min_approach_delta_px or speed >= 0.8

        return is_approaching, delta_dist, speed

    def _verify_s3_insertion(self, detections, hand_points, item_label="item", container_label="container"):
        item_det = next((d for d in detections if d["label"] == item_label), None)
        container_det = next((d for d in detections if d["label"] == container_label), None)

        if not item_det or not container_det:
            return False

        item_box = item_det["box"]
        container_box = container_det["box"]

        dist = self._distance_between_boxes(item_box, container_box)
        iou = self._box_iou(item_box, container_box)
        center_inside = self._is_center_inside(item_box, container_box)
        hand_near_item = self._hand_touching_object(hand_points, item_box)
        hand_near_cont = self._hand_touching_object(hand_points, container_box)

        is_close = center_inside or (iou > 0.02) or (dist < self.min_proximity_px) or hand_near_cont or hand_near_item

        if not is_close:
            return False

        is_approaching, delta_dist, approach_speed = self._check_approach_behavior(item_label, container_label)
        item_speed = self._get_object_motion_speed(item_label)

        has_motion = (item_speed >= self.min_motion_speed_px) or (approach_speed >= 0.5) or hand_near_item

        if not is_approaching and not center_inside and not (iou > 0.15):
            return False

        if not has_motion and not center_inside and iou < 0.1:
            return False

        return True

    def _classify_step_action(self, step, detections, hand_points):
        action = step.get("action", "")
        obj = step.get("object", "")
        near_obj = step.get("near_object", "")

        obj_det = next((d for d in detections if d["label"] == obj), None)

        if action == "pick_up":
            # S1: Take the container
            if not obj_det:
                return False
            hand_near = self._hand_touching_object(hand_points, obj_det["box"])
            motion = self._get_object_motion_speed(obj)
            return hand_near or (motion >= self.min_motion_speed_px)

        elif action == "pick_up_and_hold":
            # S2: Take the item (picking up and holding are the same)
            if not obj_det:
                return False
            hand_near = self._hand_touching_object(hand_points, obj_det["box"])
            motion = self._get_object_motion_speed(obj)

            if not (hand_near or motion >= self.min_motion_speed_px):
                return False

            cont_label = near_obj if near_obj else "container"
            if self._verify_s3_insertion(detections, hand_points, obj, cont_label):
                return False

            return True

        elif action == "insert":
            # S3: Insert item into container
            cont_label = near_obj if near_obj else "container"
            return self._verify_s3_insertion(detections, hand_points, obj, cont_label)

        elif action == "close":
            # S4: Close lid — consider closed SOONER if lid & container overlap or are close enough even for a short while
            if not obj_det:
                return False

            cont_label = near_obj if near_obj else "container"
            cont_det = next((d for d in detections if d["label"] == cont_label), None)

            if not cont_det:
                hand_near = self._hand_touching_object(hand_points, obj_det["box"])
                return hand_near

            hand_near = self._hand_touching_object(hand_points, obj_det["box"])
            iou = self._box_iou(obj_det["box"], cont_det["box"])
            center_inside = self._is_center_inside(obj_det["box"], cont_det["box"])
            dist = self._distance_between_boxes(obj_det["box"], cont_det["box"])
            is_approaching, _, _ = self._check_approach_behavior(obj, cont_label)

            # Container considered closed sooner if bounding boxes overlap (iou > 0.001) OR close enough (dist < close_proximity_px)
            is_closed_sooner = (
                center_inside
                or (iou > 0.001)
                or (dist < self.close_proximity_px)
                or hand_near
                or is_approaching
            )
            return is_closed_sooner

        if obj_det:
            return self._hand_touching_object(hand_points, obj_det["box"])

        return False

    def process_frame(self, detections, hand_points):
        """
        Main validation tick per frame.
        - Sends voice alert AS SOON AS wrong step is detected.
        - S4 lid closure confirms SOONER (1 frame required when overlap or close).
        """
        self._record_frame_history(detections, hand_points)

        if self.current_index >= len(self.procedure):
            self._write_status(note="Experiment complete")
            return None

        expected_step = self.procedure[self.current_index]
        alert_event = None
        current_frame_violations = set()

        # Rule: Lid picked up before S3 completes -> wrong step alert sent IMMEDIATELY
        if self.current_index < 2:  # before Step 3 (Insert item) is completed
            lid_det = next((d for d in detections if d["label"] == "lid"), None)
            if lid_det:
                hand_on_lid = self._hand_touching_object(hand_points, lid_det["box"])
                lid_speed = self._get_object_motion_speed("lid")

                if hand_on_lid or (lid_speed >= 0.8):
                    violation_key = "WRONG_STEP_LID_PICKED_UP"
                    current_frame_violations.add(violation_key)

                    if violation_key not in self._active_violations:
                        message = f"Wrong step. Lid picked up before Step {expected_step['step_id']} ({expected_step['description']}) complete."
                        lid_step = next((s for s in self.procedure if s["object"] == "lid"), expected_step)
                        self._log_event("ALERT_SKIPPED", expected_step, lid_step, message)
                        # Send voice alert IMMEDIATELY
                        self._speak("Wrong step")
                        alert_event = {"event": "alert", "message": message}

        # Generic out-of-order check
        for future_step in self.procedure[self.current_index + 1 :]:
            if self._classify_step_action(future_step, detections, hand_points):
                violation_key = f"OUT_OF_ORDER_{future_step['step_id']}_BEFORE_{expected_step['step_id']}"
                current_frame_violations.add(violation_key)

                if violation_key not in self._active_violations:
                    message = f"Wrong step. Step {future_step['step_id']} ({future_step['description']}) detected before Step {expected_step['step_id']} ({expected_step['description']}) complete."
                    self._log_event("ALERT_SKIPPED", expected_step, future_step, message)
                    # Send voice alert IMMEDIATELY
                    self._speak("Wrong step")
                    alert_event = {"event": "alert", "message": message}

        self._active_violations = current_frame_violations

        if alert_event:
            self._consecutive_matches = 0
            self._write_status(note=f"Violation: {alert_event['message']}")
            return alert_event

        is_step_active = self._classify_step_action(expected_step, detections, hand_points)

        if is_step_active:
            if self._candidate_step_id == expected_step["step_id"]:
                self._consecutive_matches += 1
            else:
                self._candidate_step_id = expected_step["step_id"]
                self._consecutive_matches = 1

            # S4 (Close lid) confirms SOONER (requires only 1 frame match when overlap or close)
            frames_needed = 1 if expected_step.get("action") == "close" else self.required_consecutive_frames

            if self._consecutive_matches >= frames_needed:
                self._completed_steps.add(expected_step["step_id"])
                step_event = {"event": "step_complete", "step": expected_step}
                self._log_event("STEP_COMPLETE", expected_step)

                self.current_index += 1
                self._consecutive_matches = 0
                self._candidate_step_id = None

                self._write_status(note=f"Step {expected_step['step_id']} confirmed: {expected_step['description']}")
                return step_event
            else:
                self._write_status(
                    note=f"Validating Step {expected_step['step_id']} ({self._consecutive_matches}/{frames_needed})"
                )
                return None
        else:
            self._consecutive_matches = 0
            self._candidate_step_id = None
            self._write_status(note=f"Waiting for Step {expected_step['step_id']}: {expected_step['description']}")
            return None

    def _log_event(self, event_type, expected_step, detected_step=None, message=None):
        entry = {
            "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
            "type": event_type,
            "expected_step": expected_step["step_id"],
            "description": expected_step["description"],
        }
        if detected_step:
            entry["detected_step"] = detected_step["step_id"]
        if message:
            entry["message"] = message

        try:
            with open(LOG_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except OSError:
            pass

    def _write_status(self, note=""):
        status = {
            "current_step_index": self.current_index,
            "total_steps": len(self.procedure),
            "current_step": self.procedure[self.current_index] if self.current_index < len(self.procedure) else None,
            "complete": self.current_index >= len(self.procedure),
            "note": note,
            "last_updated": datetime.datetime.now().isoformat(timespec="seconds"),
        }
        try:
            with open(STATUS_PATH, "w", encoding="utf-8") as f:
                json.dump(status, f, indent=2)
        except OSError:
            pass