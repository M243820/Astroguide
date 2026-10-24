# AstroGuide

**Real-Time Computer Vision Telemetry & Autonomous Procedure Verification System**

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Streamlit](https://img.shields.io/badge/Frontend-Streamlit-FF4B4B.svg)](https://streamlit.io/)
[![YOLOv8](https://img.shields.io/badge/Vision-YOLOv8-00FFFF.svg)](https://ultralytics.com/)
[![MediaPipe](https://img.shields.io/badge/Pose%20%26%20Hand-MediaPipe-orange.svg)](https://developers.google.com/mediapipe)
[![HTTP Streaming](https://img.shields.io/badge/Live%20Streaming-HTTP%20MJPEG-green.svg)](#real-time-mjpeg-video-streaming-port-5005)
[![License: CC BY 4.0](https://img.shields.io/badge/License-CC%20BY%204.0-lightgrey.svg)](https://creativecommons.org/licenses/by/4.0/)

AstroGuide is an offline, full-stack computer vision monitoring system designed for mission-critical aerospace and laboratory procedures. It pairs fine-tuned **YOLOv8 object detection** and **MediaPipe hand landmark tracking** with a rule-based **temporal state verification engine**, presented through a custom **real-time web telemetry dashboard** with embedded live HTTP video streaming.

---

##  Key Highlights

- **Edge-First & Fully Offline:** Zero cloud or external API dependencies. All inference, video recording, and state validation run strictly locally on device.
- **Embedded Web Video Streaming:** Live 30 FPS annotated vision stream delivered directly to the browser via a dedicated **HTTP MJPEG multipart server (port 5005)**.
- **Strict Physical Interaction (Presence ≠ Action):** Rejects false positives caused by static bounding box co-presence or random jitter; requires intentional velocity and hand-object contact.
- **Early Insertion Detection:** Confirms insertion intent early through trajectory analysis (decreasing distance delta $\Delta d$ over time) without requiring deep occluding bounding box overlap.
- **Single-Trigger Voice Alerts:** Low-latency auditory warning system (pyttsx3) that triggers **exactly once per violation event** (e.g. lid picked up before sample insertion is completed) to avoid audio flooding.
- **Automatic Lifecycle Termination:** Automatically completes the session, saves recordings locally, and cleanly terminates camera feeds upon successful verification of all procedure steps.

---

##  System Architecture

`
                      +---------------------------------------+
                      |       Physical Camera Feed (30 FPS)   |
                      +---------------------------------------+
                                          |
                                          v
                      +---------------------------------------+
                      |         Preprocessing & Exposure      |
                      |          Normalization Engine         |
                      +---------------------------------------+
                                          |
                        +-----------------+-----------------+
                        |                                   |
                        v                                   v
             +--------------------+               +--------------------+
             |  YOLOv8 Detection  |               |    MediaPipe 21-Pt |
             |   (Objects: Vial,  |               |     Hand Landmark  |
             |   Container, Lid)  |               |     Tracking Model |
             +--------------------+               +--------------------+
                        |                                   |
                        +-----------------+-----------------+
                                          |
                                          v
                      +---------------------------------------+
                      |       ProcedureTracker State Machine  |
                      |   - Approach Trajectory Analysis      |
                      |   - Holding vs Insertion Logic        |
                      |   - Step Order & Out-of-Order Alerts  |
                      +---------------------------------------+
                                 |                 |
                   (Live Frame)  v                 v  (State & Events)
             +-----------------------+       +-------------------------+
             | HTTP MJPEG Server     |       | JSON Telemetry Stream   |
             | Port 5005 (/video)    |       | outputs/logs/status.json|
             +-----------------------+       +-------------------------+
                         |                                |
                         +---------------+----------------+
                                         |
                                         v
                      +---------------------------------------+
                      |       AstroGuide Streamlit Web UI     |
                      |  - Space Grotesk Custom Theme         |
                      |  - Responsive Live Video Feed (MJPEG) |
                      |  - Dynamic 2s Telemetry Polling       |
                      |  - Interactive Procedure Editor       |
                      |  - Subprocess Lifecycle Controller    |
                      +---------------------------------------+
`

---

## Web & Frontend Engineering Highlights

While the backend processes computer vision and spatial geometry, the web frontend provides a mission-control command center built with advanced web engineering practices:

### 1. Real-Time MJPEG Video Streaming (Port 5005)
Rather than writing frames to disk and reading them back (which introduces disk I/O bottlenecks and UI lag), the vision pipeline hosts a lightweight, threaded **HTTP MJPEG server**:
- Endpoint GET /video_feed serves multipart/x-mixed-replace; boundary=frame.
- Endpoint GET /snapshot provides instant static frame captures for low-bandwidth environments.
- The web dashboard embeds the stream with dynamic client-side fallback handling (localhost vs 127.0.0.1 cross-origin resolution).

### 2. Custom Space-Themed Design System
- Built with custom CSS injection utilizing Google Fonts (**Space Grotesk** for headings, **DM Mono** for telemetry data).
- Glassmorphism surfaces, custom slider/checkbox control accents (#4A1F1F, #C9A55C), and responsive column layouts (1.75 : 1.25 split view).
- Multi-page routing integrating the main Command Center with the **Procedure Editor**.

### 3. Reactive Self-Refreshing Telemetry Fragments
- Employs Streamlit's @st.fragment(run_every=2) to isolate telemetry updates.
- Real-time step progress, status badges, and JSONL log tables refresh asynchronously every 2 seconds without reloading or flickering the main page DOM.

### 4. Web-Driven Subprocess Lifecycle Management
- Launch and terminate the native camera vision pipeline directly from the browser UI.
- Implements cross-platform PID tracking (pipeline.pid), process polling, and clean tree termination (	askkill on Windows / SIGTERM on Unix).

---

## The 4-Step Validated Sequence

AstroGuide validates procedures in strict physical sequence:

| Step | Action | Object | Validation Rules |
| :---: | :---: | :---: | :--- |
| **S1** | **Take Container** | container | Hand contact with container + intentional displacement ( \ge 1.5\text{ px/frame}$). |
| **S2** | **Take & Hold Item** | item | Hand contact with sample item. Retains **Holding** state even near container until approach motion is verified. |
| **S3** | **Insert Item** | item $\rightarrow$ container | **Early detection**: Decreasing distance delta ($\Delta d \ge 6\text{ px}$), directional velocity, and container proximity. Deep overlap not required. |
| **S4** | **Close Lid** | lid $\rightarrow$ container | **Closed sooner**: Confirms in 1 frame as soon as lid and container overlap or touch. Triggers automatic session completion. |

> **Out-of-Order Rule:** If the lid is picked up before S3 (Insert Item) is completed, a low-latency voice alert (**"Wrong step"**) is immediately dispatched once.

---

## Repository Structure

`
AstroGuide/
├── app.py                      # Main Streamlit web dashboard & telemetry frontend
├── main.py                     # Root CLI entrypoint to launch vision pipeline
├── procedure.json              # Configured active procedure sequence (S1-S4)
├── requirements.txt            # Python dependencies
├── configs/
│   ├── data.yaml               # YOLOv8 class definition & dataset mapping
│   └── settings.json           # Proximity thresholds, hold frames, & camera index
├── src/
│   ├── pipeline/
│   │   └── main_pipeline.py    # Camera engine, MediaPipe tracking, & HTTP stream server
│   ├── tracking/
│   │   └── tracker.py          # State machine, approach trajectory & sequence rules
│   └── detection/
│       ├── train_yolo.py       # YOLOv8 fine-tuning script
│       ├── exposure_fix.py     # Automatic adaptive histogram/exposure equalization
│       ├── extract_frames.py   # Dataset video frame extractor
│       └── synth_compose.py    # Synthetic dataset augmentation tool
├── pages/
│   └── 01_Procedure_Editor.py  # In-browser procedure step editor
├── models/
│   └── yolo/best.pt            # Fine-tuned YOLOv8 custom weights
├── outputs/
│   ├── videos/
│   │   └── sample_demo.mp4     # Sample verified session video
│   └── logs/
│       └── sample_run_log.jsonl# Sample timestamped session telemetry
└── assets/                     # UI visual assets and background images
`

---

## Quickstart Guide

### 1. Prerequisites
- Python 3.10+
- Webcam or USB video input device

### 2. Installation
`ash
git clone https://github.com/M243820/Astroguide.git
cd Astroguide
python -m venv venv
# Windows:
.\venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

pip install -r requirements.txt
`

### 3. Launching the System

#### Option A: Launch from the Web Dashboard (Recommended)
`ash
streamlit run app.py
`
Open the local URL displayed in your terminal (typically http://localhost:8501). Click **"Launch Monitoring"** at the top of the dashboard. The camera feed will stream directly inside the web interface!

#### Option B: Standalone Terminal Execution
`ash
# Terminal 1 (Frontend):
streamlit run app.py

# Terminal 2 (Vision Pipeline):
python main.py
`

---

## Sample Outputs & Telemetry

- **Live Demonstration Video:** Watch [outputs/videos/sample_demo.mp4](outputs/videos/sample_demo.mp4) to see real-time object bounding boxes, hand tracking centroids, proximity HUD, and sequential step transitions.
- **Structured Telemetry Log:** View [outputs/logs/sample_run_log.jsonl](outputs/logs/sample_run_log.jsonl) for sample JSONL timestamped events:
  `json
  {"timestamp": "2026-09-08T09:49:03", "type": "STEP_COMPLETE", "expected_step": 1, "description": "Take the container"}
  {"timestamp": "2026-09-08T09:49:11", "type": "ALERT_SKIPPED", "expected_step": 2, "description": "Take the item", "detected_step": 4, "message": "Wrong step. Lid picked up before Step 2 (Take the item) complete."}
  {"timestamp": "2026-09-08T09:49:18", "type": "STEP_COMPLETE", "expected_step": 2, "description": "Take the item"}
  {"timestamp": "2026-09-08T09:49:19", "type": "STEP_COMPLETE", "expected_step": 3, "description": "Insert the item into the container"}
  {"timestamp": "2026-09-08T09:49:25", "type": "STEP_COMPLETE", "expected_step": 4, "description": "Close the lid onto the container"}
  `

---

## Tech Stack & Dependencies

- **Frontend & UI:** Streamlit, HTML5, Custom CSS3 (Space Grotesk, DM Mono)
- **Networking & Streaming:** HTTP MJPEG, multipart/x-mixed-replace, Python http.server, Threading
- **Object Detection:** Ultralytics YOLOv8 (PyTorch)
- **Pose & Hand Tracking:** Google MediaPipe Tasks API
- **Computer Vision:** OpenCV (cv2), NumPy
- **Speech Synthesis:** pyttsx3
- **Data Management:** Pandas, JSON / JSONL

---

##  License
This project is open-source under the [Creative Commons Attribution 4.0 International License (CC BY 4.0)](https://creativecommons.org/licenses/by/4.0/).
