from pathlib import Path
import hashlib

import pandas as pd
import streamlit as st
from supabase import create_client

# RoadSense CivicLink — Live Incident Management
BASE_DIR = Path(__file__).resolve().parent
DETECTIONS_FILE = BASE_DIR / "detections.csv"
STATUS_FILE = BASE_DIR / "report_status.csv"

st.set_page_config(page_title="RoadSense | CivicLink", page_icon="🛣️", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Space+Grotesk:wght@500;600;700&display=swap');
.stApp{background:radial-gradient(ellipse at 10% 0%,#162b42 0%,#08111f 45%);color:#e7edf5;font-family:'DM Sans',sans-serif}
[data-testid="stSidebar"]{background:#0b1625;border-right:1px solid #26364b}
.block-container{max-width:1500px;padding-top:1.4rem;padding-bottom:2rem}
h1,h2,h3{font-family:'Space Grotesk',sans-serif!important;letter-spacing:-.03em}
[data-testid="stMetric"]{background:linear-gradient(145deg,#142338,#0e1929);border:1px solid #26364b;border-radius:16px;padding:17px}
[data-testid="stMetricLabel"]{color:#a7b6c9!important}
[data-testid="stMetricValue"]{color:#f3f7fb!important;font-family:'Space Grotesk',sans-serif}
div[data-testid="stDataFrame"]{border:1px solid #26364b;border-radius:12px;overflow:hidden}
div.stButton>button{border-radius:10px;font-weight:600;min-height:2.5rem}
.rs-hero{padding:24px 26px;border:1px solid #29415a;border-radius:20px;background:linear-gradient(120deg,#1b354d,#0d1c2d);margin:6px 0 22px}
.rs-eyebrow{color:#43d9bd;text-transform:uppercase;letter-spacing:.15em;font-size:.72rem;font-weight:700;margin-bottom:8px}
.rs-title{font-family:'Space Grotesk',sans-serif;font-size:1.8rem;font-weight:700;color:#f5f8fc;margin-bottom:8px}
.rs-subtitle{color:#a8b8ca;font-size:.96rem}
.rs-section{font-family:'Space Grotesk',sans-serif;font-size:1.15rem;font-weight:600;margin:8px 0 12px}
hr{border-color:#23344a!important}
</style>
""", unsafe_allow_html=True)


def find_col(df, names):
    if df.empty:
        return None
    lookup = {str(c).strip().lower(): c for c in df.columns}
    for name in names:
        if name.lower() in lookup:
            return lookup[name.lower()]
    for col in df.columns:
        if any(name.lower() in str(col).strip().lower() for name in names):
            return col
    return None


def read_csv(path):
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()
    except Exception as exc:
        st.error(f"Could not read {path.name}: {exc}")
        return pd.DataFrame()


def count_status(frame, mapping, name):
    if frame.empty or "_report_id" not in frame:
        return 0
    return sum(mapping.get(rid, "Pending") == name for rid in frame["_report_id"])


def load_detections():
    """Prefer shared Supabase records; use local CSV if cloud settings are absent."""
    try:
        url = st.secrets.get("SUPABASE_URL", "")
        key = st.secrets.get("SUPABASE_KEY", "")
    except Exception:
        url, key = "", ""

    if url and key:
        try:
            client = create_client(url, key)
            response = (
                client.table("detections")
                .select("id,source_id,timestamp,class_id,confidence,latitude,longitude,status")
                .order("timestamp", desc=True)
                .execute()
            )
            frame = pd.DataFrame(response.data or [])
            return frame, "Supabase"
        except Exception as exc:
            st.warning(f"Could not load Supabase data; showing local CSV if available. Details: {exc}")

    return read_csv(DETECTIONS_FILE), "Local CSV"


def save_status(report_id, new_status, db_id=None):
    """Persist cloud status when the row came from Supabase; otherwise save locally."""
    try:
        url = st.secrets.get("SUPABASE_URL", "")
