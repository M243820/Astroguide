import base64
import datetime
import json
import os
import signal
import subprocess
import sys
import time
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

# -------------------------------------------------------------------
# Path Anchoring (Guarantees stability regardless of launch directory)
# -------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

STATUS_PATH = os.path.join(BASE_DIR, "outputs", "logs", "status.json")
LOG_PATH = os.path.join(BASE_DIR, "outputs", "logs", "run_log.jsonl")
PROCEDURE_PATH = os.path.join(BASE_DIR, "procedure.json")
SETTINGS_PATH = os.path.join(BASE_DIR, "configs", "settings.json")
BG_IMAGE_CANDIDATES = [
    os.path.join(BASE_DIR, "attached_assets", "bg3_1788771360260.png"),
    os.path.join(BASE_DIR, "assets", "bg3.png"),
    os.path.join(os.path.expanduser("~"), "Downloads", "bg3.png"),
]
BG_IMAGE_PATH = next((path for path in BG_IMAGE_CANDIDATES if os.path.exists(path)), BG_IMAGE_CANDIDATES[0])
LOWER_BG_IMAGE_PATH = os.path.join(BASE_DIR, "assets", "bg4.png")
PID_PATH = os.path.join(BASE_DIR, "outputs", "logs", "pipeline.pid")

st.set_page_config(
    page_title="AstroGuide",
    layout="wide",
    page_icon="🛰️",
    initial_sidebar_state="collapsed",
)

# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------

def load_json(path, default=None):
    if not os.path.exists(path):
        return default
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return default


def load_log_lines(path):
    if not os.path.exists(path):
        return []

    entries = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    except OSError:
        pass

    return entries


def is_recent(iso_timestamp, seconds=15):
    if not iso_timestamp:
        return False
    try:
        ts = datetime.datetime.fromisoformat(iso_timestamp)
        now = datetime.datetime.now(ts.tzinfo) if ts.tzinfo else datetime.datetime.now()
        return (now - ts).total_seconds() < seconds
    except (ValueError, TypeError):
        return False


def get_base64_image(path):
    if not os.path.exists(path):
        return ""
    try:
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    except OSError:
        return ""


def is_pipeline_process_running():
    if "pipeline_proc" in st.session_state:
        proc = st.session_state["pipeline_proc"]
        if proc and proc.poll() is None:
            return True

    if os.path.exists(PID_PATH):
        try:
            with open(PID_PATH, "r") as f:
                pid = int(f.read().strip())
            os.kill(pid, 0)
            return True
        except (OSError, ValueError):
            try:
                os.remove(PID_PATH)
            except OSError:
                pass
    return False


def stop_pipeline_process():
    if "pipeline_proc" in st.session_state:
        proc = st.session_state["pipeline_proc"]
        if proc and proc.poll() is None:
            proc.terminate()
        st.session_state.pop("pipeline_proc", None)

    if os.path.exists(PID_PATH):
        try:
            with open(PID_PATH, "r") as f:
                pid = int(f.read().strip())
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True)
            else:
                os.kill(pid, signal.SIGTERM)
        except Exception:
            pass
        try:
            os.remove(PID_PATH)
        except OSError:
            pass

    if sys.platform == "win32":
        try:
            subprocess.run(
                ["powershell", "-Command", "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*main_pipeline.py*' } | Stop-Process -Force"],
                capture_output=True,
                timeout=3,
            )
        except Exception:
            pass


# -------------------------------------------------------------------
# Space Theme Styling
# -------------------------------------------------------------------

st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Space+Grotesk:wght@400;500;600;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Space Grotesk', sans-serif;
}

.stApp {
    background:
        linear-gradient(180deg, #ede6d6 0%, #ede6d6 100%);
    color: #3a342e;
}

.block-container {
    max-width: 1240px;
    padding-top: 1.2rem;
    padding-bottom: 3rem;
}

#MainMenu, footer, header {
    visibility: hidden;
}

[data-testid="stAppViewContainer"] {
    background: transparent;
}

[data-testid="stVerticalBlock"] {
    gap: 0.65rem;
}

[data-testid="stDataFrame"] {
    border: 1px solid rgba(184, 175, 156, .72);
    border-radius: 14px;
    overflow: hidden;
    box-shadow: 0 14px 40px rgba(0, 0, 0, .26);
}

[data-testid="stMarkdownContainer"] p,
[data-testid="stCaptionContainer"] {
    color: #5c564d;
}

/* Navigation */
.navbar {
    height: 54px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 18px;
    margin-bottom: 42px;
    border: 1px solid rgba(184, 175, 156, .80);
    border-radius: 17px;
    background: rgba(237, 230, 214, .88);
    box-shadow: 0 10px 28px rgba(58, 52, 46, .08), inset 0 1px rgba(255,255,255,.65);
    backdrop-filter: blur(10px);
}

.nav-brand {
    font-size: 14px;
    font-weight: 700;
    color: #3a342e;
    letter-spacing: .8px;
    text-transform: uppercase;
}

.nav-brand span {
    color: #c9a55c;
}

.nav-links {
    display: flex;
    gap: 24px;
}

.nav-link {
    color: #5c564d;
    font-size: 12px;
    text-decoration: none;
    font-weight: 500;
    transition: color 0.2s;
}

.nav-link:hover, .nav-link.active {
    color: #3a342e;
}

.nav-right {
    display: flex;
    align-items: center;
    gap: 12px;
    font-size: 11px;
}

.nav-status {
    padding: 6px 12px;
    border-radius: 999px;
    background: rgba(184,175,156,.16);
    color: #5c564d;
    font-weight: 600;
    letter-spacing: .6px;
}

.nav-status.live {
    color: #3a342e;
    background: rgba(201, 165, 92, .18);
    border: 1px solid rgba(201, 165, 92, .62);
    box-shadow: none;
}

/* Hero */
.hero-shell {
    position: relative;
    overflow: hidden;
    margin: 0 -1.2rem;
    min-height: 500px;
    display: flex;
    flex-direction: column;
    justify-content: flex-end;
    padding: 42px 1.2rem 46px;
    border-top: 1px solid rgba(184, 175, 156, .45);
    border-bottom: 1px solid rgba(184, 175, 156, .45);
    background: #101722;
}

.hero-shell > * {
    position: relative;
    z-index: 1;
}

.hero-brand-title {
    max-width: 560px;
    margin: 0 0 80px auto;
    color: #ede6d6;
    font-size: clamp(34px, 5vw, 68px);
    font-weight: 700;
    letter-spacing: 3px;
    line-height: 1;
    text-align: right;
    text-transform: uppercase;
    text-shadow: 0 0 14px rgba(201, 165, 92, .46);
}

.hero-title {
    max-width: 560px;
    margin: 0 0 12px auto;
    font-size: clamp(24px, 3.2vw, 40px);
    line-height: 1.05;
    font-weight: 600;
    letter-spacing: -1.8px;
    color: #ede6d6;
    text-align: right;
    text-shadow: 0 12px 44px rgba(0,0,0,.28);
}

.hero-title .accent {
    color: #c9a55c;
    text-decoration: underline;
    text-decoration-color: rgba(201, 165, 92, .70);
    text-decoration-thickness: 2px;
    text-underline-offset: 8px;
}

.hero-sub {
    max-width: 500px;
    margin: 16px 0 0 auto;
    padding-top: 6px;
    color: #ede6d6;
    font-size: 13px;
    line-height: 1.7;
    text-align: right;
}

.hero-meta {
    display: flex;
    justify-content: flex-end;
    flex-wrap: wrap;
    gap: 9px;
    margin-top: 22px;
}

.hero-chip {
    padding: 7px 11px;
    border: 1px solid rgba(237, 230, 214, .34);
    border-radius: 999px;
    color: #ede6d6;
    background: rgba(16, 23, 34, .46);
    font-family: 'DM Mono', monospace;
    font-size: 10px;
    letter-spacing: .35px;
}

.hero-chip strong {
    color: #c9a55c;
    font-weight: 500;
}

.session-status-card {
    min-height: 0;
    width: min(100%, 440px);
    padding: 11px 15px;
    margin-top: 0;
}

.session-status-card .card-text {
    line-height: 1.35;
}

.procedure-toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    margin: 2px 0 16px;
}

.procedure-hint {
    color: #5c564d;
    font-size: 12px;
}

.procedure-link {
    display: inline-block;
    padding: 8px 12px;
    border: 1px solid #b8af9c;
    border-radius: 9px;
    color: #3a342e !important;
    background: transparent;
    font-size: 12px;
    font-weight: 600;
    text-decoration: none !important;
}

.procedure-link:hover {
    border-color: #3a342e;
    background: rgba(184, 175, 156, .16);
}

/* Sections */
.section {
    padding: 45px 0 15px;
}

.section-kicker {
    color: #c9a55c;
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 2.5px;
    margin-bottom: 8px;
}

.section-title {
    color: #3a342e;
    font-size: 29px;
    font-weight: 600;
    letter-spacing: -0.5px;
    margin-bottom: 8px;
}

.section-copy {
    color: #5c564d;
    font-size: 13px;
    line-height: 1.6;
    max-width: 650px;
}

/* Cards */
.card {
    min-height: 150px;
    padding: 21px;
    border-radius: 18px;
    border: 1px solid rgba(184, 175, 156, .72);
    background: rgba(237, 230, 214, .60);
    box-shadow: 0 12px 30px rgba(58,52,46,.08), inset 0 1px rgba(255,255,255,.55);
    backdrop-filter: blur(7px);
    transition: transform .2s ease, border-color .2s ease, box-shadow .2s ease;
}

.card:hover {
    transform: translateY(-3px);
    border-color: rgba(201, 165, 92, .82);
    box-shadow: 0 16px 36px rgba(58,52,46,.13);
}

.card-icon {
    width: 39px;
    height: 39px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 12px;
    background: rgba(201, 165, 92, .12);
    border: 1px solid rgba(201, 165, 92, .45);
    color: #3a342e;
    font-size: 17px;
    margin-bottom: 12px;
}

.card-title {
    color: #3a342e;
    font-size: 16px;
    font-weight: 600;
    margin-bottom: 6px;
}

.card-text {
    color: #5c564d;
    font-size: 13px;
    line-height: 1.6;
}

/* Step cards */
.step {
    padding: 13px 16px;
    margin-bottom: 8px;
    border-radius: 13px;
    border: 1px solid rgba(184, 175, 156, .68);
    background: rgba(237, 230, 214, .44);
    color: #5c564d;
    font-size: 12px;
    transition: all .2s ease;
}

.step.current {
    background: rgba(201, 165, 92, .12);
    border-color: rgba(201, 165, 92, .78);
    color: #3a342e;
    box-shadow: inset 3px 0 #c9a55c;
}

.step.done {
    color: #6f5a2e;
    opacity: .85;
}

.alert-box {
    background: rgba(184, 175, 156, .18);
    border: 1px solid rgba(184, 175, 156, .82);
    padding: 12px 15px;
    border-radius: 12px;
    color: #3a342e;
    font-size: 12px;
    margin-top: 10px;
}

/* Streamlit button custom styles */
div.st-key-launch_pipeline_btn > button {
    background: transparent !important;
    color: #3a342e !important;
    font-weight: 700 !important;
    font-size: 15px !important;
    letter-spacing: .25px !important;
    font-family: 'Space Grotesk', sans-serif !important;
    border: 1px solid #b8af9c !important;
    padding: 11px 25px !important;
    border-radius: 13px !important;
    box-shadow: 0 5px 16px rgba(58, 52, 46, .08) !important;
    transition: all 0.2s ease !important;
}

div.st-key-launch_pipeline_btn > button:hover {
    transform: translateY(-2px);
    background: rgba(184, 175, 156, .16) !important;
    border-color: #3a342e !important;
    box-shadow: 0 8px 20px rgba(58, 52, 46, .12) !important;
}

div.st-key-stop_pipeline_btn > button {
    background: transparent !important;
    border: 1px solid #b8af9c !important;
    color: #3a342e !important;
    font-weight: 700 !important;
    border-radius: 10px !important;
}

div.st-key-stop_pipeline_btn > button:hover {
    background: rgba(184, 175, 156, .16) !important;
    border-color: #3a342e !important;
    color: #3a342e !important;
}

[data-testid="stSlider"] [role="slider"] {
    background: #3a1616 !important;
    border-color: #3a342e !important;
    box-shadow: 0 0 0 4px rgba(58,22,22,.16) !important;
}

[data-testid="stSlider"] [data-baseweb="slider"] > div > div {
    background: #3a1616 !important;
}

[data-testid="stCheckbox"] label span {
    color: #5c564d !important;
}

[data-testid="stCheckbox"] [role="checkbox"] {
    border-color: #3a1616 !important;
}

[data-testid="stCheckbox"] [role="checkbox"][aria-checked="true"] {
    background-color: #3a1616 !important;
    border-color: #3a1616 !important;
}

[data-testid="stCheckbox"] input,
[data-testid="stSlider"] input[type="range"] {
    accent-color: #3a1616 !important;
}

div.stDownloadButton > button,
div.stFormSubmitButton > button {
    border: 1px solid #b8af9c !important;
    border-radius: 10px !important;
    color: #3a342e !important;
    background: transparent !important;
}

div.stDownloadButton > button:hover,
div.stFormSubmitButton > button:hover {
    border-color: #3a342e !important;
    color: #3a342e !important;
    background: rgba(184, 175, 156, .16) !important;
}

.footer {
    text-align: center;
    padding: 45px 0 10px;
    color: #5c564d;
    font-size: 11px;
}

div.st-key-lower_page {
    position: relative;
    isolation: isolate;
    margin: 0 -1.2rem;
    padding: 0 1.2rem 1rem;
}

div.st-key-lower_page::before {
    content: "";
    position: absolute;
    z-index: -1;
    inset: 0 -100vw;
    background-color: #ede6d6;
    background-image: var(--lower-page-bg, none);
    background-position: center top;
    background-size: auto;
    background-repeat: no-repeat;
    pointer-events: none;
}
</style>
""",
    unsafe_allow_html=True,
)

bg_data = get_base64_image(BG_IMAGE_PATH)
if bg_data:
    st.markdown(
        f"""
        <style>
        .hero-shell {{
            background:
                linear-gradient(180deg, rgba(16, 23, 34, .34), rgba(16, 23, 34, .52)),
                url("data:image/png;base64,{bg_data}") !important;
            background-size: cover !important;
            background-position: center center !important;
            background-repeat: no-repeat !important;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )

lower_bg_data = get_base64_image(LOWER_BG_IMAGE_PATH)
if lower_bg_data:
    st.markdown(
        f"""
        <style>
        :root {{
            --lower-page-bg: url("data:image/png;base64,{lower_bg_data}");
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )

# -------------------------------------------------------------------
# Navigation
# -------------------------------------------------------------------

initial_status = load_json(STATUS_PATH)
pipeline_live_init = initial_status is not None and is_recent(initial_status.get("last_updated"), seconds=15)
status_text = "● LIVE" if pipeline_live_init else "○ OFFLINE"
live_class = "live" if pipeline_live_init else ""

st.markdown(
    f"""<div class="navbar">
 <div class="nav-brand">✦ Astro<span>Guide</span></div>
<div class="nav-links">
     <a href="/" class="nav-link active">Dashboard</a>
     <a href="/Procedure_Editor" target="_self" class="nav-link">Procedure Editor</a>
</div>
<div class="nav-right">
    <span class="nav-status {live_class}">{status_text}</span>
</div>
</div>""",
    unsafe_allow_html=True,
)

# -------------------------------------------------------------------
# Hero
# -------------------------------------------------------------------

st.markdown(
    f"""<div class="hero-shell">

<div class="hero-brand-title">AstroGuide</div>

<div class="hero-title">
    See every <span class="accent">mission step</span><br>
    before it becomes a risk.
</div>

<div class="hero-sub">
    AstroGuide monitors the camera feed, verifies procedures in sequence,
    and logs every interaction locally on your device without transmitting data outside.
</div>

</div>""",
    unsafe_allow_html=True,
)

st.markdown("<div style='margin-top: 18px;'></div>", unsafe_allow_html=True)

# -------------------------------------------------------------------
# Pipeline Controller
# -------------------------------------------------------------------

is_running = is_pipeline_process_running() or pipeline_live_init

col_b1, col_b2, col_b3 = st.columns([1.3, 1.4, 1.3])
with col_b2:
    if not is_running:
        if st.button("Launch Monitoring", key="launch_pipeline_btn", use_container_width=True):
            script_path = os.path.join(BASE_DIR, "src", "pipeline", "main_pipeline.py")
            if os.path.exists(script_path):
                try:
                    os.makedirs(os.path.join(BASE_DIR, "outputs", "logs"), exist_ok=True)
                    proc = subprocess.Popen(
                        [sys.executable, script_path, "--no-window"],
                        cwd=BASE_DIR,
                    )
                    st.session_state["pipeline_proc"] = proc
                    with open(PID_PATH, "w") as f:
                        f.write(str(proc.pid))
                    st.toast("Vision pipeline started! Camera initializing...")
                    st.session_state["scroll_to_live"] = True
                    time.sleep(1.2)
                    st.rerun()
                except Exception as e:
                    st.error(f"Error starting pipeline: {e}")
            else:
                st.error(f"Cannot find pipeline script at: {script_path}")
    else:
        btn_stop, btn_stat = st.columns([1.1, 1.1])
        with btn_stop:
            if st.button("Stop Pipeline", key="stop_pipeline_btn", use_container_width=True):
                stop_pipeline_process()
                st.toast("Pipeline stopped.")
                time.sleep(0.8)
                st.rerun()
        with btn_stat:
            st.markdown(
                '<div style="text-align:center; padding:9px 12px; background:rgba(82,220,117,0.14); '
                'border:1px solid rgba(82,220,117,0.3); border-radius:10px; color:#baffc1; font-weight:700; '
                'font-size:12px; height:42px; display:flex; align-items:center; justify-content:center;">'
                '● Pipeline Active</div>',
                unsafe_allow_html=True,
            )

# -------------------------------------------------------------------
# System Overview Cards
# -------------------------------------------------------------------

st.markdown(
    """
<div class="section">
    <div class="section-kicker">SYSTEMS ONLINE</div>
    <div class="section-title">A calm interface for critical work</div>
    <div class="section-copy">
        Autonomous, offline computer-vision monitoring for critical aerospace procedures.
        The vision and tracking pipeline runs independently while the dashboard displays real-time telemetry.
    </div>
</div>
""",
    unsafe_allow_html=True,
)

feature_cols = st.columns(4)
features = [
    ("👁️", "Visual Intelligence", "YOLOv8 object detection paired with hand tracking."),
    ("✓", "Sequence Lock", "Confirms each procedure step in the correct order."),
    ("◉", "Contact Proof", "Filters brief proximity with hold-frame logic."),
    ("▣", "Private Flight Record", "Timestamped telemetry stays on this device."),
]

for col, (_, title, text) in zip(feature_cols, features):
    with col:
        st.markdown(
            f"""
<div class="card">
    <div class="card-title">{title}</div>
    <div class="card-text">{text}</div>
</div>
""",
            unsafe_allow_html=True,
        )

# -------------------------------------------------------------------
# Experiment Steps
# -------------------------------------------------------------------

st.markdown(
    """
<div class="section">
    <div class="section-kicker">PROCEDURE</div>
    <div class="section-title">Experiment Steps</div>
</div>
""",
    unsafe_allow_html=True,
)

st.markdown(
    """
<div class="procedure-toolbar">
    <span class="procedure-hint">Follow the configured sequence in order.</span>
    <a class="procedure-link" href="/Procedure_Editor" target="_self">Open Procedure Editor ↗</a>
</div>
""",
    unsafe_allow_html=True,
)

# -------------------------------------------------------------------
# Live Section (Self-Refreshing Fragment)
# -------------------------------------------------------------------

@st.fragment(run_every=2)
def render_live_telemetry():
    status = load_json(STATUS_PATH)
    procedure = load_json(PROCEDURE_PATH, default=[])
    log_entries = load_log_lines(LOG_PATH)
    pipeline_live = status is not None and is_recent(status.get("last_updated"), seconds=15)

    if not pipeline_live:
        st.info(
            "The monitoring pipeline is currently offline. You can click "
            "**'Launch Monitoring'** above to start it, "
        )

    if not procedure:
        st.warning("No procedure loaded. Go to the Procedure Editor page to create one.")
    else:
        current_index = status.get("current_step_index", 0) if status else 0
        for i, step in enumerate(procedure):
            label = f"Step {step.get('step_id', i+1)}: {step.get('description', '')}"
            if i < current_index:
                cls, prefix, suffix = "step done", "✓", ""
            elif i == current_index:
                cls, prefix, suffix = "step current", "▶", " <i>(current)</i>"
            else:
                cls, prefix, suffix = "step", "○", ""
            st.markdown(f'<div class="{cls}">{prefix}&nbsp;&nbsp; {label}{suffix}</div>', unsafe_allow_html=True)

        if status and status.get("complete"):
            st.success("Experiment complete — all steps confirmed in order.")

    st.markdown(
        """
        <div class="section" style="padding-top:30px;">
            <div class="section-kicker">COMMAND CENTER</div>
            <div id="live-experiment-monitoring" class="section-title">Live experiment monitoring</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    main_col = st.container()
    side_col = st.container()

    with main_col:
        if pipeline_live:
            st.markdown(
                """<div style="border-radius: 14px; overflow: hidden; border: 1px solid rgba(143,145,255,0.25); background: #070520; box-shadow: 0 10px 30px rgba(0,0,0,0.35); margin-bottom: 22px;">
    <div style="padding: 8px 14px; background: rgba(30,19,103,0.7); display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid rgba(255,255,255,0.08);">
        <span style="font-size: 11px; font-weight: 700; color: #baffc1; letter-spacing: 0.5px;">● LIVE STREAM (30 FPS)</span>
        <span style="font-size: 10px; color: #c9c5e8;">YOLOv8 Detection + MediaPipe Tracking</span>
    </div>
    <img id="astroguide-live-feed"
         src="http://127.0.0.1:5005/video_feed" 
         onerror="this.onerror=null; this.src='http://127.0.0.1:5005/snapshot?t=' + Date.now();"
         style="width: 100%; display: block; aspect-ratio: 16/9; object-fit: cover; background: #000;" 
         alt="AstroGuide Live Vision Feed" />
</div>""",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                """<div style="border-radius: 14px; border: 1px dashed rgba(255,255,255,0.15); background: rgba(255,255,255,0.02); padding: 42px 20px; text-align: center; margin-bottom: 22px;">
    <div style="font-size: 34px; margin-bottom: 8px;">📷</div>
    <div style="font-weight: 600; color: #fff; font-size: 13px; margin-bottom: 4px;">Camera Feed Standby</div>
    <div style="color: #8f8ba8; font-size: 11px;">Click <b>Launch Monitoring Pipeline</b> above to activate the live vision stream.</div>
</div>""",
                unsafe_allow_html=True,
            )

        if log_entries:
            last_entry = log_entries[-1]
            if last_entry.get("type") == "ALERT_SKIPPED" and is_recent(last_entry.get("timestamp"), seconds=8):
                st.markdown(
                    f"""<div class="alert-box">🔊 <b>Voice Alert:</b> {last_entry.get("message", "")}</div>""",
                    unsafe_allow_html=True,
                )

        st.markdown("### Timestamped Telemetry Log")
        if log_entries:
            df = pd.DataFrame(log_entries)
            cols = [c for c in ["timestamp", "type", "expected_step", "detected_step", "description", "message"] if c in df.columns]
            st.dataframe(df[cols].iloc[::-1], use_container_width=True, hide_index=True, height=240)
            log_text = "\n".join(json.dumps(e) for e in log_entries)
            st.download_button("Download full log (.jsonl)", log_text, file_name="astroguide_log.jsonl", key="dl_log_btn")
        else:
            st.caption("No steps logged yet for this session.")

    with side_col:
        st.markdown("### Session Status")
        note = status.get("note", "Waiting — no interaction detected") if status else "Standby (Pipeline Offline)"
        raw_steps = status.get("total_steps", len(procedure)) if status else len(procedure)
        total_steps = len(raw_steps) if isinstance(raw_steps, list) else raw_steps
        last_updated = status.get("last_updated", "-") if status else "-"

        st.markdown(
            f"""<div class="card session-status-card">
    <div class="card-title">Mission Status</div>
    <div class="card-text">
        <div style="color:#ffffff; font-weight:600; margin-bottom:2px;">Status Note</div>
        <div style="margin-bottom:12px;">{note}</div>
        <div style="color:#ffffff; font-weight:600; margin-bottom:2px;">Configured Steps</div>
        <div style="margin-bottom:12px;">{total_steps}</div>
        <div style="color:#ffffff; font-weight:600; margin-bottom:2px;">Last Heartbeat</div>
        <div>{last_updated}</div>
    </div>
</div>""",
            unsafe_allow_html=True,
        )

        st.caption(f"Telemetry synced: {datetime.datetime.now().strftime('%H:%M:%S')}")


render_live_telemetry()

with st.container(key="lower_page"):
    # -------------------------------------------------------------------
    # Configuration & Settings Section
    # -------------------------------------------------------------------

    st.markdown(
        """
    <div class="section">
        <div class="section-kicker">TUNE THE SYSTEM</div>
        <div class="section-title">Detection & tracking settings</div>
        <div class="section-copy">
            Configure tracking parameters for hand-object proximity, hold frame thresholds, and camera exposure correction.
        </div>
    </div>
    """,
        unsafe_allow_html=True,
    )

    settings = load_json(SETTINGS_PATH, default={})

    with st.form("settings_form"):
        c1, c2 = st.columns(2)

        with c1:
            dist = st.slider(
                "Hand-object proximity factor",
                0.2,
                1.5,
                float(settings.get("relative_distance_factor", 0.6)),
                step=0.05,
                help="Multiplier of the detected object's bounding box size for touch radius.",
            )

            hold = st.slider(
                "Minimum hold frames",
                1,
                40,
                int(settings.get("required_consecutive_frames", 2)),
                help="Consecutive frames an interaction must persist to confirm step completion.",
            )

        with c2:
            conf = st.slider(
                "Detection confidence threshold",
                0.1,
                0.95,
                float(settings.get("confidence_threshold", 0.5)),
                help="Minimum YOLOv8 confidence score to register an object.",
            )

            exposure_fix = st.checkbox(
                "Apply automatic lighting correction",
                value=settings.get("apply_exposure_fix", True),
                help="Evens out harsh specular glare and deep shadows before running inference.",
            )

            show_debug = st.checkbox(
                "Render debug overlay on stream",
                value=settings.get("show_debug_overlay", True),
                help="Draws proximity thresholds and hand-to-object lines directly on the stream.",
            )

        saved = st.form_submit_button("Save Settings")

        if saved:
            new_settings = {
                **settings,
                "relative_distance_factor": dist,
                "required_consecutive_frames": hold,
                "confidence_threshold": conf,
                "apply_exposure_fix": exposure_fix,
                "show_debug_overlay": show_debug,
            }

            os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok=True)
            with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
                json.dump(new_settings, f, indent=2)

            st.success("✅ Settings saved successfully. They will apply to new pipeline frames automatically.")

    # -------------------------------------------------------------------
    # Footer
    # -------------------------------------------------------------------

    st.markdown(
        """
    <div class="footer">
        🛰️ AstroGuide · Offline AI Experiment Monitoring<br>
        Video is recorded locally in <b>outputs/videos/</b> and never leaves this device.
    </div>
    """,
        unsafe_allow_html=True,
    )

if st.session_state.pop("scroll_to_live", False):
    components.html(
        """
        <script>
        (() => {
            const scrollToLiveSection = () => {
                const target = window.parent.document.getElementById("live-experiment-monitoring");
                if (target) {
                    target.scrollIntoView({ behavior: "smooth", block: "start" });
                }
            };

            setTimeout(scrollToLiveSection, 350);
        })();
        </script>
        """,
        height=1,
    )