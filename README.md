# DMFC Migration Tracker — Streamlit App

Collaborative cutover tracker for the DMFI→DMFC SAP ECC carve-out.  
PP · PP-PI · QM · PM — Go-Live: 2 January 2027.

## What it does

- **Two people can update simultaneously** — both Miguel and Miah can have the page open, update steps, raise blockers, and see each other's changes after a refresh
- **Step-level timestamps** — each step (Extract, Pre-Val, Load, Post-Val, etc.) has Start/Stop buttons that capture timestamps automatically
- **Dependency tracking** — objects know what they depend on and show as Blocked/Waiting/Ready
- **Critical path** — computed live from actual durations
- **Blocker management** — raise a blocker with reason + owner, clear it when resolved
- **Audit trail** — every change is logged with who made it and when
- **CSV export** — download the full cutover log as evidence

---

## Setup

### 1. Supabase (database — free tier is sufficient)

1. Create a project at https://supabase.com
2. Go to **SQL Editor** and run this once:

```sql
create table if not exists object_status (
    id          text primary key,
    status      text default 'Not Started',
    m1_loaded   integer,
    m1_errors   integer,
    notes       text,
    updated_by  text,
    updated_at  timestamptz default now()
);

create table if not exists step_log (
    id          bigint generated always as identity primary key,
    obj_id      text,
    step_key    text,
    status      text,
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
```

3. Copy your **Project URL** and **anon public key** from Settings → API.

### 2. Local development

```bash
pip install -r requirements.txt
export SUPABASE_URL="https://your-project.supabase.co"
export SUPABASE_KEY="your-anon-key"
streamlit run app.py
```

Without Supabase env vars it runs in local memory mode (no persistence, single user).

### 3. Streamlit Cloud deployment

1. Push this folder to a GitHub repo (private is fine)
2. Go to https://share.streamlit.io → New app → select your repo → `app.py`
3. In **Advanced settings → Secrets**, add:

```toml
SUPABASE_URL = "https://your-project.supabase.co"
SUPABASE_KEY = "your-anon-key"
```

4. Deploy. Share the URL with your teammate.

---

## How shifts work

Both users just go to the same URL. Changes persist immediately in Supabase.  
Hit **Refresh** in the header to see the other person's latest updates.

No export/import needed — the database is the shared state.

---

## Files

```
app.py          — main entry point, tabs, login
data.py         — all static migration data (objects, steps, deps, M1 results)
                  + Supabase client + local fallback
views/
  mfg.py        — MFG Workstream tab (step checklist, status updates)
  runbook.py    — Cutover Runbook (readiness, blockers, critical path)
  summary.py    — Summary (charts, M1 results table, audit log)
  schedule.py   — Schedule reference (M1 dates, Mock 2 focus areas)
requirements.txt
README.md
```

---

## Adding more objects

Edit the `OBJECTS` list in `data.py`. Add the DM-ID to `EXT_NUM_OBJECTS` or `PREREQ_OBJECTS` if needed. Add a `MOCK1_RESULTS` entry. Done — the rest of the app picks it up automatically.
