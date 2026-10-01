"""views/mfg.py — MFG Workstream tab"""

import streamlit as st
from datetime import datetime, timezone
from data import OBJECTS, STEP_DEFS, MOCK1_RESULTS, MOCK2_ACTIONS, EXT_NUM_OBJECTS, PREREQ_OBJECTS

MOD_COLOR = {"PP": "#1A237E", "PP-PI": "#283593", "QM": "#004D40", "PM": "#BF360C"}
MOD_BG    = {"PP": "#E8EAF6", "PP-PI": "#E8EAF6", "QM": "#E0F2F1", "PM": "#FBE9E7"}


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


def render_mfg(db, user):
    st.subheader("⚙ MFG Workstream — PP · PP-PI · QM · PM")

    # ── Filters ───────────────────────────────────────────────────────────────
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        mod_filter = st.multiselect("Module", ["PP", "PP-PI", "QM", "PM"], default=[])
    with col2:
        wave_filter = st.multiselect("Wave", sorted(set(o["wave"] for o in OBJECTS)), default=[])
    with col3:
        status_filter = st.multiselect("Status", ["Not Started", "In Progress", "Completed"], default=[])
    with col4:
        search = st.text_input("Search object", placeholder="name or DM-ID")

    all_status = db.get_all_status()
    active_blockers = db.get_blockers()

    objs = OBJECTS
    if mod_filter:
        objs = [o for o in objs if o["module"] in mod_filter]
    if wave_filter:
        objs = [o for o in objs if o["wave"] in wave_filter]
    if status_filter:
        objs = [o for o in objs if all_status.get(o["id"], {}).get("status", "Not Started") in status_filter]
    if search:
        q = search.lower()
        objs = [o for o in objs if q in o["name"].lower() or q in o["id"].lower()]

    if not objs:
        st.info("No objects match the current filters.")
        return

    st.caption(f"{len(objs)} objects shown")
    st.markdown("---")

    # ── Object cards ───────────────────────────────────────────────────────────
    for obj in objs:
        oid = obj["id"]
        db_status = all_status.get(oid, {})
        obj_status = db_status.get("status", "Not Started")
        steps = db.get_steps(oid)
        blocked = oid in active_blockers
        shown = _shown_steps(oid)
        done_count = sum(1 for s in shown if steps.get(s["key"], {}).get("status") == "done")

        status_icon = {"Not Started": "⬜", "In Progress": "🟡", "Completed": "✅"}.get(obj_status, "⬜")
        block_icon  = "🚨 " if blocked else ""
        progress_label = f" [{done_count}/{len(shown)}]"

        with st.expander(
            f"{block_icon}{status_icon} **{oid}** — {obj['name']}{progress_label}  "
            f"| {obj['module']} · {obj['wave']} · {obj['tool']}",
            expanded=False,
        ):
            _render_object_detail(db, user, obj, db_status, steps, active_blockers, blocked, shown)


def _render_object_detail(db, user, obj, db_status, steps, active_blockers, blocked, shown_steps):
    oid = obj["id"]
    m1 = MOCK1_RESULTS.get(oid, {})
    actions = MOCK2_ACTIONS.get(oid, [])

    # ── Progress bar ───────────────────────────────────────────────────────────
    done_count = sum(1 for s in shown_steps if steps.get(s["key"], {}).get("status") == "done")
    st.progress(
        done_count / len(shown_steps) if shown_steps else 0.0,
        text=f"{done_count}/{len(shown_steps)} steps completed",
    )

    # ── Top info row ───────────────────────────────────────────────────────────
    col1, col2, col3 = st.columns(3)
    with col1:
        mc = MOD_COLOR.get(obj["module"], "#555")
        ml = MOD_BG.get(obj["module"], "#f5f5f5")
        st.markdown(
            f'<span style="background:{ml};color:{mc};padding:3px 10px;'
            f'border-radius:4px;font-weight:700">{obj["module"]}</span>',
            unsafe_allow_html=True,
        )
        st.caption(f"Tool: {obj['tool']}")
        if obj["vol"]:
            st.caption(f"Source volume: {obj['vol']:,}")

    with col2:
        if m1:
            loaded = m1.get("loaded")
            errors = m1.get("errors")
            rate = m1.get("rate", "—")
            if loaded is not None:
                pct = round(loaded / (loaded + errors) * 100, 1) if (loaded + errors) > 0 else 0
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

    # ── Status + M2 results ────────────────────────────────────────────────────
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
        st.rerun()

    # ── Blocker ────────────────────────────────────────────────────────────────
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
            st.rerun()
    else:
        with st.expander("⚠️ Raise a blocker for this object", expanded=False):
            blk_reason = st.text_input("Reason", key=f"blk_reason_{oid}")
            blk_owner = st.text_input(
                "Owner / Escalate to", value=_default_owner(oid), key=f"blk_owner_{oid}",
            )
            if st.button("🚨 Raise Blocker", key=f"raise_blk_{oid}"):
                if blk_reason:
                    db.raise_blocker(oid, blk_reason, blk_owner, user["name"])
                    db.log(oid, "blocker_raised", blk_reason, user["name"])
                    st.warning("Blocker raised.")
                    st.rerun()

    # ── Step checklist ─────────────────────────────────────────────────────────
    st.markdown("#### Execution Checklist")
    st.caption(f"{done_count}/{len(shown_steps)} steps completed")

    for si, step in enumerate(shown_steps):
        sk = step["key"]
        sr = steps.get(sk, {})
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
                dur = f"{mins}m" if mins < 60 else f"{mins//60}h {mins%60}m"
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
                    st.rerun()
            elif is_running:
                if st.button("■ Stop", key=f"stop_{oid}_{sk}"):
                    _stop_step(db, oid, sk, user["name"], steps, shown_steps)
                    st.rerun()
        with btn_cols[1]:
            if is_done or is_running:
                if st.button("↺ Reset", key=f"reset_{oid}_{sk}"):
                    _reset_step(db, oid, sk, user["name"])
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


def _start_step(db, obj_id, step_key, user_name, current_obj_status):
    db.upsert_step(obj_id, step_key, {
        "status": "running",
        "started_at": now_iso(),
        "ended_at": None,
        "note": "",
    }, user_name)
    db.log(obj_id, "step_start", step_key, user_name)
    if current_obj_status == "Not Started":
        db.upsert_status(obj_id, {
            "status": "In Progress",
            "updated_by": user_name,
            "updated_at": now_iso(),
        })
        db.log(obj_id, "status_auto", "auto→In Progress", user_name)


def _stop_step(db, obj_id, step_key, user_name, steps, shown_steps):
    sr = steps.get(step_key, {})
    db.upsert_step(obj_id, step_key, {
        "status": "done",
        "started_at": sr.get("started_at"),
        "ended_at": now_iso(),
        "note": sr.get("note", ""),
    }, user_name)
    db.log(obj_id, "step_done", step_key, user_name)
    updated = {**steps, step_key: {"status": "done"}}
    if shown_steps and all(updated.get(s["key"], {}).get("status") == "done" for s in shown_steps):
        db.upsert_status(obj_id, {
            "status": "Completed",
            "updated_by": user_name,
            "updated_at": now_iso(),
        })
        db.log(obj_id, "status_auto", "auto→Completed (all steps done)", user_name)


def _reset_step(db, obj_id, step_key, user_name):
    db.upsert_step(obj_id, step_key, {
        "status": "pending", "started_at": None, "ended_at": None, "note": "",
    }, user_name)
    db.log(obj_id, "step_reset", step_key, user_name)


def _default_owner(oid):
    owners = {
        "DM-055": "FICO Team",
        "DM-042": "Angelo (Basis)",
        "DM-039": "Angelo (ABAP)",
        "DM-037": "SI MFG Team / Angelo",
        "DM-054": "SI MFG Team",
        "DM-073": "SI MFG Team",
        "DM-074": "Angelo (ABAP)",
        "DM-076": "SI MFG Team",
        "DM-071": "MM Team",
    }
    return owners.get(oid, "")
