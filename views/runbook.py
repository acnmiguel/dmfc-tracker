"""views/runbook.py — Cutover Runbook tab"""

import streamlit as st
import pandas as pd
from datetime import datetime, timezone
from data import OBJECTS, STEP_DEFS, OBJ_DEPS, EXT_NUM_OBJECTS, PREREQ_OBJECTS, MOCK1_RESULTS


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def get_obj_readiness(obj_id, all_steps, all_status, active_blockers, obj_deps):
    """Return one of: done / running / blocked / waiting / ready"""
    steps = all_steps.get(obj_id, {})
    obj = next((o for o in OBJECTS if o["id"] == obj_id), None)
    if not obj:
        return "ready"

    has_ext = obj_id in EXT_NUM_OBJECTS
    has_prereq = obj_id in PREREQ_OBJECTS
    shown = [
        s for s in STEP_DEFS
        if not (s["key"] in ("EXT_NUM", "EXT_REVERT") and not has_ext)
        and not (s["key"] == "PREREQ" and not has_prereq)
    ]

    if shown and all(steps.get(s["key"], {}).get("status") == "done" for s in shown):
        return "done"
    if any(steps.get(s["key"], {}).get("status") == "running" for s in shown):
        return "running"
    if obj_id in active_blockers:
        return "blocked"
    dep = obj_deps.get(obj_id, {})
    if dep.get("blocker"):
        return "blocked"
    unmet = [nid for nid in dep.get("needs", [])
             if get_obj_readiness(nid, all_steps, all_status, active_blockers, obj_deps) != "done"]
    if unmet:
        return "waiting"
    return "ready"


def get_timing(obj_id, all_steps):
    steps = all_steps.get(obj_id, {})
    starts, ends = [], []
    running = False
    for s in STEP_DEFS:
        sr = steps.get(s["key"], {})
        if sr.get("started_at"):
            try:
                starts.append(datetime.fromisoformat(sr["started_at"].replace("Z", "+00:00")))
            except Exception:
                pass
        if sr.get("ended_at"):
            try:
                ends.append(datetime.fromisoformat(sr["ended_at"].replace("Z", "+00:00")))
            except Exception:
                pass
        if sr.get("status") == "running":
            running = True
    start = min(starts) if starts else None
    end = max(ends) if ends else None
    if running and start:
        end = datetime.now(timezone.utc)
    return start, end, running


def compute_critical_path(obj_deps, all_steps):
    ids = [o["id"] for o in OBJECTS]
    dist, prev = {i: 0 for i in ids}, {i: None for i in ids}

    def dur(oid):
        start, end, _ = get_timing(oid, all_steps)
        if start and end:
            return max(1, round((end - start).total_seconds() / 60))
        o = next((x for x in OBJECTS if x["id"] == oid), None)
        if not o:
            return 60
        m1 = MOCK1_RESULTS.get(oid)
        if m1 and m1.get("loaded"):
            return 60  # fallback estimate
        return 60

    indeg = {i: 0 for i in ids}
    for oid in ids:
        for n in obj_deps.get(oid, {}).get("needs", []):
            if n in indeg:
                indeg[oid] = indeg.get(oid, 0) + 1

    q = [i for i in ids if not indeg[i]]
    order = []
    while q:
        n = q.pop(0)
        order.append(n)
        for succ in ids:
            if n in obj_deps.get(succ, {}).get("needs", []):
                indeg[succ] -= 1
                if not indeg[succ]:
                    q.append(succ)

    for oid in order:
        d = dur(oid)
        for succ in ids:
            if oid in obj_deps.get(succ, {}).get("needs", []):
                if dist[oid] + d > dist[succ]:
                    dist[succ] = dist[oid] + d
                    prev[succ] = oid

    max_id = max(dist, key=dist.get)
    path, cur = [], max_id
    while cur:
        path.insert(0, cur)
        cur = prev[cur]
    return path, dist[max_id]


def render_runbook(db, user):
    st.subheader("🚨 Cutover Runbook — Live Status")

    # Load all data
    all_status = db.get_all_status()
    active_blockers = db.get_blockers()

    # Build steps dict for all objects
    all_steps = {}
    for obj in OBJECTS:
        all_steps[obj["id"]] = db.get_steps(obj["id"])

    # Compute readiness
    readiness = {}
    for obj in OBJECTS:
        readiness[obj["id"]] = get_obj_readiness(
            obj["id"], all_steps, all_status, active_blockers, OBJ_DEPS
        )

    ready = [o for o in OBJECTS if readiness[o["id"]] == "ready"]
    running = [o for o in OBJECTS if readiness[o["id"]] == "running"]
    blocked = [o for o in OBJECTS if readiness[o["id"]] == "blocked"]
    waiting = [o for o in OBJECTS if readiness[o["id"]] == "waiting"]
    done = [o for o in OBJECTS if readiness[o["id"]] == "done"]

    # ── Live clock + summary ───────────────────────────────────────────────────
    now = datetime.now(timezone.utc)
    cols = st.columns(5)
    metrics = [
        ("🟢 Running", len(running)),
        ("✅ Ready", len(ready)),
        ("🚨 Blocked", len(blocked)),
        ("⏳ Waiting", len(waiting)),
        ("✅ Done", f"{len(done)}/{len(OBJECTS)}"),
    ]
    for col, (label, val) in zip(cols, metrics):
        col.metric(label, val)

    st.caption(f"Last refreshed: {now.strftime('%Y-%m-%d %H:%M:%S UTC')}  |  Use Refresh button in header to update")

    # ── Export ─────────────────────────────────────────────────────────────────
    col_exp1, col_exp2, _ = st.columns([2, 2, 6])
    with col_exp1:
        if st.button("📊 Export Log (CSV)"):
            csv = _build_csv(OBJECTS, readiness, all_steps, active_blockers, OBJ_DEPS)
            st.download_button(
                "Download CSV",
                csv,
                file_name=f"DMFC_Cutover_Log_{now.strftime('%Y%m%d_%H%M')}.csv",
                mime="text/csv",
            )

    st.markdown("---")

    # ── READY TO START ─────────────────────────────────────────────────────────
    if ready:
        st.markdown("### ✅ Ready to Start")
        cp_path, _ = compute_critical_path(OBJ_DEPS, all_steps)
        cp_set = set(cp_path)
        cols = st.columns(4)
        for i, o in enumerate(ready):
            with cols[i % 4]:
                cp_badge = " 🔥CP" if o["id"] in cp_set else ""
                st.success(f"**{o['id']}**{cp_badge}\n\n{o['name']}")

    # ── RUNNING ────────────────────────────────────────────────────────────────
    if running:
        st.markdown("### 🟡 Currently Running")
        for o in running:
            start, end, _ = get_timing(o["id"], all_steps)
            elapsed = ""
            if start:
                mins = round((now - start).total_seconds() / 60)
                elapsed = f" — {mins}m elapsed" if mins < 60 else f" — {mins//60}h {mins%60}m elapsed"
            st.warning(f"**{o['id']}** {o['name']}{elapsed}")

    # ── BLOCKED ────────────────────────────────────────────────────────────────
    if blocked:
        st.markdown("### 🚨 Blocked — Action Required")
        for o in blocked:
            blk = active_blockers.get(o["id"])
            dep = OBJ_DEPS.get(o["id"], {})
            reason = blk["reason"] if blk else dep.get("blocker", "Unknown")
            owner = (blk["owner"] if blk else dep.get("owner", "—")) or "—"
            raised = blk["raised_at"][:16] if blk and blk.get("raised_at") else "Pre-existing"

            with st.expander(f"🚨 **{o['id']}** — {o['name']}", expanded=True):
                col1, col2 = st.columns([4, 1])
                with col1:
                    st.error(f"**Reason:** {reason}  \n**Owner:** {owner}  \n**Raised:** {raised}")
                with col2:
                    if blk:
                        if st.button("✅ Clear", key=f"rb_clear_{o['id']}"):
                            db.clear_blocker(blk.get("id", o["id"]), user["name"])
                            db.log(o["id"], "blocker_cleared", reason, user["name"])
                            st.rerun()
                    else:
                        if st.button("📝 Raise", key=f"rb_raise_{o['id']}"):
                            db.raise_blocker(o["id"], reason, owner, user["name"])
                            db.log(o["id"], "blocker_raised", reason, user["name"])
                            st.rerun()

    # ── WAITING ────────────────────────────────────────────────────────────────
    if waiting:
        st.markdown("### ⏳ Waiting on Dependencies")
        rows = []
        for o in waiting:
            dep = OBJ_DEPS.get(o["id"], {})
            needs_info = ", ".join(
                f"{nid} [{readiness.get(nid,'?').upper()}]"
                for nid in dep.get("needs", [])
            )
            rows.append({"Object": f"{o['id']} — {o['name']}", "Waiting for": needs_info})
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # ── FULL TABLE ─────────────────────────────────────────────────────────────
    st.markdown("### 📋 Full Load Sequence")
    cp_path, cp_total = compute_critical_path(OBJ_DEPS, all_steps)
    cp_set = set(cp_path)

    rows = []
    for o in OBJECTS:
        oid = o["id"]
        state = readiness[oid]
        start, end, is_running_obj = get_timing(oid, all_steps)
        elapsed_mins = None
        if start and end:
            elapsed_mins = round((end - start).total_seconds() / 60)

        steps_done = sum(
            1 for s in STEP_DEFS
            if all_steps.get(oid, {}).get(s["key"], {}).get("status") == "done"
        )
        steps_total = len(STEP_DEFS)

        blk = active_blockers.get(oid)
        dep = OBJ_DEPS.get(oid, {})
        blocker_txt = ""
        if blk:
            blocker_txt = blk["reason"]
        elif dep.get("blocker") and state == "blocked":
            blocker_txt = dep["blocker"]

        db_st = db.get_all_status().get(oid, {})
        m2_loaded = db_st.get("m1_loaded")
        m2_errors = db_st.get("m1_errors")

        rows.append({
            "CP": "🔥" if oid in cp_set else "",
            "DM-ID": oid,
            "Object": o["name"],
            "Mod": o["module"],
            "Status": state.upper(),
            "Act. Start": start.strftime("%b %d %H:%M") if start else "—",
            "Elapsed": (
                f"{elapsed_mins}m" if elapsed_mins is not None and elapsed_mins < 60
                else f"{elapsed_mins//60}h {elapsed_mins%60}m" if elapsed_mins is not None
                else "—"
            ),
            "M1 Loaded": f"{MOCK1_RESULTS.get(oid, {}).get('loaded') or '—'}",
            "M2 Loaded": f"{m2_loaded or '—'}",
            "M2 Errors": f"{m2_errors or '—'}",
            "Steps": f"{steps_done}/{steps_total}",
            "Blocker": blocker_txt[:60] + "…" if len(blocker_txt) > 60 else blocker_txt,
        })

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)

    # ── Critical path ──────────────────────────────────────────────────────────
    st.markdown(f"### 🔥 Critical Path — {cp_total} mins estimated")
    cp_names = " → ".join(
        f"**{oid}** ({next(o['name'] for o in OBJECTS if o['id'] == oid)})"
        for oid in cp_path
        if any(o["id"] == oid for o in OBJECTS)
    )
    st.info(cp_names)
    st.caption("Delays on critical path objects delay go-live. All others have float.")


def _build_csv(objects, readiness, all_steps, active_blockers, obj_deps):
    lines = [
        "DM-ID,Object,Module,Status,Act Start,Act End,Elapsed (min),"
        "M1 Loaded,M1 Errors,Steps Done,Steps Total,Blocker"
    ]
    now = datetime.now(timezone.utc)
    for o in objects:
        oid = o["id"]
        start, end, _ = get_timing(oid, all_steps)
        elapsed = ""
        if start and end:
            elapsed = str(round((end - start).total_seconds() / 60))
        m1 = MOCK1_RESULTS.get(oid, {})
        steps_done = sum(
            1 for s in STEP_DEFS
            if all_steps.get(oid, {}).get(s["key"], {}).get("status") == "done"
        )
        blk = active_blockers.get(oid)
        dep = obj_deps.get(oid, {})
        blocker = (blk["reason"] if blk else dep.get("blocker", "")).replace(",", ";")
        row = [
            oid,
            o["name"].replace(",", ";"),
            o["module"],
            readiness.get(oid, ""),
            start.strftime("%Y-%m-%d %H:%M") if start else "",
            end.strftime("%Y-%m-%d %H:%M") if end else "",
            elapsed,
            str(m1.get("loaded") or ""),
            str(m1.get("errors") or ""),
            str(steps_done),
            str(len(STEP_DEFS)),
            blocker,
        ]
        lines.append(",".join(row))
    return "\n".join(lines)
