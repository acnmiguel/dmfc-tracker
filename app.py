"""
DMFC Migration Tracker — Streamlit app
Two-user collaborative cutover tracker for the DMFI→DMFC SAP ECC carve-out.
"""

import streamlit as st
import pandas as pd
from datetime import datetime, timezone
import json

from data import get_db, OBJECTS, STEP_DEFS, OBJ_DEPS, MFG_MODS

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="DMFC Migration Tracker",
    page_icon="🔄",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Session defaults ──────────────────────────────────────────────────────────
if "user" not in st.session_state:
    st.session_state.user = None

# ── Auth (simple name-based — not security, just attribution) ─────────────────
def login_screen():
    st.title("🔄 DMFC Migration Tracker")
    st.caption("DMFI → DMFC · ECZ → ECD · Sandbox: S4XCLNT100 · Go-Live: 2 Jan 2027")
    st.markdown("---")
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.subheader("Who are you?")
        name = st.text_input("Your name (for attribution on updates)")
        role = st.selectbox("Role", [
            "SI MFG Lead (Miguel)",
            "AMS PP/QM/PM (Miah)",
            "Data Migration Lead (Rommel)",
            "Basis/ABAP (Angelo)",
            "Del Monte Functional (Jonathan)",
            "Other",
        ])
        if st.button("Enter Tracker", type="primary", use_container_width=True):
            if name.strip():
                st.session_state.user = {"name": name.strip(), "role": role}
                st.rerun()
            else:
                st.error("Please enter your name.")

if not st.session_state.user:
    login_screen()
    st.stop()

user = st.session_state.user
db = get_db()

# ── Header ─────────────────────────────────────────────────────────────────────
col1, col2 = st.columns([3, 1])
with col1:
    st.title("🔄 DMFC Migration Tracker")
    st.caption(f"Logged in as **{user['name']}** ({user['role']})")
with col2:
    st.caption("DMFI → DMFC · ECZ → ECD · Go-Live: 2 Jan 2027")
    if st.button("🔄 Refresh", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

st.markdown("---")

# ── Tabs ──────────────────────────────────────────────────────────────────────
tabs = st.tabs(["📋 MFG Workstream", "🚨 Cutover Runbook", "📊 Summary", "🗓️ Schedule"])

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1: MFG WORKSTREAM
# ═══════════════════════════════════════════════════════════════════════════════
with tabs[0]:
    from views.mfg import render_mfg
    render_mfg(db, user)

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2: CUTOVER RUNBOOK
# ═══════════════════════════════════════════════════════════════════════════════
with tabs[1]:
    from views.runbook import render_runbook
    render_runbook(db, user)

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 3: SUMMARY
# ═══════════════════════════════════════════════════════════════════════════════
with tabs[2]:
    from views.summary import render_summary
    render_summary(db, user)

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 4: SCHEDULE (read-only reference)
# ═══════════════════════════════════════════════════════════════════════════════
with tabs[3]:
    from views.schedule import render_schedule
    render_schedule(db, user)
