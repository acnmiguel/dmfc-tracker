"""views/gantt.py — Cutover schedule: Bar Gantt · Schedule Grid · Day Cards"""

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

STATUS_BG  = {"done": "#C8E6C9", "running": "#FFF9C4", "planned": "#BBDEFB"}
STATUS_FG  = {"done": "#1B5E20", "running": "#F57F17", "planned": "#0D47A1"}
STATUS_BAR = {"done": "#66BB6A", "running": "#FFA726", "planned": "#64B5F6"}


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
    """True if object spanning (plan_s, plan_e) is active on integer day d (1-based)."""
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
    c1, c2, c3 = st.columns([2, 5, 2])
    with c1:
        start_date = st.date_input(
            "Cutover Day 1", value=datetime(2027, 1, 2).date(), key="gantt_start"
        )
    with c2:
        view = st.radio(
            "View",
            ["📊 Bar Gantt", "📅 Schedule Grid", "🗓️ Day Cards"],
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

    if view == "📊 Bar Gantt":
        _render_bar_gantt(rows, base)
    elif view == "📅 Schedule Grid":
        _render_grid(rows, base)
    else:
        _render_day_cards(rows, base)


# ── View 1: Bar Gantt ──────────────────────────────────────────────────────────

def _render_bar_gantt(rows, base):
    labels, offsets, widths, colors, hovers = [], [], [], [], []

    for owner in _OWNER_ORDER:
        labels.append(f"── {owner} ──")
        offsets.append(0); widths.append(0)
        colors.append("rgba(0,0,0,0)"); hovers.append("")

        for r in rows[owner]:
            short = r["name"][:26] + ("…" if len(r["name"]) > 26 else "")
            labels.append(f"  {r['oid']}  {short}")
            offsets.append(max(0.0, r["bar_s"] - 1))
            widths.append(max(0.08, r["bar_e"] - r["bar_s"]))
            colors.append(STATUS_BAR.get(r["status"], "#64B5F6"))
            hovers.append(
                f"<b>{r['oid']}</b> — {r['name']}<br>"
                f"Owner: {owner} · Module: {r['module']}<br>"
                f"Planned: Day {r['plan_s']}–{r['plan_e']}<br>"
                f"Status: <b>{r['status'].upper()}</b>"
            )

    fig_h = max(320, len(labels) * 34 + 60)

    fig = go.Figure()
    fig.add_trace(go.Bar(          # invisible offset
        y=labels, x=offsets, orientation="h",
        marker_color="rgba(0,0,0,0)",
        hoverinfo="skip", showlegend=False,
    ))
    fig.add_trace(go.Bar(          # colored duration
        y=labels, x=widths, orientation="h",
        marker=dict(color=colors, line=dict(color="white", width=1)),
        hovertext=hovers, hoverinfo="text",
        showlegend=False,
    ))
    for s, c in STATUS_BAR.items():
        fig.add_trace(go.Bar(y=[None], x=[None], orientation="h",
                             marker_color=c, name=s.capitalize(), showlegend=True))

    fig.update_layout(
        barmode="stack", height=fig_h,
        xaxis=dict(
            tickmode="array",
            tickvals=list(range(TOTAL_DAYS)),
            ticktext=[f"Day {i+1}" for i in range(TOTAL_DAYS)],
            range=[-0.3, TOTAL_DAYS + 0.3],
            showgrid=True, gridcolor="#e0e0e0", zeroline=False,
        ),
        yaxis=dict(autorange="reversed", title="", tickfont_size=11),
        plot_bgcolor="#f9f9f9",
        margin=dict(t=10, b=10, l=5, r=90),
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="right", x=1),
    )
    st.plotly_chart(fig, use_container_width=True)


# ── View 2: Schedule Grid ──────────────────────────────────────────────────────

def _render_grid(rows, base):
    html = """
<style>
.sg { border-collapse:collapse; width:100%; font-family:sans-serif; font-size:11px }
.sg th { background:#37474F; color:white; padding:6px 4px; text-align:center;
          border:1px solid #455A64; white-space:nowrap }
.sg th.obj-col { text-align:left; min-width:170px }
.sg td { padding:4px 3px; border:1px solid #e0e0e0; text-align:center }
.sg td.obj-cell { text-align:left; padding:4px 8px; border-left-width:3px }
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
            name_s = r["name"][:28] + ("…" if len(r["name"]) > 28 else "")
            status = r["status"]
            bg = STATUS_BG.get(status, "#E3F2FD")
            fg = STATUS_FG.get(status, "#0D47A1")
            icon = {"done": "✅", "running": "🟡", "planned": "▓"}.get(status, "")

            html += (
                f"<tr><td class='obj-cell' style='border-left-color:{mc}'>"
                f"<b>{r['oid']}</b> {name_s}</td>"
            )
            for d in range(1, TOTAL_DAYS + 1):
                if _day_active(r["plan_s"], r["plan_e"], d):
                    html += (
                        f"<td style='background:{bg};color:{fg};font-size:13px'>{icon}</td>"
                    )
                else:
                    html += "<td></td>"
            html += "</tr>"

    html += "</table></div>"
    st.markdown(html, unsafe_allow_html=True)
    st.caption("▓ Planned · 🟡 Running · ✅ Done  |  Left border color = SAP module")


# ── View 3: Day Cards ──────────────────────────────────────────────────────────

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
                # Card header
                st.markdown(
                    f"<div style='background:#37474F;color:white;padding:7px 10px;"
                    f"border-radius:6px 6px 0 0;font-weight:700;font-size:12px'>"
                    f"Day {d} &nbsp;·&nbsp; {date_label}</div>",
                    unsafe_allow_html=True,
                )

                if not objs_today:
                    st.markdown(
                        "<div style='padding:10px;color:#aaa;font-size:11px;"
                        "border:1px solid #eee;border-top:none;border-radius:0 0 6px 6px'>"
                        "No tasks</div>",
                        unsafe_allow_html=True,
                    )
                    continue

                items = ""
                for r in objs_today:
                    bg = STATUS_BG.get(r["status"], "#E3F2FD")
                    fg = STATUS_FG.get(r["status"], "#0D47A1")
                    mc = MOD_COLORS.get(r["module"], "#607D8B")
                    o_dot = "🔵" if r["owner"] == "Miguel" else "🟢"
                    icon = {"done": "✅", "running": "🟡", "planned": "⬜"}.get(r["status"], "⬜")
                    name_s = r["name"][:22] + ("…" if len(r["name"]) > 22 else "")
                    items += (
                        f"<div style='padding:5px 7px;margin:3px 0;border-radius:4px;"
                        f"background:{bg};border-left:3px solid {mc}'>"
                        f"<span style='color:{fg};font-size:11px'>{icon} {o_dot} "
                        f"<b>{r['oid']}</b></span><br>"
                        f"<span style='color:#555;font-size:10px'>{name_s}</span>"
                        f"</div>"
                    )

                st.markdown(
                    f"<div style='padding:5px;border:1px solid #eee;border-top:none;"
                    f"border-radius:0 0 6px 6px'>{items}</div>",
                    unsafe_allow_html=True,
                )

    st.caption("🔵 Miguel · 🟢 Alyssa &nbsp;|&nbsp; ⬜ Planned · 🟡 Running · ✅ Done")
