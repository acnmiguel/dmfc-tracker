"""
DMFC Migration Tracker — Streamlit app
Two-user collaborative cutover tracker for the DMFI→DMFC SAP ECC carve-out.
"""

import streamlit as st
import json
from datetime import datetime, timezone

from data import get_db, OBJECTS, STEP_DEFS, OBJ_DEPS, MFG_MODS

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="DMFC Migration Tracker",
    page_icon="🔄",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Auto-refresh (interval stored in session state so user can change it) ──────
from streamlit_autorefresh import st_autorefresh
REFRESH_OPTIONS = {"1 min": 60_000, "5 min": 300_000, "10 min": 600_000}
if "refresh_interval_ms" not in st.session_state:
    st.session_state.refresh_interval_ms = 300_000  # default 5 min
st_autorefresh(interval=st.session_state.refresh_interval_ms, limit=None, key="autorefresh")

# ── Team roster ────────────────────────────────────────────────────────────────
TEAM = [
    ("Miguel",   "SI MFG Lead"),
    ("Alyssa",   "AMS Migration"),
    ("Miah",     "AMS PP/QM/PM"),
    ("Rommel",   "Data Migration Lead"),
    ("Angelo",   "Basis/ABAP"),
    ("Jonathan", "Del Monte Functional"),
]
TEAM_NAMES = [t[0] for t in TEAM]
TEAM_ROLES = dict(TEAM)

# ── Login — restore from query param so refresh doesn't log you out ────────────
if "user" not in st.session_state:
    raw = st.query_params.get("u", "")
    if raw:
        try:
            st.session_state.user = json.loads(raw)
        except Exception:
            st.session_state.user = None
    else:
        st.session_state.user = None


def login_screen():
    st.title("🔄 DMFC Migration Tracker")
    st.caption("DMFI → DMFC · ECZ → ECD · Go-Live: 2 Jan 2027")
    st.markdown("---")
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.subheader("Who are you?")
        name = st.selectbox("Team member", TEAM_NAMES)
        if st.button("Enter Tracker", type="primary", use_container_width=True):
            user = {"name": name, "role": TEAM_ROLES[name]}
            st.session_state.user = user
            st.query_params["u"] = json.dumps(user)
            st.rerun()


if not st.session_state.user:
    login_screen()
    st.stop()

user = st.session_state.user
db = get_db()

# ── Header ─────────────────────────────────────────────────────────────────────
col1, col2 = st.columns([3, 1])
with col1:
    st.title("🔄 DMFC Migration Tracker")
    st.caption(f"Logged in as **{user['name']}** · {user['role']}")
with col2:
    st.caption("DMFI → DMFC · Go-Live: 2 Jan 2027")
    hc1, hc2, hc3 = st.columns(3)
    with hc1:
        if st.button("🔄 Refresh", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
    with hc2:
        selected = st.selectbox(
            "Auto-refresh", list(REFRESH_OPTIONS.keys()),
            index=list(REFRESH_OPTIONS.values()).index(st.session_state.refresh_interval_ms),
            key="refresh_picker", label_visibility="collapsed",
        )
        st.session_state.refresh_interval_ms = REFRESH_OPTIONS[selected]
    with hc3:
        if st.button("🚪 Log out", use_container_width=True):
            st.session_state.user = None
            st.query_params.clear()
            st.rerun()

st.caption(
    f"Auto-refresh: {selected} · Last: {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}"
)
st.markdown("---")

# ── Tabs ───────────────────────────────────────────────────────────────────────
tabs = st.tabs(["📋 MFG Workstream", "🚨 Cutover Runbook", "📊 Summary", "🗓️ Schedule"])

with tabs[0]:
    from views.mfg import render_mfg
    render_mfg(db, user)

with tabs[1]:
    from views.runbook import render_runbook
    render_runbook(db, user)

with tabs[2]:
    from views.summary import render_summary
    render_summary(db, user)

with tabs[3]:
    from views.schedule import render_schedule
    render_schedule(db, user)
