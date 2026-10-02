"""views/schedule.py — Schedule reference tab"""

import streamlit as st
import pandas as pd
from data import OBJECTS, MOCK1_RESULTS, OBJ_DEPS

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
