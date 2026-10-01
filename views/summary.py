"""views/summary.py — Summary tab"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from data import OBJECTS, STEP_DEFS, MOCK1_RESULTS, EXT_NUM_OBJECTS, PREREQ_OBJECTS


def render_summary(db, user):
    st.subheader("📊 Migration Summary")

    all_status = db.get_all_status()
    active_blockers = db.get_blockers()

    # ── Status breakdown ───────────────────────────────────────────────────────
    status_counts = {"Not Started": 0, "In Progress": 0, "Completed": 0, "Blocked": 0}
    module_stats = {}

    for obj in OBJECTS:
        oid = obj["id"]
        s = all_status.get(oid, {}).get("status", "Not Started")
        if oid in active_blockers:
            status_counts["Blocked"] += 1
        else:
            status_counts[s] = status_counts.get(s, 0) + 1

        mod = obj["module"]
        if mod not in module_stats:
            module_stats[mod] = {"total": 0, "done": 0, "m1_loaded": 0, "m1_source": 0}
        module_stats[mod]["total"] += 1
        if s == "Completed":
            module_stats[mod]["done"] += 1
        m1 = MOCK1_RESULTS.get(oid, {})
        if m1.get("loaded"):
            module_stats[mod]["m1_loaded"] += m1["loaded"]
        if m1.get("loaded") is not None and m1.get("errors") is not None:
            module_stats[mod]["m1_source"] += m1["loaded"] + m1["errors"]

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("##### Object Status")
        fig = px.pie(
            values=list(status_counts.values()),
            names=list(status_counts.keys()),
            color=list(status_counts.keys()),
            color_discrete_map={
                "Completed": "#2E7D32",
                "In Progress": "#F57F17",
                "Not Started": "#9E9E9E",
                "Blocked": "#C62828",
            },
            hole=0.4,
        )
        fig.update_layout(height=280, margin=dict(t=0, b=0))
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.markdown("##### Mock 1 Results by Module")
        mod_rows = []
        for mod, stats in module_stats.items():
            pct = round(stats["m1_loaded"] / stats["m1_source"] * 100, 1) if stats["m1_source"] else 0
            mod_rows.append({
                "Module": mod,
                "Objects": stats["total"],
                "M1 Loaded": f"{stats['m1_loaded']:,}",
                "M1 Source": f"{stats['m1_source']:,}",
                "M1 Rate": f"{pct}%",
            })
        st.dataframe(pd.DataFrame(mod_rows), use_container_width=True, hide_index=True)

    st.markdown("---")

    # ── Mock 1 results table ───────────────────────────────────────────────────
    st.markdown("##### Mock 1 Results — Full Object List")
    rows = []
    for obj in OBJECTS:
        oid = obj["id"]
        m1 = MOCK1_RESULTS.get(oid, {})
        loaded = m1.get("loaded")
        errors = m1.get("errors")
        rate = m1.get("rate", "—")
        note = m1.get("note", "")
        db_st = all_status.get(oid, {})
        m2_loaded = db_st.get("m1_loaded")
        m2_errors = db_st.get("m1_errors")
        rows.append({
            "DM-ID": oid,
            "Object": obj["name"],
            "Module": obj["module"],
            "M1 Posted": f"{loaded:,}" if loaded is not None else "—",
            "M1 Source": f"{(loaded or 0)+(errors or 0):,}" if loaded is not None else "—",
            "M1 Rate": rate,
            "M2 Posted": f"{m2_loaded:,}" if m2_loaded else "—",
            "M2 Errors": f"{m2_errors:,}" if m2_errors else "—",
            "Mock 1 Note": note[:80] + "…" if len(note) > 80 else note,
        })

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)

    st.markdown("---")

    # ── Audit log ──────────────────────────────────────────────────────────────
    st.markdown("##### Recent Activity Log")
    audit = db.get_audit(limit=30)
    if audit:
        audit_rows = [
            {
                "Time": r["at"][:16] if r.get("at") else "",
                "User": r.get("by_user", ""),
                "Object": r.get("obj_id", ""),
                "Action": r.get("action", ""),
                "Detail": r.get("detail", ""),
            }
            for r in audit
        ]
        st.dataframe(pd.DataFrame(audit_rows), use_container_width=True, hide_index=True)
    else:
        st.caption("No activity recorded yet.")
