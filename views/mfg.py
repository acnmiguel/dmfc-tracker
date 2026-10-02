"""views/mfg.py — MFG Workstream tab"""

import streamlit as st
from datetime import datetime, timezone
from data import OBJECTS, STEP_DEFS, MOCK1_RESULTS, MOCK2_ACTIONS, EXT_NUM_OBJECTS, PREREQ_OBJECTS, OBJECT_OWNERS
from views.gantt import PLAN, _day_active

MOD_COLOR   = {"PP": "#1A237E", "PP-PI": "#283593", "QM": "#004D40", "PM": "#BF360C"}
MOD_BG      = {"PP": "#E8EAF6", "PP-PI": "#E8EAF6", "QM": "#E0F2F1", "PM": "#FBE9E7"}
OWNER_COLOR = {"Miguel": "#1565C0", "Alyssa": "#2E7D32"}
OWNER_BG    = {"Miguel": "#BBDEFB", "Alyssa": "#C8E6C9"}
OWNER_BD    = {"Miguel": "#1565C0", "Alyssa": "#2E7D32"}


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def _shown_steps(obj_id):
    has_ext    = obj_id in EXT_NUM_OBJECTS
    has_prereq = obj_id in PREREQ_OBJECTS
    return [
        s for s in STEP_DEFS
        if not (s["key"] in ("EXT_NUM", "EXT_REVERT") and not has_ext)
        and not (s["key"] == "PREREQ" and not has_prereq)
    ]


def _get_next_step(steps, shown_steps):
    """Return (step_def, step_record) for the first running or pending step."""
    for s in shown_steps:
        sr = steps.get(s["key"], {})
        if sr.get("status") in ("running", "pending", None, ""):
            return s, sr
    return None, {}


# ── Main entry ─────────────────────────────────────────────────────────────────

def render_mfg(db, user):
    st.subheader("⚙ MFG Workstream — PP · PP-PI · QM · PM")

    if "active_obj" not in st.session_state:
        st.session_state.active_obj = None

    view_mode = st.radio(
        "View",
        ["📋 Checklist", "⚡ Quick Actions", "📌 Kanban", "📅 My Tasks Today"],
        horizontal=True,
        key="mfg_view",
    )

    # Kanban and My Tasks Today handle their own layout; others share filters
    if view_mode not in ("📌 Kanban", "📅 My Tasks Today"):
        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            owner_filter = st.multiselect("Owner", ["Miguel", "Alyssa"], default=[])
        with col2:
            mod_filter = st.multiselect("Module", ["PP", "PP-PI", "QM", "PM"], default=[])
        with col3:
            wave_filter = st.multiselect("Wave", sorted(set(o["wave"] for o in OBJECTS)), default=[])
        with col4:
            status_filter = st.multiselect("Status", ["Not Started", "In Progress", "Completed"], default=[])
        with col5:
            search = st.text_input("Search", placeholder="name or DM-ID")
    else:
        owner_filter = mod_filter = wave_filter = status_filter = []
        search = ""

    # Bulk data load
    all_status      = db.get_all_status()
    active_blockers = db.get_blockers()
    try:
        all_steps = db.get_all_steps()
    except AttributeError:
        all_steps = {obj["id"]: db.get_steps(obj["id"]) for obj in OBJECTS}

    objs = list(OBJECTS)
    if owner_filter:
        objs = [o for o in objs if OBJECT_OWNERS.get(o["id"], "—") in owner_filter]
    if mod_filter:
        objs = [o for o in objs if o["module"] in mod_filter]
    if wave_filter:
        objs = [o for o in objs if o["wave"] in wave_filter]
    if status_filter:
        objs = [o for o in objs if all_status.get(o["id"], {}).get("status", "Not Started") in status_filter]
    if search:
        q = search.lower()
        objs = [o for o in objs if q in o["name"].lower() or q in o["id"].lower()]

    if view_mode == "📋 Checklist":
        if not objs:
            st.info("No objects match the current filters.")
            return
        st.caption(f"{len(objs)} objects shown")
        st.markdown("---")
        _render_checklist(db, user, objs, all_status, all_steps, active_blockers)

    elif view_mode == "⚡ Quick Actions":
        if not objs:
            st.info("No objects match the current filters.")
            return
        st.caption(f"{len(objs)} objects · Start or stop the current step without expanding")
        st.markdown("---")
        _render_quick_actions(db, user, objs, all_status, all_steps, active_blockers)

    elif view_mode == "📌 Kanban":
        _render_kanban(db, user, all_status, all_steps, active_blockers)

    else:
        _render_my_tasks(db, user, all_status, all_steps, active_blockers)


# ── View 1: Checklist (original) ───────────────────────────────────────────────

def _render_checklist(db, user, objs, all_status, all_steps, active_blockers):
    for obj in objs:
        oid = obj["id"]
        db_status  = all_status.get(oid, {})
        obj_status = db_status.get("status", "Not Started")
        steps      = all_steps.get(oid, {})
        blocked    = oid in active_blockers
        shown      = _shown_steps(oid)
        done_count = sum(1 for s in shown if steps.get(s["key"], {}).get("status") == "done")
        owner      = OBJECT_OWNERS.get(oid, "—")
        status_icon = {"Not Started": "⬜", "In Progress": "🟡", "Completed": "✅"}.get(obj_status, "⬜")
        block_icon  = "🚨 " if blocked else ""
        owner_color = OWNER_COLOR.get(owner, "#555")
        is_expanded = st.session_state.active_obj == oid

        with st.expander(
            f"{block_icon}{status_icon} **{oid}** — {obj['name']}  "
            f"[{done_count}/{len(shown)}] · {owner} | {obj['module']} · {obj['wave']}",
            expanded=is_expanded,
        ):
            _render_object_detail(db, user, obj, db_status, steps, active_blockers, blocked, shown, owner, owner_color)


# ── View 2: Quick Actions ──────────────────────────────────────────────────────

def _render_quick_actions(db, user, objs, all_status, all_steps, active_blockers):
    for obj in objs:
        oid        = obj["id"]
        db_status  = all_status.get(oid, {})
        obj_status = db_status.get("status", "Not Started")
        steps      = all_steps.get(oid, {})
        shown      = _shown_steps(oid)
        done_count = sum(1 for s in shown if steps.get(s["key"], {}).get("status") == "done")
        owner      = OBJECT_OWNERS.get(oid, "—")
        blocked    = oid in active_blockers
        is_expanded = st.session_state.active_obj == oid
        next_step, next_sr = _get_next_step(steps, shown)

        status_icon = {"Not Started": "⬜", "In Progress": "🟡", "Completed": "✅"}.get(obj_status, "⬜")
        obg = OWNER_BG.get(owner, "#F5F5F5")
        obd = OWNER_BD.get(owner, "#888")

        # ── Card row ──────────────────────────────────────────────────────────
        st.markdown(
            f'<div style="background:{obg};border-left:4px solid {obd};'
            f'border-radius:4px;padding:6px 10px;margin-bottom:2px">'
            f'{"🚨 " if blocked else ""}{status_icon} <b>{oid}</b> — {obj["name"]}'
            f' &nbsp;<span style="color:#777;font-size:11px">{owner} · {obj["module"]}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

        c_prog, c_step, c_btn, c_det = st.columns([2, 3, 1, 1])
        with c_prog:
            st.progress(
                done_count / len(shown) if shown else 0.0,
                text=f"{done_count}/{len(shown)} steps",
            )
        with c_step:
            if next_step:
                sr_status = next_sr.get("status", "pending")
                if sr_status == "running":
                    try:
                        s_dt = datetime.fromisoformat(
                            next_sr["started_at"].replace("Z", "+00:00")
                        )
                        st.caption(f"🟢 Running: **{next_step['label']}** since {s_dt.strftime('%H:%M')}")
                    except Exception:
                        st.caption(f"🟢 Running: **{next_step['label']}**")
                else:
                    st.caption(f"Next: **{next_step['label']}**")
            elif done_count == len(shown):
                st.caption("✅ All steps complete")
        with c_btn:
            if next_step:
                sk = next_step["key"]
                if next_sr.get("status") == "running":
                    if st.button("■ Stop", key=f"qa_stop_{oid}", use_container_width=True):
                        _stop_step(db, oid, sk, user["name"], steps, shown)
                        st.session_state.active_obj = oid
                        st.rerun()
                else:
                    if st.button("▶ Start", key=f"qa_start_{oid}", type="primary", use_container_width=True):
                        _start_step(db, oid, sk, user["name"], obj_status)
                        st.session_state.active_obj = oid
                        st.rerun()
        with c_det:
            label = "▲ Hide" if is_expanded else "▼ Details"
            if st.button(label, key=f"qa_det_{oid}", use_container_width=True):
                st.session_state.active_obj = oid if not is_expanded else None
                st.rerun()

        if is_expanded:
            with st.container():
                st.markdown(
                    '<div style="border-left:3px solid #90CAF9;padding-left:14px;margin:4px 0 12px 0">',
                    unsafe_allow_html=True,
                )
                _render_object_detail(
                    db, user, obj, db_status, steps, active_blockers,
                    blocked, shown, owner, OWNER_COLOR.get(owner, "#555"),
                )
                st.markdown("</div>", unsafe_allow_html=True)

        st.markdown('<hr style="margin:4px 0;border-color:#eee">', unsafe_allow_html=True)


# ── View 3: Kanban ─────────────────────────────────────────────────────────────

def _render_kanban(db, user, all_status, all_steps, active_blockers):
    all_objs = list(OBJECTS)
    not_started = [o for o in all_objs if all_status.get(o["id"], {}).get("status", "Not Started") == "Not Started"]
    in_progress  = [o for o in all_objs if all_status.get(o["id"], {}).get("status", "") == "In Progress"]
    completed    = [o for o in all_objs if all_status.get(o["id"], {}).get("status", "") == "Completed"]

    col_ns, col_ip, col_done = st.columns(3)

    def _card(col, obj, next_label, next_status):
        oid   = obj["id"]
        steps = all_steps.get(oid, {})
        shown = _shown_steps(oid)
        done_count = sum(1 for s in shown if steps.get(s["key"], {}).get("status") == "done")
        owner = OBJECT_OWNERS.get(oid, "—")
        obg   = OWNER_BG.get(owner, "#F5F5F5")
        obd   = OWNER_BD.get(owner, "#888")
        blocked = oid in active_blockers
        next_step, _ = _get_next_step(steps, shown)

        with col:
            st.markdown(
                f'<div style="background:{obg};border-left:4px solid {obd};'
                f'border-radius:6px;padding:10px 12px;margin-bottom:6px">'
                f'{"🚨 " if blocked else ""}<b>{oid}</b>'
                f'<span style="color:#777;font-size:10px"> · {owner} · {obj["module"]}</span><br>'
                f'<span style="font-size:12px">{obj["name"]}</span><br>'
                f'<span style="color:#888;font-size:10px">{done_count}/{len(shown)} steps'
                + (f' · Next: {next_step["label"]}' if next_step else '') +
                f'</span></div>',
                unsafe_allow_html=True,
            )
            if next_label:
                if st.button(next_label, key=f"kb_{next_status}_{oid}", use_container_width=True):
                    db.upsert_status(oid, {
                        "status": next_status,
                        "updated_by": user["name"],
                        "updated_at": now_iso(),
                    })
                    db.log(oid, "status_kanban", f"→{next_status}", user["name"])
                    st.rerun()

    with col_ns:
        st.markdown(f"### ⬜ Not Started &nbsp; `{len(not_started)}`")
        for o in sorted(not_started, key=lambda x: OBJECT_OWNERS.get(x["id"], "")):
            _card(col_ns, o, "→ Start", "In Progress")

    with col_ip:
        st.markdown(f"### 🟡 In Progress &nbsp; `{len(in_progress)}`")
        for o in in_progress:
            _card(col_ip, o, "→ Mark Done", "Completed")

    with col_done:
        st.markdown(f"### ✅ Done &nbsp; `{len(completed)}`")
        for o in completed:
            _card(col_done, o, None, None)


# ── View 4: My Tasks Today ─────────────────────────────────────────────────────

def _render_my_tasks(db, user, all_status, all_steps, active_blockers):
    c1, c2 = st.columns([2, 4])
    with c1:
        day1 = st.date_input(
            "Cutover Day 1", value=datetime(2027, 1, 2).date(), key="mt_day1"
        )
    base = datetime(day1.year, day1.month, day1.day)
    today = datetime.now().date()
    day_num = max(1, (today - day1).days + 1)

    with c2:
        st.markdown(
            f"**Today is Day {day_num}** &nbsp;·&nbsp; "
            f"{today.strftime('%A, %B %d %Y')}"
        )

    # Objects planned for today
    today_objs = [
        o for o in OBJECTS
        if o["id"] in PLAN and _day_active(*PLAN[o["id"]], day_num)
    ]

    if not today_objs:
        st.info(f"No objects scheduled for Day {day_num}. Check the Schedule Grid for other days.")
        return

    # Split by owner
    mine    = [o for o in today_objs if OBJECT_OWNERS.get(o["id"]) == user.get("name")]
    theirs  = [o for o in today_objs if OBJECT_OWNERS.get(o["id"]) != user.get("name")]

    def _task_card(obj):
        oid        = obj["id"]
        db_status  = all_status.get(oid, {})
        obj_status = db_status.get("status", "Not Started")
        steps      = all_steps.get(oid, {})
        shown      = _shown_steps(oid)
        done_count = sum(1 for s in shown if steps.get(s["key"], {}).get("status") == "done")
        owner      = OBJECT_OWNERS.get(oid, "—")
        blocked    = oid in active_blockers
        is_expanded = st.session_state.active_obj == oid
        next_step, next_sr = _get_next_step(steps, shown)

        obg = OWNER_BG.get(owner, "#F5F5F5")
        obd = OWNER_BD.get(owner, "#888")
        status_icon = {"Not Started": "⬜", "In Progress": "🟡", "Completed": "✅"}.get(obj_status, "⬜")

        st.markdown(
            f'<div style="background:{obg};border-left:4px solid {obd};'
            f'border-radius:6px;padding:10px 14px;margin-bottom:4px">'
            f'{"🚨 " if blocked else ""}{status_icon} <b style="font-size:14px">{obj["name"]}</b><br>'
            f'<span style="color:#666;font-size:11px">{oid} · {obj["module"]} · '
            f'{done_count}/{len(shown)} steps</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

        bc1, bc2, bc3 = st.columns([3, 1, 1])
        with bc1:
            if next_step:
                sr_status = next_sr.get("status", "pending")
                if sr_status == "running":
                    try:
                        s_dt = datetime.fromisoformat(next_sr["started_at"].replace("Z", "+00:00"))
                        st.caption(f"🟢 Running: **{next_step['label']}** since {s_dt.strftime('%H:%M')}")
                    except Exception:
                        st.caption(f"🟢 Running: **{next_step['label']}**")
                else:
                    st.caption(f"Next step: **{next_step['label']}**")
            elif done_count == len(shown):
                st.caption("✅ All steps complete")
        with bc2:
            if next_step:
                sk = next_step["key"]
                if next_sr.get("status") == "running":
                    if st.button("■ Stop", key=f"mt_stop_{oid}", use_container_width=True):
                        _stop_step(db, oid, sk, user["name"], steps, shown)
                        st.session_state.active_obj = oid
                        st.rerun()
                else:
                    if st.button("▶ Start", key=f"mt_start_{oid}", type="primary", use_container_width=True):
                        _start_step(db, oid, sk, user["name"], obj_status)
                        st.session_state.active_obj = oid
                        st.rerun()
        with bc3:
            label = "▲ Hide" if is_expanded else "▼ Details"
            if st.button(label, key=f"mt_det_{oid}", use_container_width=True):
                st.session_state.active_obj = oid if not is_expanded else None
                st.rerun()

        if is_expanded:
            with st.container():
                st.markdown(
                    '<div style="border-left:3px solid #90CAF9;padding-left:14px;margin:4px 0 12px 0">',
                    unsafe_allow_html=True,
                )
                _render_object_detail(
                    db, user, obj, db_status, steps, active_blockers,
                    blocked, shown, owner, OWNER_COLOR.get(owner, "#555"),
                )
                st.markdown("</div>", unsafe_allow_html=True)

        st.markdown('<hr style="margin:6px 0;border-color:#eee">', unsafe_allow_html=True)

    if mine:
        st.markdown(f"### 👤 Your tasks — Day {day_num} ({len(mine)} objects)")
        for obj in mine:
            _task_card(obj)

    if theirs:
        owner_name = next(
            (OBJECT_OWNERS.get(o["id"]) for o in theirs if OBJECT_OWNERS.get(o["id"])), "Team"
        )
        st.markdown(f"### 👥 {owner_name}'s tasks — Day {day_num} ({len(theirs)} objects)")
        for obj in theirs:
            _task_card(obj)


# ── Detail panel (shared by all views) ────────────────────────────────────────

def _render_object_detail(db, user, obj, db_status, steps, active_blockers, blocked, shown_steps, owner, owner_color):
    oid     = obj["id"]
    m1      = MOCK1_RESULTS.get(oid, {})
    actions = MOCK2_ACTIONS.get(oid, [])

    done_count = sum(1 for s in shown_steps if steps.get(s["key"], {}).get("status") == "done")
    st.progress(
        done_count / len(shown_steps) if shown_steps else 0.0,
        text=f"{done_count}/{len(shown_steps)} steps · Owner: **{owner}**",
    )

    col1, col2, col3 = st.columns(3)
    with col1:
        mc = MOD_COLOR.get(obj["module"], "#555")
        ml = MOD_BG.get(obj["module"], "#f5f5f5")
        st.markdown(
            f'<span style="background:{ml};color:{mc};padding:3px 10px;'
            f'border-radius:4px;font-weight:700">{obj["module"]}</span>'
            f'&nbsp;&nbsp;<span style="color:{owner_color};font-weight:600">{owner}</span>',
            unsafe_allow_html=True,
        )
        st.caption(f"Tool: {obj['tool']}")
        if obj["vol"]:
            st.caption(f"Source volume: {obj['vol']:,}")
    with col2:
        if m1:
            loaded = m1.get("loaded")
            errors = m1.get("errors")
            rate   = m1.get("rate", "—")
            if loaded is not None:
                pct   = round(loaded / (loaded + errors) * 100, 1) if (loaded + errors) > 0 else 0
                color = "#2E7D32" if pct >= 95 else "#E65100" if pct >= 50 else "#C62828"
                st.markdown(
                    f"**Mock 1:** `{loaded:,} / {loaded+errors:,}` "
                    f'<span style="color:{color};font-weight:700">({rate})</span>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown("**Mock 1:** Not in scope")
            st.caption(m1.get("note", ""))
    with col3:
        if actions:
            st.markdown("**Mock 2 actions:**")
            for a in actions:
                st.markdown(f"• {a}")

    st.markdown("---")

    col_s, col_l, col_e, col_notes = st.columns([2, 2, 2, 4])
    with col_s:
        new_status = st.selectbox(
            "Status",
            ["Not Started", "In Progress", "Completed"],
            index=["Not Started", "In Progress", "Completed"].index(
                db_status.get("status", "Not Started")
            ),
            key=f"status_{oid}",
        )
    with col_l:
        new_loaded = st.number_input(
            "M2 Records Loaded", min_value=0,
            value=int(db_status.get("m1_loaded") or 0), step=1, key=f"loaded_{oid}",
        )
    with col_e:
        new_errors = st.number_input(
            "M2 Errors", min_value=0,
            value=int(db_status.get("m1_errors") or 0), step=1, key=f"errors_{oid}",
        )
    with col_notes:
        new_notes = st.text_area(
            "Notes", value=db_status.get("notes", ""), height=68, key=f"notes_{oid}",
        )

    if st.button("💾 Save", key=f"save_{oid}"):
        db.upsert_status(oid, {
            "status": new_status,
            "m1_loaded": new_loaded or None,
            "m1_errors": new_errors or None,
            "notes": new_notes,
            "updated_by": user["name"],
            "updated_at": now_iso(),
        })
        db.log(oid, "status_update",
               f"status={new_status} loaded={new_loaded} errors={new_errors}",
               user["name"])
        st.success("Saved!", icon="✅")
        st.session_state.active_obj = oid
        st.rerun()

    blk = active_blockers.get(oid)
    if blk:
        st.error(
            f"🚨 **BLOCKED** — {blk['reason']}  |  Owner: **{blk['owner']}**  "
            f"|  Raised by {blk['raised_by']} at {blk['raised_at'][:16]}",
        )
        if st.button("✅ Clear Blocker", key=f"clear_blk_{oid}"):
            db.clear_blocker(blk["id"] if "id" in blk else oid, user["name"])
            db.log(oid, "blocker_cleared", blk["reason"], user["name"])
            st.success("Blocker cleared.")
            st.session_state.active_obj = oid
            st.rerun()
    else:
        with st.expander("⚠️ Raise a blocker for this object", expanded=False):
            blk_reason = st.text_input("Reason", key=f"blk_reason_{oid}")
            blk_owner  = st.text_input(
                "Owner / Escalate to", value=_default_owner(oid), key=f"blk_owner_{oid}",
            )
            if st.button("🚨 Raise Blocker", key=f"raise_blk_{oid}"):
                if blk_reason:
                    db.raise_blocker(oid, blk_reason, blk_owner, user["name"])
                    db.log(oid, "blocker_raised", blk_reason, user["name"])
                    st.warning("Blocker raised.")
                    st.session_state.active_obj = oid
                    st.rerun()

    st.markdown("#### Execution Checklist")

    for si, step in enumerate(shown_steps):
        sk      = step["key"]
        sr      = steps.get(sk, {})
        status  = sr.get("status", "pending")
        started = sr.get("started_at")
        ended   = sr.get("ended_at")
        note    = sr.get("note", "")
        color   = step["color"]
        is_done    = status == "done"
        is_running = status == "running"

        label_parts = [f"**{si+1}. {step['label']}**"]
        if is_done and started and ended:
            try:
                s_dt = datetime.fromisoformat(started.replace("Z", "+00:00"))
                e_dt = datetime.fromisoformat(ended.replace("Z", "+00:00"))
                mins = round((e_dt - s_dt).total_seconds() / 60)
                dur  = f"{mins}m" if mins < 60 else f"{mins//60}h {mins%60}m"
                label_parts.append(f"▶ {s_dt.strftime('%b %d %H:%M')} → ■ {e_dt.strftime('%b %d %H:%M')} ⏱ {dur}")
            except Exception:
                pass
        elif is_running and started:
            try:
                s_dt = datetime.fromisoformat(started.replace("Z", "+00:00"))
                label_parts.append(f"🟢 Running since {s_dt.strftime('%b %d %H:%M')}")
            except Exception:
                pass

        bg     = "#F1F8F1" if is_done else "#FFF8E1" if is_running else "#fafafa"
        border = "#A5D6A7" if is_done else "#FFB300" if is_running else "#e0e0e0"

        st.markdown(
            f'<div style="background:{bg};border:1px solid {border};'
            f'border-left:4px solid {color};padding:8px 12px;border-radius:4px;margin-bottom:6px">'
            f"{'  '.join(label_parts)}"
            f"</div>",
            unsafe_allow_html=True,
        )

        btn_cols = st.columns([1, 1, 1, 4])
        with btn_cols[0]:
            if not is_done and not is_running:
                if st.button("▶ Start", key=f"start_{oid}_{sk}"):
                    _start_step(db, oid, sk, user["name"], db_status.get("status", "Not Started"))
                    st.session_state.active_obj = oid
                    st.rerun()
            elif is_running:
                if st.button("■ Stop", key=f"stop_{oid}_{sk}"):
                    _stop_step(db, oid, sk, user["name"], steps, shown_steps)
                    st.session_state.active_obj = oid
                    st.rerun()
        with btn_cols[1]:
            if is_done or is_running:
                if st.button("↺ Reset", key=f"reset_{oid}_{sk}"):
                    _reset_step(db, oid, sk, user["name"])
                    st.session_state.active_obj = oid
                    st.rerun()
        with btn_cols[3]:
            new_note = st.text_input(
                "Note", value=note, label_visibility="collapsed",
                placeholder="Add note…", key=f"note_{oid}_{sk}",
            )
            if new_note != note:
                db.upsert_step(oid, sk, {
                    "status": status, "started_at": started,
                    "ended_at": ended, "note": new_note,
                }, user["name"])


# ── Step helpers ───────────────────────────────────────────────────────────────

def _start_step(db, obj_id, step_key, user_name, current_obj_status):
    db.upsert_step(obj_id, step_key, {
        "status": "running", "started_at": now_iso(), "ended_at": None, "note": "",
    }, user_name)
    db.log(obj_id, "step_start", step_key, user_name)
    if current_obj_status == "Not Started":
        db.upsert_status(obj_id, {"status": "In Progress", "updated_by": user_name, "updated_at": now_iso()})
        db.log(obj_id, "status_auto", "auto→In Progress", user_name)


def _stop_step(db, obj_id, step_key, user_name, steps, shown_steps):
    sr = steps.get(step_key, {})
    db.upsert_step(obj_id, step_key, {
        "status": "done", "started_at": sr.get("started_at"),
        "ended_at": now_iso(), "note": sr.get("note", ""),
    }, user_name)
    db.log(obj_id, "step_done", step_key, user_name)
    updated = {**steps, step_key: {"status": "done"}}
    if shown_steps and all(updated.get(s["key"], {}).get("status") == "done" for s in shown_steps):
        db.upsert_status(obj_id, {"status": "Completed", "updated_by": user_name, "updated_at": now_iso()})
        db.log(obj_id, "status_auto", "auto→Completed (all steps done)", user_name)


def _reset_step(db, obj_id, step_key, user_name):
    db.upsert_step(obj_id, step_key, {
        "status": "pending", "started_at": None, "ended_at": None, "note": "",
    }, user_name)
    db.log(obj_id, "step_reset", step_key, user_name)


def _default_owner(oid):
    owners = {
        "DM-055": "FICO Team",       "DM-042": "Angelo (Basis)",
        "DM-039": "Angelo (ABAP)",   "DM-037": "SI MFG Team / Angelo",
        "DM-054": "SI MFG Team",     "DM-073": "SI MFG Team",
        "DM-074": "Angelo (ABAP)",   "DM-076": "SI MFG Team",
        "DM-071": "MM Team",
    }
    return owners.get(oid, "")
