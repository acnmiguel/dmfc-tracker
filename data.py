"""
data.py — static migration data + Supabase client factory

Supabase schema (run once in your project's SQL editor):

    create table if not exists object_status (
        id          text primary key,   -- DM-ID e.g. 'DM-055'
        status      text,               -- Not Started / In Progress / Completed
        m1_loaded   integer,
        m1_errors   integer,
        notes       text,
        updated_by  text,
        updated_at  timestamptz default now()
    );

    create table if not exists step_log (
        id          bigint generated always as identity primary key,
        obj_id      text,               -- DM-ID
        step_key    text,               -- PREREQ / EXTRACT / LOAD etc.
        status      text,               -- pending / running / done
        started_at  timestamptz,
        ended_at    timestamptz,
        note        text,
        updated_by  text,
        updated_at  timestamptz default now()
    );

    create table if not exists blockers (
        id          bigint generated always as identity primary key,
        obj_id      text,
        reason      text,
        owner       text,
        raised_by   text,
        raised_at   timestamptz default now(),
        cleared_by  text,
        cleared_at  timestamptz
    );

    create table if not exists audit_log (
        id          bigint generated always as identity primary key,
        obj_id      text,
        action      text,
        detail      text,
        by_user     text,
        at          timestamptz default now()
    );

    -- Enable realtime on step_log and blockers if you want live updates:
    -- alter publication supabase_realtime add table step_log;
    -- alter publication supabase_realtime add table blockers;
"""

import os
import streamlit as st

# ── Supabase client ────────────────────────────────────────────────────────────
@st.cache_resource
def get_db():
    """Returns a thin wrapper around Supabase. Falls back to in-memory store
    if SUPABASE_URL / SUPABASE_KEY are not set (useful for local dev)."""
    url = os.environ.get("SUPABASE_URL") or st.secrets.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_KEY") or st.secrets.get("SUPABASE_KEY", "")
    if url and key:
        from supabase import create_client
        return SupabaseDB(create_client(url, key))
    else:
        st.warning(
            "⚠️ SUPABASE_URL / SUPABASE_KEY not set — running in local memory mode. "
            "Changes will not persist across refreshes.",
            icon="⚠️",
        )
        return LocalDB()


# ── Supabase wrapper ───────────────────────────────────────────────────────────
class SupabaseDB:
    def __init__(self, client):
        self.sb = client

    # ── Object status ──────────────────────────────────────────────────────────
    def get_all_status(self):
        res = self.sb.table("object_status").select("*").execute()
        return {r["id"]: r for r in (res.data or [])}

    def upsert_status(self, obj_id, fields: dict):
        self.sb.table("object_status").upsert({"id": obj_id, **fields}).execute()

    # ── Step log ───────────────────────────────────────────────────────────────
    def get_steps(self, obj_id):
        res = (
            self.sb.table("step_log")
            .select("*")
            .eq("obj_id", obj_id)
            .order("updated_at", desc=True)
            .execute()
        )
        # Latest record per step_key wins
        seen, steps = set(), {}
        for r in (res.data or []):
            if r["step_key"] not in seen:
                steps[r["step_key"]] = r
                seen.add(r["step_key"])
        return steps

    def upsert_step(self, obj_id, step_key, fields: dict, user_name: str):
        # Insert new row (audit trail — every change is a new row)
        self.sb.table("step_log").insert({
            "obj_id": obj_id,
            "step_key": step_key,
            "updated_by": user_name,
            **fields,
        }).execute()

    # ── Blockers ───────────────────────────────────────────────────────────────
    def get_blockers(self):
        res = (
            self.sb.table("blockers")
            .select("*")
            .is_("cleared_at", "null")
            .execute()
        )
        return {r["obj_id"]: r for r in (res.data or [])}

    def raise_blocker(self, obj_id, reason, owner, user_name):
        self.sb.table("blockers").insert({
            "obj_id": obj_id,
            "reason": reason,
            "owner": owner,
            "raised_by": user_name,
        }).execute()

    def clear_blocker(self, blocker_id, user_name):
        from datetime import datetime, timezone
        self.sb.table("blockers").update({
            "cleared_by": user_name,
            "cleared_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", blocker_id).execute()

    # ── Audit ──────────────────────────────────────────────────────────────────
    def log(self, obj_id, action, detail, user_name):
        try:
            self.sb.table("audit_log").insert({
                "obj_id": obj_id,
                "action": action,
                "detail": detail,
                "by_user": user_name,
            }).execute()
        except Exception:
            pass  # audit failure shouldn't block main action

    def get_audit(self, obj_id=None, limit=50):
        q = self.sb.table("audit_log").select("*").order("at", desc=True).limit(limit)
        if obj_id:
            q = q.eq("obj_id", obj_id)
        res = q.execute()
        return res.data or []


# ── Local in-memory fallback (dev / no Supabase) ──────────────────────────────
class LocalDB:
    """Thread-unsafe in-memory store — fine for single-user local testing."""

    def __init__(self):
        self._status: dict = {}
        self._steps: dict = {}   # {obj_id: {step_key: row}}
        self._blockers: dict = {}
        self._audit: list = []

    def get_all_status(self):
        return self._status

    def upsert_status(self, obj_id, fields):
        self._status.setdefault(obj_id, {"id": obj_id})
        self._status[obj_id].update(fields)

    def get_steps(self, obj_id):
        return self._steps.get(obj_id, {})

    def upsert_step(self, obj_id, step_key, fields, user_name):
        self._steps.setdefault(obj_id, {})
        self._steps[obj_id][step_key] = {"obj_id": obj_id, "step_key": step_key,
                                          "updated_by": user_name, **fields}

    def get_blockers(self):
        return {k: v for k, v in self._blockers.items() if not v.get("cleared_at")}

    def raise_blocker(self, obj_id, reason, owner, user_name):
        from datetime import datetime, timezone
        self._blockers[obj_id] = {
            "id": obj_id, "obj_id": obj_id,
            "reason": reason, "owner": owner,
            "raised_by": user_name,
            "raised_at": datetime.now(timezone.utc).isoformat(),
        }

    def clear_blocker(self, blocker_id, user_name):
        from datetime import datetime, timezone
        if blocker_id in self._blockers:
            self._blockers[blocker_id]["cleared_by"] = user_name
            self._blockers[blocker_id]["cleared_at"] = datetime.now(timezone.utc).isoformat()

    def log(self, obj_id, action, detail, user_name):
        from datetime import datetime, timezone
        self._audit.append({"obj_id": obj_id, "action": action, "detail": detail,
                             "by_user": user_name, "at": datetime.now(timezone.utc).isoformat()})

    def get_audit(self, obj_id=None, limit=50):
        data = self._audit[::-1][:limit]
        if obj_id:
            data = [r for r in data if r["obj_id"] == obj_id]
        return data


# ══════════════════════════════════════════════════════════════════════════════
# STATIC MIGRATION DATA
# ══════════════════════════════════════════════════════════════════════════════

MFG_MODS = {"PP", "PP-PI", "QM", "PM"}

STEP_DEFS = [
    {"key": "PREREQ",      "label": "Pre-Requisite Setup",            "color": "#880E4F"},
    {"key": "EXV_CFG",     "label": "Setup Extraction Config (ECZ)",  "color": "#1565C0"},
    {"key": "EXTRACT",     "label": "Run Extraction (ECZ)",           "color": "#0277BD"},
    {"key": "PRE_VAL",     "label": "Pre-Load Validation",            "color": "#00838F"},
    {"key": "APPROVAL1",   "label": "Approval (Pre-Load)",            "color": "#2E7D32"},
    {"key": "EXT_NUM",     "label": "Setup External Number Range",    "color": "#E65100"},
    {"key": "LOAD",        "label": "Load via LSMW / BAPI / IDoc",   "color": "#1F5C2E"},
    {"key": "ECD_CFG",     "label": "Setup Extraction Config (ECD)",  "color": "#1565C0"},
    {"key": "EXTRACT_ECD", "label": "Run Extraction (ECD)",           "color": "#0277BD"},
    {"key": "POST_VAL",    "label": "Post-Load Validation",           "color": "#00838F"},
    {"key": "APPROVAL2",   "label": "Approval (Post-Load)",           "color": "#2E7D32"},
    {"key": "EXT_REVERT",  "label": "Revert External Number Range",   "color": "#C62828"},
]

# Objects that require external number range
EXT_NUM_OBJECTS = {
    "DM-025",  # Equipment Master — OIEN
    "DM-054",  # Maintenance Plan — IP20
    "DM-070",  # Open QN — IW20
    "DM-041",  # General Task Lists — OIL4
    "DM-073",  # Equipment Task Lists — OIL4
    "DM-074",  # FL Task Lists — OIL4
    "DM-039",  # Master Recipe — C2N2
    "DM-043",  # Inspection Plan — OQ62
    "DM-077",  # Maintenance Orders — OION
    "DM-076",  # Process Orders — CO82
}

# Objects with PREREQ steps
PREREQ_OBJECTS = {
    "DM-055",  # Work Centers / Resources — PK05, CSSL/CSKS
    "DM-025",  # Equipment Master — OIEN
    "DM-054",  # Maintenance Plan — IP20, IP11
    "DM-041",  # General Task Lists — OIL4, WC dependency
    "DM-073",  # Equipment Task Lists — OIL4, EQ Master dependency
    "DM-074",  # FL Task Lists — OIL4, WC Pass 3
    "DM-042",  # MIC — BD64, WE20, namespace
    "DM-039",  # Master Recipe — C2N2
    "DM-043",  # Inspection Plan — OQ62
    "DM-083",  # Document BOM — WE20, BD64
    "DM-076",  # Process Orders — CO82
    "DM-077",  # Maintenance Orders — OION
    "DM-070",  # Open QN — IW20
    "DM-078",  # Open Maint Notifs — IW20
}

OBJ_DEPS = {
    "DM-055": {"needs": [], "blocker": "CSSL/CSKS CO master data not loaded in ECD", "owner": "FICO Team"},
    "DM-018": {"needs": [], "blocker": "", "owner": ""},
    "DM-025": {"needs": ["DM-018"], "blocker": "", "owner": "",
                "note": "Equipment Master requires Functional Locations loaded first. 1,355 failed Mock 0 on this."},
    "DM-041": {"needs": ["DM-055"], "blocker": "", "owner": ""},
    "DM-073": {"needs": ["DM-025", "DM-055"], "blocker": "Equip TL reverted to internal numbering in Mock 1", "owner": "SI MFG Team"},
    "DM-074": {"needs": ["DM-018", "DM-055"], "blocker": "FL TL Pass 3 needs ARBPL lookup after WC loads", "owner": "Angelo (ABAP)"},
    "DM-042": {"needs": [], "blocker": "SAP namespace activation pending (SAP_EHS_*/LOBM_*)", "owner": "Angelo (Basis)"},
    "DM-043": {"needs": ["DM-042"], "blocker": "ZCHA waiting on MIC fix and MM material load", "owner": "Angelo (Basis)"},
    "DM-054": {"needs": [], "blocker": "IP11 manual entry required — 7 strategies, 62 packages", "owner": "SI MFG Team"},
    "DM-039": {"needs": [], "blocker": "ABAP fix for duplicate KTEXT within recipe groups pending", "owner": "Angelo (ABAP)"},
    "DM-037": {"needs": [], "blocker": "Production BOM: 29/25,481 in Mock 1 — ALE IDoc root cause investigation required", "owner": "SI MFG Team / Angelo"},
    "DM-076": {"needs": ["DM-037", "DM-039", "DM-038"], "blocker": "Prerequisites incomplete (BOM, Recipe, Prod Version)", "owner": "SI MFG Team"},
    "DM-083": {"needs": ["DM-037"], "blocker": "", "owner": ""},
}

MOCK1_RESULTS = {
    "DM-055": {"loaded": 643,   "errors": 0,     "rate": "100%",  "note": "Complete after CSSL/CSKS fix. OBJID/KAPID unresolved."},
    "DM-018": {"loaded": 1765,  "errors": 0,     "rate": "100%",  "note": "Complete."},
    "DM-025": {"loaded": 13851, "errors": 1,     "rate": "~100%", "note": "One record outside external number range — manual creation."},
    "DM-037": {"loaded": 29,    "errors": 25452, "rate": "0.1%",  "note": "CRITICAL — ALE IDoc not generated for most records. Root cause unknown."},
    "DM-083": {"loaded": None,  "errors": None,  "rate": "—",     "note": "Not in Mock 1 scope."},
    "DM-040": {"loaded": 2606,  "errors": 2,     "rate": "99.9%", "note": "Near complete."},
    "DM-041": {"loaded": 1111,  "errors": 5,     "rate": "99.6%", "note": "Near complete. 5 failures to investigate."},
    "DM-073": {"loaded": 892,   "errors": 2,     "rate": "99.8%", "note": "Near complete. Internal numbering revert — confirm strategy."},
    "DM-074": {"loaded": 27,    "errors": 0,     "rate": "100%",  "note": "Complete."},
    "DM-042": {"loaded": None,  "errors": None,  "rate": "—",     "note": "Not in Mock 1 scope (ALE IDoc setup pending)."},
    "DM-039": {"loaded": 18188, "errors": 6962,  "rate": "72.3%", "note": "Material inactive/discontinued. Business cleansing required."},
    "DM-043": {"loaded": 20,    "errors": 0,     "rate": "100%",  "note": "Complete."},
    "DM-038": {"loaded": 13054, "errors": 0,     "rate": "100%",  "note": "Complete. T437P not transported — add to Mock 2 config checklist."},
    "DM-054": {"loaded": 3704,  "errors": 1113,  "rate": "76.9%", "note": "Z4 fiscal year variant not maintained. Order type config gaps."},
    "DM-070": {"loaded": 9,     "errors": 0,     "rate": "100%",  "note": "Complete."},
    "DM-071": {"loaded": 233,   "errors": 895,   "rate": "20.7%", "note": "Origin 17/04 exclusions required. Vendor migration incomplete."},
    "DM-076": {"loaded": 2,     "errors": 42,    "rate": "4.5%",  "note": "Not representative — prerequisites incomplete. Retry after full chain."},
    "DM-078": {"loaded": 18444, "errors": 0,     "rate": "100%",  "note": "Complete."},
    "DM-077": {"loaded": 1276,  "errors": 980,   "rate": "56.6%", "note": "Z4 fiscal year variant. 2024 orders need business cleansing decision."},
}

MOCK2_ACTIONS = {
    "DM-037": [
        "Investigate why BOM IDocs not created despite active materials",
        "Evaluate LSMW CS01 recording as fallback method",
        "Do not retry ALE without root cause analysis",
    ],
    "DM-039": [
        "Review inactive/discontinued materials against agreed scope",
        "Confirm recipe version-history business rules",
        "Carry proven LSMW conversion rules forward as Mock 2 baseline",
    ],
    "DM-055": [
        "Finalise OBJID/KAPID number range strategy (dummy WC approach)",
        "Validate CIF/APO downstream impact before Mock 2",
        "Confirm pooled capacities exist in ECD pre-load",
    ],
    "DM-054": [
        "Maintain fiscal year variant Z4 for 2025 in ECD",
        "Fix period version Z4 configuration",
        "Confirm order type fully maintained",
    ],
    "DM-076": [
        "Complete full prerequisite chain: Material→BOM→Recipe→ProdVersion",
        "Re-run only after all upstream objects confirmed complete",
    ],
    "DM-071": [
        "Apply origin 17 exclusion filter (manual lots not permitted)",
        "Apply origin 04 exclusion or scope validation",
        "Complete Vendor migration first",
        "Complete MATMAS/MATQM",
    ],
    "DM-073": [
        "Confirm Equipment TL number range strategy before Mock 2",
        "Investigate why external numbering reverted to internal in Mock 1",
    ],
}

# Full object list (19 MFG objects)
OBJECTS = [
    {"id": "DM-055", "name": "Work Centers / Resources",          "module": "PP-PI", "wave": "W3", "seq": 1,  "tool": "LSMW",                "vol": 643,   "ext_num": False, "prereq": True},
    {"id": "DM-018", "name": "Functional Locations",              "module": "PM",    "wave": "W3", "seq": 2,  "tool": "LSMW",                "vol": 1765,  "ext_num": False, "prereq": False},
    {"id": "DM-025", "name": "Equipment Master",                  "module": "PM",    "wave": "W4", "seq": 3,  "tool": "LSMW",                "vol": 13852, "ext_num": True,  "prereq": True},
    {"id": "DM-037", "name": "Bill of Material (Production BOM)", "module": "PP",    "wave": "W5", "seq": 4,  "tool": "ALE IDoc (WE20/BD64)","vol": 25481, "ext_num": False, "prereq": False},
    {"id": "DM-083", "name": "Document BOM",                      "module": "PP",    "wave": "W5", "seq": 5,  "tool": "ALE IDoc (WE20/BD64)","vol": None,  "ext_num": False, "prereq": True},
    {"id": "DM-040", "name": "Equipment BOM",                     "module": "PM",    "wave": "W5", "seq": 6,  "tool": "LSMW",                "vol": 2608,  "ext_num": False, "prereq": False},
    {"id": "DM-041", "name": "General Task Lists (PLNTY=A)",      "module": "PM",    "wave": "W5", "seq": 7,  "tool": "LSMW",                "vol": 1116,  "ext_num": True,  "prereq": True},
    {"id": "DM-073", "name": "Equipment Task Lists (PLNTY=E)",    "module": "PM",    "wave": "W5", "seq": 8,  "tool": "LSMW",                "vol": 894,   "ext_num": True,  "prereq": True},
    {"id": "DM-074", "name": "FL Task Lists (PLNTY=T)",           "module": "PM",    "wave": "W5", "seq": 9,  "tool": "LSMW",                "vol": 27,    "ext_num": True,  "prereq": True},
    {"id": "DM-042", "name": "Master Inspection Characteristics", "module": "QM",    "wave": "W5", "seq": 10, "tool": "ALE IDoc (QPMK)",     "vol": 4152,  "ext_num": False, "prereq": True},
    {"id": "DM-039", "name": "Master Recipe (PP-PI)",             "module": "PP",    "wave": "W5", "seq": 11, "tool": "LSMW",                "vol": 25150, "ext_num": True,  "prereq": True},
    {"id": "DM-043", "name": "Inspection Plan (QM-M05)",          "module": "QM",    "wave": "W5", "seq": 12, "tool": "LSMW",                "vol": 20,    "ext_num": True,  "prereq": True},
    {"id": "DM-038", "name": "Production Version",                "module": "PP",    "wave": "W5", "seq": 13, "tool": "LSMW",                "vol": 13054, "ext_num": False, "prereq": False},
    {"id": "DM-054", "name": "Maintenance Plan",                  "module": "PM",    "wave": "W6", "seq": 14, "tool": "LSMW",                "vol": 4817,  "ext_num": True,  "prereq": True},
    {"id": "DM-070", "name": "Open Quality Notifications",        "module": "QM",    "wave": "W9", "seq": 15, "tool": "LSMW",                "vol": 9,     "ext_num": True,  "prereq": True},
    {"id": "DM-071", "name": "Open Inspection Lots",              "module": "QM",    "wave": "W9", "seq": 16, "tool": "LSMW",                "vol": 1128,  "ext_num": False, "prereq": False},
    {"id": "DM-076", "name": "Open Process Orders",               "module": "PP",    "wave": "W10","seq": 17, "tool": "LSMW",                "vol": 44,    "ext_num": True,  "prereq": True},
    {"id": "DM-078", "name": "Open Maintenance Notifications",    "module": "PM",    "wave": "W10","seq": 18, "tool": "LSMW",                "vol": 18444, "ext_num": True,  "prereq": True},
    {"id": "DM-077", "name": "Open Maintenance Orders",           "module": "PM",    "wave": "W10","seq": 19, "tool": "LSMW",                "vol": 2256,  "ext_num": True,  "prereq": True},
]
