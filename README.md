# AstroGuide

Offline AI experiment-monitoring system. Watches a camera feed, recognizes
hand-object interactions against a predefined procedure, and alerts (voice +
on-screen + log) if a step is skipped or done out of order. Runs fully
locally — no internet or cloud dependency required.

## How the pieces fit together (read this first)

This project is **two separate programs that talk through shared files**,
not one single script:

1. **`src/pipeline/main_pipeline.py`** — owns the camera. Runs YOLO object
   detection + MediaPipe hand/pose tracking + the sequence tracker. Opens
   its own video window (OpenCV). Writes live status to
   `outputs/logs/status.json` and events to `outputs/logs/run_log.jsonl`.
2. **`app.py`** — the Streamlit dashboard. It does NOT touch the camera —
   it just reads and displays the files that (1) is writing, refreshing
   every couple seconds.

Run them in **two separate terminals**, at the same time.

## One-time setup

```bash
pip install -r requirements.txt
```

## Step-by-step: build the object detector

1. Collect photos of your experiment objects (see project chat history /
   team notes for the exact shot list used).
2. Label them in Roboflow, export in **YOLOv8 format**, and place the
   resulting `train/valid/test` folders under `data/annotations/`.
3. Update `configs/data.yaml` so `names:` lists your actual object classes
   in the same order Roboflow assigned them, and the `train:`/`val:` paths
   point at your exported folders.
4. Train:
   ```bash
   python src/detection/train_yolo.py
   ```
5. When training finishes, copy the resulting weights file into the path
   the pipeline expects:
   ```bash
   mkdir -p models/yolo
   cp runs/detect/train/weights/best.pt models/yolo/best.pt
   ```
   If `models/yolo/best.pt` doesn't exist, `main_pipeline.py` will fall
   back to the generic pretrained YOLO model (won't recognize your custom
   objects — you'll see a warning printed when you run it).

## Step-by-step: define the experiment procedure

1. In a terminal:
   ```bash
   streamlit run app.py
   ```
2. In the sidebar, open the **Procedure Editor** page.
3. Add one row per step (description, object, action, minimum duration).
   The **Object** dropdown only offers classes your trained model actually
   knows — this is intentional, it prevents defining a step the vision
   system has no way to detect.
4. Click **Save Procedure** — this writes `procedure.json` at the project
   root, which is what the pipeline reads.

## Step-by-step: run a live monitoring session

**Terminal 1:**
```bash
streamlit run app.py
```
Leave this running — it's your dashboard, open the local URL it prints in
your browser.

**Terminal 2:**
```bash
python src/pipeline/main_pipeline.py
```
This opens a video window showing the live annotated camera feed. Perform
the experiment steps in front of the camera. The dashboard (Terminal 1's
browser tab) will update automatically — step tracker, alerts, and log
table all update live as the pipeline detects progress.

Press **ESC** in the video window to stop the session. The recorded video
is saved to `outputs/videos/`, and the full event log is in
`outputs/logs/run_log.jsonl`.

## Tuning detection (if it's too strict or too lenient)

On the dashboard's right-hand panel, under **Detection Settings**, you can
adjust:
- **Hand-object distance threshold** — how close a hand must be to an
  object to count as touching it.
- **Minimum hold frames** — how long an interaction must be held before
  it's trusted (filters out brief, accidental contact).
- **Confidence threshold** — minimum YOLO confidence to trust a detection.
- **Lighting correction** — toggles automatic exposure/contrast
  normalization (helps with harsh or uneven lighting).

Changes are saved to `configs/settings.json`. **Restart
`main_pipeline.py`** after changing settings for them to take effect.

## Troubleshooting

- **"could not open camera"** — try changing `camera_index` in
  `configs/settings.json` (0, 1, 2...) if you have multiple cameras.
- **No sound on alerts** — some systems need a system-level TTS voice
  installed for `pyttsx3` to work; the pipeline will still run and log
  alerts even if audio fails, it just prints a warning.
- **Dashboard says OFFLINE** — means `main_pipeline.py` isn't running, or
  hasn't written a status update in the last 15 seconds. Check Terminal 2
  for errors.
- **Detections seem wrong/inconsistent** — usually means the model needs
  more/better labeled training images, or the distance/hold thresholds
  need tuning for your specific camera distance and lighting.

## Project structure

```
AstroGuide/
├── data/               # raw photos, processed frames, Roboflow annotations
├── models/yolo/        # trained detector weights (best.pt) go here
├── src/
│   ├── detection/       # dataset prep + training scripts
│   ├── tracking/        # tracker.py — the rule-based state machine
│   └── pipeline/        # main_pipeline.py — the live camera/AI loop
├── pages/               # Streamlit multi-page dashboard pages
├── configs/             # data.yaml (training), settings.json (tuning)
├── outputs/             # session videos and logs
├── procedure.json       # the currently active experiment sequence
├── app.py               # dashboard entry point
└── requirements.txt
```
