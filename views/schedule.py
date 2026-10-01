"""views/schedule.py — Schedule reference tab"""

import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timezone
from data import OBJECTS, MOCK1_RESULTS, OBJ_DEPS, STEP_DEFS

M1_SCHEDULE = {
    "DM-055": {"exv": "Sep 14 00:00", "upv": "Sep 14 15:30", "wave": "W2"},
    "DM-042": {"exv": "Sep 14 03:00", "upv": "Sep 15 02:00", "wave": "W3"},
    "DM-025": {"exv": "Sep 11 07:30", "upv": "Sep 14 23:30", "wave": "W3"},
    "DM-018": {"exv": "Sep 11 06:00", "upv": "Sep 15 00:30", "wave": "W3"},
    "DM-037": {"exv": "Sep 09 20:00", "upv": "Sep 15 11:00", "wave": "W4"},
    "DM-083": {"exv": "Sep 11 17:00", "upv": "Sep 15 13:00", "wave": "W4"},
    "DM-040": {"exv": "Sep 11 07:30", "upv": "Sep 14 23:30", "wave": "W4"},
    "DM-041": {"exv": "Sep 11 10:00", "upv": "Sep 15 17:30", "wave": "W5"},
    "DM-073": {"exv": "Sep 11 10:00", "upv": "Sep 15 17:30", "wave": "W5"},
    "DM-074": {"exv": "Sep 11 10:00", "upv": "Sep 15 17:30", "wave": "W5"},
    "DM-039": {"exv": "Sep 09 20:00", "upv": "Sep 15 20:30", "wave": "W6"},
    "DM-043": {"exv": "Sep 11 06:00", "upv": "Sep 15 18:30", "wave": "W5"},
    "DM-038": {"exv": "Sep 11 08:00", "upv": "Sep 16 04:00", "wave": "W6"},
    "DM-054": {"exv": "Sep 10 09:30", "upv": "Sep 16 02:30", "wave": "W6"},
}

MOD_COLORS = {"PP": "#3949AB", "PP-PI": "#5C6BC0", "QM": "#00897B", "PM": "#F4511E"}


def render_schedule(db, user):
    st.subheader("🗓️ Mock 1 Schedule Reference")
    st.caption("Read-only reference. Mock 2 dates TBD after Mock 1 findings resolved.")

    rows = []
    for obj in OBJECTS:
        oid = obj["id"]
        sched = M1_SCHEDULE.get(oid, {})
        m1 = MOCK1_RESULTS.get(oid, {})
        dep = OBJ_DEPS.get(oid, {})
        loaded = m1.get("loaded")
        errors = m1.get("errors")

        rows.append({
            "DM-ID": oid,
            "Object": obj["name"],
            "Mod": obj["module"],
            "M1 Wave": sched.get("wave", obj["wave"]),
            "M1 EXV Start": sched.get("exv", "—"),
            "M1 UPV Start": sched.get("upv", "—"),
            "Tool": obj["tool"],
            "M1 Posted": f"{loaded:,}" if loaded is not None else "—",
            "M1 Rate": m1.get("rate", "—"),
            "Dependency": ", ".join(dep.get("needs", [])) or "—",
            "Blocker": dep.get("blocker", "")[:60] if dep.get("blocker") else "",
        })

    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    st.markdown("---")
    st.markdown("### 📊 Load Sequence — Gantt View")
    st.caption("Bars show actual step timing when available, M1 planned schedule otherwise.")

    gantt_rows = []
    for obj in OBJECTS:
        oid = obj["id"]
        sched = M1_SCHEDULE.get(oid, {})
        steps = db.get_steps(oid)

        actual_start, actual_end = None, None
        has_running = False
        for s in STEP_DEFS:
            sr = steps.get(s["key"], {})
            for field in ("started_at", "ended_at"):
                val = sr.get(field)
                if val:
                    try:
                        t = datetime.fromisoformat(val.replace("Z", "+00:00"))
                        if field == "started_at":
                            if actual_start is None or t < actual_start:
                                actual_start = t
                        else:
                            if actual_end is None or t > actual_end:
                                actual_end = t
                    except Exception:
                        pass
            if sr.get("status") == "running":
                has_running = True

        if actual_start:
            end = actual_end if actual_end else datetime.now(timezone.utc)
            gantt_rows.append({
                "ID": oid,
                "Name": obj["name"],
                "Module": obj["module"],
                "Wave": obj["wave"],
                "Bar": "Actual",
                "Start": actual_start,
                "Finish": end,
            })
        elif sched.get("exv") and sched.get("upv"):
            try:
                s_dt = datetime.strptime(f"2025 {sched['exv']}", "%Y %b %d %H:%M")
                e_dt = datetime.strptime(f"2025 {sched['upv']}", "%Y %b %d %H:%M")
                gantt_rows.append({
                    "ID": oid,
                    "Name": obj["name"],
                    "Module": obj["module"],
                    "Wave": obj["wave"],
                    "Bar": "Planned (M1)",
                    "Start": s_dt,
                    "Finish": e_dt,
                })
            except Exception:
                pass

    if gantt_rows:
        df_g = pd.DataFrame(gantt_rows)
        fig = px.timeline(
            df_g,
            x_start="Start",
            x_end="Finish",
            y="ID",
            color="Module",
            color_discrete_map=MOD_COLORS,
            hover_data={"Name": True, "Wave": True, "Bar": True,
                        "Start": False, "Finish": False, "ID": False},
            labels={"ID": "Object"},
        )
        fig.update_yaxes(autorange="reversed", title="")
        fig.update_layout(
            height=580,
            margin=dict(t=20, b=20),
            legend_title="Module",
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No timing data yet. Gantt will populate as steps are started.")

    st.markdown("---")
    st.markdown("### Mock 2 Focus Areas")

    focus = [
        ("🔴 Critical", "Production BOM (DM-037)", "Only 29/25,481 via ALE. Root cause investigation required before Mock 2. Evaluate LSMW CS01 as fallback."),
        ("🔴 Critical", "Process Orders (DM-076)", "2/44 — not representative. Full chain (Material→BOM→Recipe→ProdVer) must be complete first."),
        ("🟠 High",    "Master Recipe (DM-039)", "72.3% — ABAP duplicate KTEXT fix required. Material inactive/discontinued business decisions needed."),
        ("🟠 High",    "Maintenance Plans (DM-054)", "76.9% — Z4 fiscal year variant and period version config must be fixed in ECD before Mock 2."),
        ("🟠 High",    "Maintenance Orders (DM-077)", "56.6% — Same Z4 issue. 2024 orders need business cleansing decision."),
        ("🟠 High",    "QM Inspection Lots (DM-071)", "20.7% — Origin 17/04 exclusions, vendor migration, MATMAS/MATQM must be complete."),
        ("🟡 Medium",  "Work Centers / Resources (DM-055)", "100% ✅ but OBJID/KAPID preservation unresolved. Finalise strategy before Mock 2."),
        ("🟡 Medium",  "MIC (DM-042)", "Not in Mock 1. ALE IDoc QPMK setup: BD64, WE20, namespace activation (Angelo)."),
    ]

    for priority, obj_name, detail in focus:
        with st.expander(f"{priority} — {obj_name}"):
            st.write(detail)
