from pathlib import Path
import hashlib

import pandas as pd
import streamlit as st

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
    for n in names:
        if n.lower() in lookup:
            return lookup[n.lower()]
    for c in df.columns:
        if any(n.lower() in str(c).strip().lower() for n in names):
            return c
    return None

def read_csv(path):
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Could not read {path.name}: {e}")
        return pd.DataFrame()

def save_statuses(mapping):
    pd.DataFrame(
        [{"report_id": key, "status": value} for key, value in mapping.items()],
        columns=["report_id", "status"],
    ).to_csv(STATUS_FILE, index=False)

def count_status(frame, mapping, name):
    if frame.empty or "_report_id" not in frame:
        return 0
    return sum(mapping.get(rid, "Pending") == name for rid in frame["_report_id"])

# Load source detections and identify columns.
detections = read_csv(DETECTIONS_FILE)
detections.columns = [str(c).strip() for c in detections.columns]
time_col = find_col(detections, ["timestamp", "datetime", "time", "date"])
class_col = find_col(detections, ["class_name", "class_id", "class", "label", "hazard", "type"])
confidence_col = find_col(detections, ["confidence", "score", "probability"])
lat_col = find_col(detections, ["latitude", "lat"])
lon_col = find_col(detections, ["longitude", "lon", "lng"])

# Deterministic IDs: existing row IDs remain the same as long as rows are not
# reordered or removed from detections.csv.
if not detections.empty:
    times = detections[time_col].fillna("").astype(str) if time_col else pd.Series([""] * len(detections), index=detections.index)
    labels = detections[class_col].fillna("Unknown").astype(str) if class_col else pd.Series(["Unknown"] * len(detections), index=detections.index)
    detections["_report_id"] = [
        hashlib.sha1(f"{idx}|{times.loc[idx]}|{labels.loc[idx]}|{pos}".encode("utf-8")).hexdigest()[:12]
        for pos, idx in enumerate(detections.index)
    ]
else:
    detections["_report_id"] = pd.Series(dtype=str)

# Load saved report statuses without overwriting the existing status file.
status_df = read_csv(STATUS_FILE)
statuses = {}
if not status_df.empty and {"report_id", "status"}.issubset(status_df.columns):
    statuses = dict(zip(status_df["report_id"].fillna("").astype(str), status_df["status"].fillna("Pending").astype(str)))

# Create display-only incident fields. These are not written into detections.csv.
incidents = detections.copy()
incidents["Report ID"] = incidents["_report_id"]
incidents["Status"] = incidents["_report_id"].map(lambda rid: statuses.get(rid, "Pending"))
if class_col:
    incidents["Hazard / class"] = incidents[class_col].fillna("Unknown").astype(str)
else:
    incidents["Hazard / class"] = "Unknown"
if time_col:
    incidents["Detected at"] = incidents[time_col].fillna("").astype(str)
else:
    incidents["Detected at"] = "Not recorded"
if confidence_col:
    incidents["Confidence"] = pd.to_numeric(incidents[confidence_col], errors="coerce")
else:
    incidents["Confidence"] = pd.NA
if lat_col and lon_col:
    incidents["GPS available"] = (
        pd.to_numeric(incidents[lat_col], errors="coerce").notna()
        & pd.to_numeric(incidents[lon_col], errors="coerce").notna()
    ).map({True: "Yes", False: "No"})
else:
    incidents["GPS available"] = "No"

# Confidence is a model score, not a measure of real-world damage severity.
def confidence_band(value):
    try:
        score = float(value)
    except (TypeError, ValueError):
        return "Unknown"
    if pd.isna(score):
        return "Unknown"
    if score >= 0.80:
        return "High confidence"
    if score >= 0.50:
        return "Medium confidence"
    return "Low confidence"

incidents["Confidence band"] = incidents["Confidence"].apply(confidence_band)

# Sidebar navigation.
with st.sidebar:
    st.markdown("## 🛣️ RoadSense")
    st.caption("CIVICLINK CONTROL CENTER")
    page = st.radio("WORKSPACE", ["Overview", "Incident Management", "Detection History", "Manage Reports", "About"])
    st.divider()
    st.markdown("**System status**")
    st.success("Dashboard online")
    st.caption("Detection log: " + ("Found" if DETECTIONS_FILE.exists() else "Not created yet"))
    if st.button("↻ Refresh data", use_container_width=True):
        st.rerun()

st.markdown("""
<div class="rs-hero">
<div class="rs-eyebrow">ROAD INTELLIGENCE PLATFORM</div>
<div class="rs-title">CivicLink Dashboard</div>
<div class="rs-subtitle">Monitor detections, manage incidents, and track report progress in one workspace.</div>
</div>
""", unsafe_allow_html=True)

total = len(detections)
pending = count_status(detections, statuses, "Pending")
reviewed = count_status(detections, statuses, "Reviewed")
resolved = count_status(detections, statuses, "Resolved")

if page == "Overview":
    st.markdown('<div class="rs-section">Live overview</div>', unsafe_allow_html=True)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total detections", f"{total:,}")
    m2.metric("Awaiting review", f"{pending:,}")
    m3.metric("Reviewed", f"{reviewed:,}")
    m4.metric("Resolved", f"{resolved:,}")
    left, right = st.columns([1.2, .8], gap="large")
    with left:
        st.markdown('<div class="rs-section">Recent detection activity</div>', unsafe_allow_html=True)
        if detections.empty:
            st.info(f"No detections yet. Expected log: {DETECTIONS_FILE}")
        else:
            recent = detections.drop(columns=["_report_id"], errors="ignore").copy()
            if time_col:
                recent = recent.sort_values(time_col, ascending=False, kind="stable")
            st.dataframe(recent.head(8), use_container_width=True, hide_index=True)
            st.caption(f"Latest {min(8, total)} of {total} recorded detections.")
    with right:
        st.markdown('<div class="rs-section">Report workflow</div>', unsafe_allow_html=True)
        st.bar_chart(pd.DataFrame({"Reports": [pending, reviewed, resolved]}, index=["Pending", "Reviewed", "Resolved"]))
        st.caption("Manage report statuses in Incident Management.")
    st.divider()
    st.markdown('<div class="rs-section">GPS incident map</div>', unsafe_allow_html=True)
    if not detections.empty and lat_col and lon_col:
        gps = pd.DataFrame({
            "lat": pd.to_numeric(detections[lat_col], errors="coerce"),
            "lon": pd.to_numeric(detections[lon_col], errors="coerce"),
        }).dropna()
        gps = gps[gps["lat"].between(-90, 90) & gps["lon"].between(-180, 180)]
        if not gps.empty:
            st.map(gps, latitude="lat", longitude="lon")
        else:
            st.info("GPS columns are present, but valid coordinates have not been recorded yet.")
    else:
        st.info("The map will show incident locations when valid GPS coordinates are available.")

elif page == "Incident Management":
    st.markdown('<div class="rs-section">Incident management</div>', unsafe_allow_html=True)
    st.caption("Search, filter, inspect, and update reports. Incident fields shown here are derived from detections.csv; the original detection log is not edited.")

    if incidents.empty:
        st.info("No incidents are recorded yet. Run the RoadSense detector to create detection records.")
    else:
        f1, f2, f3 = st.columns([1.2, 1, 1])
        search_text = f1.text_input("Search incidents", placeholder="Class, timestamp, report ID…")
        status_filter = f2.selectbox("Filter by status", ["All", "Pending", "Reviewed", "Resolved"])
        confidence_filter = f3.selectbox("Filter by confidence", ["All", "High confidence", "Medium confidence", "Low confidence", "Unknown"])

        filtered = incidents.copy()
        if search_text:
            searchable = filtered.astype(str).apply(
                lambda col: col.str.contains(search_text, case=False, na=False)
            ).any(axis=1)
            filtered = filtered[searchable]
        if status_filter != "All":
            filtered = filtered[filtered["Status"] == status_filter]
        if confidence_filter != "All":
            filtered = filtered[filtered["Confidence band"] == confidence_filter]

        k1, k2, k3 = st.columns(3)
        k1.metric("Matching incidents", len(filtered))
        k2.metric("Pending in view", int((filtered["Status"] == "Pending").sum()))
        k3.metric("GPS available in view", int((filtered["GPS available"] == "Yes").sum()))

        display_cols = ["Report ID", "Detected at", "Hazard / class", "Confidence", "Confidence band", "GPS available", "Status"]
        st.dataframe(filtered[display_cols], use_container_width=True, hide_index=True, height=380)

        st.divider()
        st.markdown("#### Update an incident")
        filtered_ids = filtered["_report_id"].tolist()
        if not filtered_ids:
            st.info("No incidents match those filters. Clear the filters to select a report.")
        else:
            def format_incident(rid):
                row = incidents[incidents["_report_id"] == rid].iloc[0]
                return f"{row['Hazard / class']} • {row['Detected at']} • {rid}"

            selected_id = st.selectbox("Select incident", filtered_ids, format_func=format_incident)
            status_options = ["Pending", "Reviewed", "Resolved"]
            old_status = statuses.get(selected_id, "Pending")
            new_status = st.selectbox(
                "New status",
                status_options,
                index=status_options.index(old_status) if old_status in status_options else 0,
            )
            if st.button("Save incident status", type="primary"):
                updated = dict(statuses)
                updated[selected_id] = new_status
                try:
                    save_statuses(updated)
                    st.success(f"Incident {selected_id} saved as {new_status}.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Could not save status: {exc}")

elif page == "Detection History":
    st.markdown('<div class="rs-section">Detection history</div>', unsafe_allow_html=True)
    st.caption("Raw records read from detections.csv.")
    if detections.empty:
        st.info(f"No records found. Expected file: {DETECTIONS_FILE}")
    else:
        query = st.text_input("Search detection history", placeholder="Search class, timestamp, confidence…")
        view = detections.drop(columns=["_report_id"], errors="ignore").copy()
        if query:
            mask = view.astype(str).apply(lambda col: col.str.contains(query, case=False, na=False)).any(axis=1)
            view = view[mask]
        st.metric("Matching records", len(view))
        st.dataframe(view, use_container_width=True, hide_index=True, height=440)

elif page == "Manage Reports":
    st.markdown('<div class="rs-section">Manage report statuses</div>', unsafe_allow_html=True)
    st.caption("This page retains the familiar status update workflow.")
    if incidents.empty:
        st.info("No reports are available until detections are recorded.")
    else:
        st.dataframe(incidents[["Report ID", "Hazard / class", "Detected at", "Status"]], use_container_width=True, hide_index=True, height=300)
        ids = incidents["_report_id"].tolist()
        def report_label(rid):
            row = incidents[incidents["_report_id"] == rid].iloc[0]
            return f"{row['Hazard / class']} • {row['Detected at']} • {rid}"
        chosen = st.selectbox("Select a report", ids, format_func=report_label)
        options = ["Pending", "Reviewed", "Resolved"]
        current = statuses.get(chosen, "Pending")
        new_status = st.selectbox("Report status", options, index=options.index(current) if current in options else 0)
        if st.button("Save status", type="primary"):
            updated = dict(statuses)
            updated[chosen] = new_status
            try:
                save_statuses(updated)
                st.success(f"Report {chosen} saved as {new_status}.")
                st.rerun()
            except Exception as exc:
                st.error(f"Could not save report status: {exc}")

else:
    st.markdown('<div class="rs-section">About CivicLink</div>', unsafe_allow_html=True)
    st.write("CivicLink is the monitoring and incident-management interface for RoadSense.")
    st.markdown("- `civiclink.py` — dashboard interface\n- `detections.csv` — detection log from the camera pipeline\n- `report_status.csv` — saved status for each report")
    st.warning("Confidence bands describe model confidence only. They do not measure the physical severity of a pothole. This dashboard does not automatically submit reports to a government authority.")

try:
    from streamlit_autorefresh import st_autorefresh
    st_autorefresh(interval=10000, key="roadsense_incident_refresh")
except ImportError:
    st.caption("Auto-refresh extension is unavailable; use Refresh data.")
