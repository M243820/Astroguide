import json
import os

import pandas as pd
import streamlit as st


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROCEDURE_PATH = os.path.join(BASE_DIR, "procedure.json")

PAGE_BG = "#EDE6D6"
CHARCOAL = "#3A342E"
MUTED = "#5C564D"
TAUPE = "#B8AF9C"
GOLD = "#C9A55C"
MAROON = "#4A1F1F"


st.set_page_config(
    page_title="Procedure Editor · AstroGuide",
    page_icon="🛰️",
    layout="wide",
    initial_sidebar_state="expanded",
)


def load_procedure():
    if not os.path.exists(PROCEDURE_PATH):
        return []

    try:
        with open(PROCEDURE_PATH, encoding="utf-8") as procedure_file:
            data = json.load(procedure_file)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def procedure_rows(procedure):
    rows = []
    for index, step in enumerate(procedure):
        rows.append(
            {
                "Description": step.get("description", ""),
                "Object": step.get("object", ""),
                "Action": step.get("action", ""),
                "Min. duration (sec)": step.get(
                    "min_duration_sec",
                    step.get("min_duration", 1),
                ),
            }
        )
    return rows


def save_procedure(edited_rows, original_procedure):
    saved_steps = []

    for index, row in enumerate(edited_rows):
        description = str(row.get("Description", "") or "").strip()
        object_name = str(row.get("Object", "") or "").strip()
        action = str(row.get("Action", "") or "").strip()

        try:
            duration = max(0, int(row.get("Min. duration (sec)", 0) or 0))
        except (TypeError, ValueError):
            duration = 0

        # Preserve any additional fields used by the vision pipeline.
        existing = (
            dict(original_procedure[index])
            if index < len(original_procedure) and isinstance(original_procedure[index], dict)
            else {}
        )
        existing.update(
            {
                "step_id": index + 1,
                "description": description,
                "object": object_name,
                "action": action,
                "min_duration_sec": duration,
            }
        )
        saved_steps.append(existing)

    os.makedirs(os.path.dirname(PROCEDURE_PATH), exist_ok=True)
    with open(PROCEDURE_PATH, "w", encoding="utf-8") as procedure_file:
        json.dump(saved_steps, procedure_file, indent=2)

    return saved_steps


st.markdown(
    f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Space+Grotesk:wght@400;500;600;700&display=swap');

    html, body, [class*="css"] {{
        font-family: 'Space Grotesk', sans-serif;
    }}

    .stApp {{
        background: {PAGE_BG};
        color: {CHARCOAL};
    }}

    [data-testid="stAppViewContainer"],
    [data-testid="stHeader"] {{
        background: transparent;
    }}

    [data-testid="stSidebar"] {{
        background: rgba(237, 230, 214, .86);
        border-right: 1px solid rgba(184, 175, 156, .62);
    }}

    [data-testid="stSidebarNav"] a {{
        color: {MUTED};
        border-radius: 8px;
    }}

    [data-testid="stSidebarNav"] a:hover,
    [data-testid="stSidebarNav"] a[aria-current="page"] {{
        color: {CHARCOAL};
        background: rgba(184, 175, 156, .28);
    }}

    .page-wrap {{
        max-width: 980px;
        margin: 0 auto;
        padding: 26px 0 46px;
    }}

    .page-kicker {{
        color: {GOLD};
        font: 500 10px 'DM Mono', monospace;
        letter-spacing: 2.3px;
        text-transform: uppercase;
        margin-bottom: 10px;
    }}

    .page-title {{
        color: {CHARCOAL};
        font-size: clamp(34px, 4vw, 48px);
        line-height: 1;
        letter-spacing: -1.8px;
        font-weight: 700;
        margin: 0 0 9px;
    }}

    .page-subtitle {{
        color: {MUTED};
        font-size: 13px;
        line-height: 1.6;
        margin: 0;
    }}

    .editor-section {{
        margin-top: 48px;
    }}

    .editor-section-title {{
        color: {CHARCOAL};
        font-size: 26px;
        letter-spacing: -.7px;
        font-weight: 600;
        margin: 0 0 9px;
    }}

    .editor-copy {{
        max-width: 760px;
        color: {MUTED};
        font-size: 13px;
        line-height: 1.65;
        margin-bottom: 17px;
    }}

    [data-testid="stDataEditor"] {{
        overflow: hidden;
        border: 1px solid rgba(184, 175, 156, .82);
        border-radius: 12px;
        background: rgba(255, 252, 244, .52);
        box-shadow: 0 12px 28px rgba(58, 52, 46, .07);
    }}

    [data-testid="stDataEditor"] [role="columnheader"] {{
        background: rgba(184, 175, 156, .18);
        color: {CHARCOAL};
    }}

    div.stButton > button,
    div.stDownloadButton > button {{
        min-height: 39px;
        border: 1px solid {TAUPE} !important;
        border-radius: 9px !important;
        color: {CHARCOAL} !important;
        background: transparent !important;
        font-family: 'Space Grotesk', sans-serif !important;
        font-size: 13px !important;
        font-weight: 600 !important;
        letter-spacing: .15px;
        box-shadow: none !important;
    }}

    div.stButton > button:hover,
    div.stDownloadButton > button:hover {{
        color: {CHARCOAL} !important;
        border-color: {CHARCOAL} !important;
        background: rgba(184, 175, 156, .18) !important;
    }}

    [data-testid="stAlert"] {{
        border: 1px solid rgba(184, 175, 156, .75);
        background: rgba(184, 175, 156, .18);
        color: {CHARCOAL};
    }}

    .editor-note {{
        color: {MUTED};
        font-size: 11px;
        line-height: 1.5;
        margin-top: 12px;
    }}

    @media (max-width: 760px) {{
        .page-wrap {{
            padding: 22px 0 36px;
        }}

        .editor-section {{
            margin-top: 36px;
        }}
    }}
    </style>
    """,
    unsafe_allow_html=True,
)


st.markdown('<div class="page-kicker">ASTROGUIDE / CONFIGURATION</div>', unsafe_allow_html=True)
st.markdown('<h1 class="page-title">Procedure Editor</h1>', unsafe_allow_html=True)
st.markdown('<p class="page-subtitle">Define the experiment steps AstroGuide should monitor — no coding required.</p>', unsafe_allow_html=True)

st.markdown('<div class="editor-section">', unsafe_allow_html=True)
st.markdown('<h2 class="editor-section-title">Steps</h2>', unsafe_allow_html=True)
st.markdown(
    '<p class="editor-copy">Add one row per step, in the order they should be performed. '
    'AstroGuide checks these in sequence and alerts if a step is skipped or done out of order.</p>',
    unsafe_allow_html=True,
)


original_procedure = load_procedure()
if not original_procedure:
    original_procedure = [
        {
            "step_id": 1,
            "description": "Take the container",
            "object": "container",
            "action": "pick_up",
            "min_duration_sec": 1,
        },
        {
            "step_id": 2,
            "description": "Take the item",
            "object": "item",
            "action": "pick_up_and_hold",
            "min_duration_sec": 1,
        },
        {
            "step_id": 3,
            "description": "Insert the item into the container",
            "object": "item",
            "near_object": "container",
            "action": "insert",
            "min_duration_sec": 1,
        },
        {
            "step_id": 4,
            "description": "Close the lid onto the container",
            "object": "lid",
            "near_object": "container",
            "action": "close",
            "min_duration_sec": 1,
        },
    ]


edited_table = st.data_editor(
    pd.DataFrame(procedure_rows(original_procedure)),
    key="procedure_editor_table",
    num_rows="dynamic",
    use_container_width=True,
    hide_index=True,
    column_config={
        "Description": st.column_config.TextColumn(
            "Description",
            help="What should happen in this step?",
            width="large",
            required=True,
        ),
        "Object": st.column_config.TextColumn(
            "Object",
            help="The item or object involved.",
            width="medium",
        ),
        "Action": st.column_config.TextColumn(
            "Action",
            help="The action AstroGuide should detect.",
            width="medium",
        ),
        "Min. duration (sec)": st.column_config.NumberColumn(
            "Min. duration (sec)",
            help="Minimum time the action must be held.",
            min_value=0,
            step=1,
            format="%d",
            width="small",
        ),
    },
)


st.markdown(
    '<p class="editor-note">Drag rows to keep the procedure in the order it should be performed.</p>',
    unsafe_allow_html=True,
)

button_col, download_col = st.columns([1, 1.45])
with button_col:
    if st.button("Save Procedure", use_container_width=True):
        rows = edited_table.to_dict("records") if hasattr(edited_table, "to_dict") else edited_table
        save_procedure(rows, original_procedure)
        st.success("Procedure saved successfully.")

with download_col:
    current_rows = (
        edited_table.to_dict("records")
        if hasattr(edited_table, "to_dict")
        else edited_table
    )
    download_rows = []
    for index, row in enumerate(current_rows):
        download_rows.append(
            {
                "step_id": index + 1,
                "description": str(row.get("Description", "") or "").strip(),
                "object": str(row.get("Object", "") or "").strip(),
                "action": str(row.get("Action", "") or "").strip(),
                "min_duration_sec": int(row.get("Min. duration (sec)", 0) or 0),
            }
        )

    st.download_button(
        "Download current procedure.json",
        data=json.dumps(download_rows, indent=2),
        file_name="procedure.json",
        mime="application/json",
        use_container_width=True,
    )
st.markdown('</div>', unsafe_allow_html=True)
