    left, right = st.columns([1.2, .8], gap="large")
    with left:
        st.markdown('<div class="rs-section">Recent detection activity</div>', unsafe_allow_html=True)
        if detections.empty:
            st.info("No detections yet. Once your laptop syncs records to Supabase, they will appear here.")
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
    st.caption("Search, filter, inspect, and update reports.")
    if incidents.empty:
        st.info("No incidents are recorded yet. Sync detections from the RoadSense laptop first.")
    else:
        f1, f2, f3 = st.columns([1.2, 1, 1])
        search_text = f1.text_input("Search incidents", placeholder="Class, timestamp, report ID…")
        status_filter = f2.selectbox("Filter by status", ["All", "Pending", "Reviewed", "Resolved"])
        confidence_filter = f3.selectbox("Filter by confidence", ["All", "High confidence", "Medium confidence", "Low confidence", "Unknown"])
        filtered = incidents.copy()
        if search_text:
            filtered = filtered[filtered.astype(str).apply(lambda col: col.str.contains(search_text, case=False, na=False)).any(axis=1)]
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
            new_status = st.selectbox("New status", status_options, index=status_options.index(old_status) if old_status in status_options else 0)
            if st.button("Save incident status", type="primary"):
                try:
                    row = incidents[incidents["_report_id"] == selected_id].iloc[0]
                    db_id = row[db_id_col] if db_id_col else None
                    saved_to = save_status(selected_id, new_status, db_id=db_id)
                    st.success(f"Incident {selected_id} saved as {new_status} ({saved_to}).")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Could not save incident status: {exc}")

elif page == "Detection History":
    st.markdown('<div class="rs-section">Detection history</div>', unsafe_allow_html=True)
    st.caption(f"Records loaded from {data_source}.")
    if detections.empty:
        st.info("No records found yet. Sync the laptop detection log to Supabase.")
    else:
        query = st.text_input("Search detection history", placeholder="Search class, timestamp, confidence…")
        view = detections.drop(columns=["_report_id"], errors="ignore").copy()
        if query:
            view = view[view.astype(str).apply(lambda col: col.str.contains(query, case=False, na=False)).any(axis=1)]
        st.metric("Matching records", len(view))
        st.dataframe(view, use_container_width=True, hide_index=True, height=440)

elif page == "Manage Reports":
    st.markdown('<div class="rs-section">Manage report statuses</div>', unsafe_allow_html=True)
    st.caption("Update incident status. Cloud records are saved to Supabase.")
    if incidents.empty:
        st.info("No reports are available until detections are synced.")
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
            try:
                row = incidents[incidents["_report_id"] == chosen].iloc[0]
                db_id = row[db_id_col] if db_id_col else None
                saved_to = save_status(chosen, new_status, db_id=db_id)
                st.success(f"Report {chosen} saved as {new_status} ({saved_to}).")
                st.rerun()
            except Exception as exc:
                st.error(f"Could not save report status: {exc}")

else:
    st.markdown('<div class="rs-section">About CivicLink</div>', unsafe_allow_html=True)
    st.write("CivicLink is the monitoring and incident-management interface for RoadSense.")
    st.markdown("- `civiclink.py` — dashboard interface\n- Supabase `detections` table — shared detection records\n- `detections.csv` — local detector log used for syncing")
    st.warning("Confidence bands describe model confidence only, not physical pothole severity. This dashboard does not automatically submit reports to a government authority.")

try:
    from streamlit_autorefresh import st_autorefresh
    st_autorefresh(interval=10000, key="roadsense_incident_refresh")
except ImportError:
    st.caption("Auto-refresh extension is unavailable; use Refresh data.")
