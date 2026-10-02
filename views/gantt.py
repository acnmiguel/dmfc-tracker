"""views/gantt.py — Cutover schedule: Schedule Grid · Day Cards"""

import streamlit as st
import plotly.graph_objects as go
from datetime import datetime, timedelta
from data import OBJECTS, STEP_DEFS, OBJECT_OWNERS

MOD_COLORS = {"PP": "#3949AB", "PP-PI": "#5C6BC0", "QM": "#00897B", "PM": "#F4511E"}

PLAN = {
    "DM-055": (1.0, 1.5),
    "DM-042": (1.0, 1.5),
    "DM-025": (2.0, 2.5),
    "DM-018": (2.0, 3.0),
    "DM-037": (3.0, 4.0),
    "DM-083": (3.0, 4.0),
    "DM-041": (3.0, 3.4),
    "DM-073": (3.0, 3.4),
    "DM-074": (3.0, 3.4),
    "DM-040": (3.0, 3.5),
    "DM-043": (3.0, 3.5),
    "DM-038": (3.5, 4.5),
    "DM-039": (4.0, 5.0),
    "DM-054": (4.5, 5.5),
    "DM-070": (4.5, 5.5),
    "DM-071": (5.0, 6.0),
    "DM-076": (5.5, 6.5),
    "DM-078": (6.0, 8.0),
    "DM-077": (6.0, 8.0),
}

TOTAL_DAYS = 8
_OWNER_ORDER = ["Miguel", "Alyssa"]

STATUS_BG    = {"done": "#C8E6C9", "running": "#FFF9C4", "planned": "#BBDEFB"}
STATUS_FG    = {"done": "#1B5E20", "running": "#E65100", "planned": "#0D47A1"}
STATUS_LABEL = {"done": "Done", "running": "In Progress", "planned": "Planned"}

OWNER_BG     = {"Miguel": "#BBDEFB", "Alyssa": "#C8E6C9"}
OWNER_FG     = {"Miguel": "#0D47A1", "Alyssa": "#1B5E20"}
OWNER_BORDER = {"Miguel": "#1565C0", "Alyssa": "#2E7D32"}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _get_actuals(db):
    try:
        all_steps = db.get_all_steps()
    except AttributeError:
        all_steps = {obj["id"]: db.get_steps(obj["id"]) for obj in OBJECTS}

    result = {}
    for oid in PLAN:
        steps = all_steps.get(oid, {})
        starts, ends, is_running = [], [], False
        for s in STEP_DEFS:
            sr = steps.get(s["key"], {})
            for field, bucket in [("started_at", starts), ("ended_at", ends)]:
                v = sr.get(field)
                if v:
                    try:
                        bucket.append(
                            datetime.fromisoformat(v.replace("Z", "+00:00")).replace(tzinfo=None)
                        )
                    except Exception:
                        pass
            if sr.get("status") == "running":
                is_running = True
        all_done = bool(steps) and all(
            steps.get(s["key"], {}).get("status") == "done" for s in STEP_DEFS
        )
        status = "done" if all_done else ("running" if is_running else "planned")
        result[oid] = {
            "status": status,
            "actual_start": min(starts) if starts else None,
            "actual_end": max(ends) if ends else (datetime.utcnow() if is_running else None),
        }
    return result


def _day_active(plan_s, plan_e, d):
    return plan_s < d + 0.5 and plan_e > d - 0.5


def _build_rows(obj_lookup, actuals, base, overlay):
    rows = {o: [] for o in _OWNER_ORDER}
    for oid, (ps, pe) in PLAN.items():
        owner = OBJECT_OWNERS.get(oid, "—")
        if owner not in rows:
            continue
        obj = obj_lookup.get(oid)
        act = actuals.get(oid, {})
        status = act.get("status", "planned")
        if overlay and act.get("actual_start"):
            bar_s = (act["actual_start"] - base).total_seconds() / 86400 + 1
            ae = act.get("actual_end") or datetime.utcnow()
            bar_e = (ae - base).total_seconds() / 86400 + 1
        else:
            bar_s, bar_e = ps, pe
        rows[owner].append({
            "oid": oid,
            "name": obj["name"] if obj else oid,
            "module": obj["module"] if obj else "",
            "status": status,
            "plan_s": ps, "plan_e": pe,
            "bar_s": bar_s, "bar_e": bar_e,
        })
    for owner in _OWNER_ORDER:
        rows[owner].sort(key=lambda r: r["bar_s"])
    return rows


# ── Main render ────────────────────────────────────────────────────────────────

def render_gantt(db):
    c1, c2, c3 = st.columns([2, 4, 2])
    with c1:
        start_date = st.date_input(
            "Cutover Day 1", value=datetime(2027, 1, 2).date(), key="gantt_start"
        )
    with c2:
        view = st.radio(
            "View",
            ["📅 Schedule Grid", "🗓️ Day Cards"],
            horizontal=True, key="gantt_view",
        )
    with c3:
        overlay = st.checkbox("Show actuals", value=True, key="gantt_overlay")

    base = datetime(start_date.year, start_date.month, start_date.day)
    obj_lookup = {o["id"]: o for o in OBJECTS}
    actuals = (
        _get_actuals(db) if overlay
        else {oid: {"status": "planned", "actual_start": None, "actual_end": None} for oid in PLAN}
    )
    rows = _build_rows(obj_lookup, actuals, base, overlay)

    if view == "📅 Schedule Grid":
        _render_grid(rows, base)
    else:
        _render_day_cards(rows, base)


# ── View 1: Schedule Grid ──────────────────────────────────────────────────────

def _render_grid(rows, base):
    html = """
<style>
.sg { border-collapse:collapse; width:100%; font-family:sans-serif; font-size:11px }
.sg th { background:#37474F; color:white; padding:6px 4px; text-align:center;
          border:1px solid #455A64; white-space:nowrap }
.sg th.obj-col { text-align:left; min-width:200px }
.sg td { padding:4px 5px; border:1px solid #e0e0e0; text-align:center; vertical-align:middle }
.sg td.obj-cell { text-align:left; padding:4px 8px; border-left-width:3px; white-space:normal }
.sg tr.owner-hdr td { background:#ECEFF1; font-weight:700; color:#37474F;
                       text-align:left; padding:5px 8px }
</style>
<div style="overflow-x:auto">
<table class='sg'>
<tr>
  <th class='obj-col'>Object</th>
"""
    for d in range(1, TOTAL_DAYS + 1):
        date_str = (base + timedelta(days=d - 1)).strftime("%b %d")
        html += f"<th>Day {d}<br><small>{date_str}</small></th>"
    html += "</tr>"

    for owner in _OWNER_ORDER:
        html += f"<tr class='owner-hdr'><td colspan='{TOTAL_DAYS + 1}'>👤 {owner}</td></tr>"
        for r in rows[owner]:
            mc = MOD_COLORS.get(r["module"], "#607D8B")
            status = r["status"]
            bg = STATUS_BG.get(status, "#E3F2FD")
            fg = STATUS_FG.get(status, "#0D47A1")
            label = STATUS_LABEL.get(status, status)

            html += (
                f"<tr><td class='obj-cell' style='border-left-color:{mc}'>"
                f"<b>{r['oid']}</b> {r['name']}</td>"
            )
            for d in range(1, TOTAL_DAYS + 1):
                if _day_active(r["plan_s"], r["plan_e"], d):
                    html += (
                        f"<td style='background:{bg};color:{fg};"
                        f"font-size:10px;font-weight:600'>{label}</td>"
                    )
                else:
                    html += "<td></td>"
            html += "</tr>"

    html += "</table></div>"
    st.markdown(html, unsafe_allow_html=True)
    st.caption("Left border color = SAP module (PP / PP-PI / QM / PM)")


# ── View 2: Day Cards ──────────────────────────────────────────────────────────

def _render_day_cards(rows, base):
    day_objs = {d: [] for d in range(1, TOTAL_DAYS + 1)}
    for owner in _OWNER_ORDER:
        for r in rows[owner]:
            for d in range(1, TOTAL_DAYS + 1):
                if _day_active(r["plan_s"], r["plan_e"], d):
                    day_objs[d].append({**r, "owner": owner})

    for batch_start in range(0, TOTAL_DAYS, 4):
        cols = st.columns(4)
        for i in range(4):
            d = batch_start + i + 1
            if d > TOTAL_DAYS:
                break
            date_label = (base + timedelta(days=d - 1)).strftime("%a %b %d")
            objs_today = day_objs[d]

            with cols[i]:
                st.markdown(
                    f"<div style='background:#37474F;color:white;padding:7px 10px;"
                    f"border-radius:6px 6px 0 0;font-weight:700;font-size:12px'>"
                    f"Day {d} &nbsp;·&nbsp; {date_label}</div>",
                    unsafe_allow_html=True,
                )

                if not objs_today:
                    st.markdown(
                        "<div style='padding:10px;color:#aaa;font-size:11px;"
                        "border:1px solid #eee;border-top:none;"
                        "border-radius:0 0 6px 6px'>No tasks</div>",
                        unsafe_allow_html=True,
                    )
                    continue

                items = ""
                for r in objs_today:
                    owner = r["owner"]
                    obg = OWNER_BG.get(owner, "#F5F5F5")
                    ofg = OWNER_FG.get(owner, "#333")
                    obd = OWNER_BORDER.get(owner, "#888")
                    status_label = STATUS_LABEL.get(r["status"], r["status"])
                    status_fg = STATUS_FG.get(r["status"], "#555")

                    items += (
                        f"<div style='padding:7px 10px;margin:3px 0;border-radius:4px;"
                        f"background:{obg};border-left:4px solid {obd}'>"
                        f"<div style='color:{ofg};font-weight:700;font-size:12px'>"
                        f"{r['name']}</div>"
                        f"<div style='color:#555;font-size:10px;margin-top:2px'>"
                        f"{r['oid']} · "
                        f"<span style='color:{status_fg};font-weight:600'>{status_label}</span>"
                        f"</div>"
                        f"</div>"
                    )

                st.markdown(
                    f"<div style='padding:5px;border:1px solid #eee;border-top:none;"
                    f"border-radius:0 0 6px 6px'>{items}</div>",
                    unsafe_allow_html=True,
                )

    st.caption("🔵 Blue = Miguel · 🟢 Green = Alyssa")
