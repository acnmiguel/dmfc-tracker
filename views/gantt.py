"""views/gantt.py — Top-of-page cutover Gantt (two swim lanes: Miguel / Alyssa)"""

import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta
from data import OBJECTS, STEP_DEFS, OBJECT_OWNERS

MOD_COLORS = {"PP": "#3949AB", "PP-PI": "#5C6BC0", "QM": "#00897B", "PM": "#F4511E"}

# Planned load sequence — (day_start, day_end) relative to cutover Day 1
# Based on the schedule image shared by the user.
PLAN = {
    "DM-055": (1.0,  1.5),   # Work Centers / Resources
    "DM-042": (1.0,  1.5),   # Master Inspection Characteristics
    "DM-025": (2.0,  2.5),   # Equipment Master
    "DM-018": (2.0,  3.0),   # Functional Locations
    "DM-037": (3.0,  4.0),   # Production BOM
    "DM-083": (3.0,  4.0),   # Document BOM
    "DM-041": (3.0,  3.4),   # General Task Lists
    "DM-073": (3.0,  3.4),   # Equipment Task Lists
    "DM-074": (3.0,  3.4),   # FL Task Lists
    "DM-040": (3.0,  3.5),   # Equipment BOM
    "DM-043": (3.0,  3.5),   # Inspection Plan
    "DM-038": (3.5,  4.5),   # Production Version
    "DM-039": (4.0,  5.0),   # Master Recipe
    "DM-054": (4.5,  5.5),   # Maintenance Plan
    "DM-070": (4.5,  5.5),   # Open Quality Notifications
    "DM-071": (5.0,  6.0),   # Open Inspection Lots
    "DM-076": (5.5,  6.5),   # Open Process Orders
    "DM-078": (6.0,  8.0),   # Open Maintenance Notifications
    "DM-077": (6.0,  8.0),   # Open Maintenance Orders
}

_OWNER_ORDER = ["Miguel", "Alyssa"]


def render_gantt(db):
    gc1, gc2, gc3 = st.columns([2, 2, 3])
    with gc1:
        start_date = st.date_input(
            "Cutover Day 1",
            value=datetime(2027, 1, 2).date(),
            key="gantt_start",
        )
    with gc2:
        overlay = st.checkbox("Show actual timings", value=True, key="gantt_overlay")

    base = datetime(start_date.year, start_date.month, start_date.day)

    # Fetch all step actuals in one call
    try:
        all_steps = db.get_all_steps()
    except AttributeError:
        all_steps = {obj["id"]: db.get_steps(obj["id"]) for obj in OBJECTS}

    obj_lookup = {o["id"]: o for o in OBJECTS}
    rows = []

    for oid, (plan_s, plan_e) in PLAN.items():
        obj = obj_lookup.get(oid)
        if not obj:
            continue
        owner = OBJECT_OWNERS.get(oid, "—")

        # ── Actual timings ────────────────────────────────────────────────────
        actual_start = actual_end = None
        if overlay:
            steps = all_steps.get(oid, {})
            for s in STEP_DEFS:
                sr = steps.get(s["key"], {})
                for field in ("started_at", "ended_at"):
                    val = sr.get(field)
                    if val:
                        try:
                            t = datetime.fromisoformat(
                                val.replace("Z", "+00:00")
                            ).replace(tzinfo=None)
                            if field == "started_at":
                                if actual_start is None or t < actual_start:
                                    actual_start = t
                            else:
                                if actual_end is None or t > actual_end:
                                    actual_end = t
                        except Exception:
                            pass
                if steps.get(s["key"], {}).get("status") == "running":
                    actual_end = actual_end or datetime.utcnow()

        if actual_start:
            row_start = actual_start
            row_end   = actual_end or datetime.utcnow()
            bar_type  = "Actual"
        else:
            row_start = base + timedelta(days=plan_s - 1)
            row_end   = base + timedelta(days=plan_e - 1)
            bar_type  = "Planned"

        day_n = int((row_start - base).days) + 1

        rows.append({
            "ID":     oid,
            "Label":  f"{oid} · {obj['name'][:28]}",
            "Owner":  owner,
            "Module": obj["module"],
            "Wave":   obj["wave"],
            "Type":   bar_type,
            "Day":    f"Day {day_n}",
            "Start":  row_start,
            "Finish": row_end,
            "seq":    obj["seq"],
        })

    if not rows:
        st.info("No schedule data to display.")
        return

    df = pd.DataFrame(rows)
    df["Owner"] = pd.Categorical(df["Owner"], _OWNER_ORDER)
    df = df.sort_values(["Owner", "Start"], ascending=[True, True])

    fig = px.timeline(
        df,
        x_start="Start",
        x_end="Finish",
        y="Label",
        color="Module",
        color_discrete_map=MOD_COLORS,
        facet_row="Owner",
        pattern_shape="Type",
        pattern_shape_map={"Planned": "", "Actual": "x"},
        hover_data={
            "ID": True, "Wave": True, "Type": True, "Day": True,
            "Label": False, "Start": False, "Finish": False,
            "Owner": False, "Module": False, "seq": False,
        },
        labels={"Label": ""},
    )

    # Day-level x-axis ticks
    total_days = 14
    tick_vals  = [base + timedelta(days=i) for i in range(total_days)]
    tick_text  = [f"Day {i+1}" for i in range(total_days)]

    fig.update_xaxes(
        tickmode="array",
        tickvals=tick_vals,
        ticktext=tick_text,
        showgrid=True,
        gridcolor="#e0e0e0",
        range=[base - timedelta(hours=6), base + timedelta(days=total_days)],
    )
    fig.update_yaxes(autorange="reversed", title="", tickfont_size=11)
    fig.update_layout(
        height=500,
        margin=dict(t=30, b=10, l=10, r=10),
        legend_title="Module",
        plot_bgcolor="#f9f9f9",
    )
    # Clean up facet labels — show just "Miguel" / "Alyssa" not "Owner=Miguel"
    fig.for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1],
                                               font_size=13, font_color="#333"))

    st.plotly_chart(fig, use_container_width=True)
    st.caption(
        "Planned bars (solid) from the schedule image · "
        "Actual bars (hatched ✕) from live step timings · "
        "Day 1 = cutover kickoff date above"
    )
