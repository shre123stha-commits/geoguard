# GeoGuard-EO

Watch protected land from above. Verify on the ground.

GeoGuard-EO watches user-defined government or protected land parcels with free
Sentinel-1 (radar) and Sentinel-2 (optical) imagery, flags **likely new built-up surface**
inside those parcels, fuses optical and radar evidence into a confidence class
(`high` / `medium` / `low`), and gives reviewers a map, before/after imagery, area, PDF
reports, exports, scheduled scans, e-mail alerts and a review workflow with an audit trail.

> **Satellite detection is a screening aid. Verify on the ground before acting.**
> Sentinel-2 is 10 m per pixel; anything under roughly 400 m² is unreliable and is not
> reported. A detection is a reason to look, never a finding.

Built with **100 % free** data, software and services: Microsoft Planetary Computer STAC
(no account), Supabase free tier (or your own PostgreSQL), Esri World Imagery / CARTO
basemap tiles, Gmail App Password for alerts. See `docs/` for the full specification and
`docs/evaluation.md` for how well it works.

## Status

**v1.0.0** — Phases 0–8 complete. Everything below has been exercised end to end on the
sample area. Known limits are listed at the bottom of this file and inside the app.

## Stack

Python 3.11+ · FastAPI · SQLAlchemy 2 + GeoAlchemy2 + Alembic · PostgreSQL 15+ + PostGIS 3 ·
rasterio / numpy / shapely / scikit-image · STAC (Planetary Computer; Copernicus CDSE fallback) ·
APScheduler · ReportLab · React 18 + Vite + TypeScript + Tailwind · MapLibre GL + terra-draw ·
TanStack Query · pytest · Vitest · Playwright (manual QA)

---

## Setup on a new Windows machine (PowerShell)

### 1. Install once

- **Python 3.11 or newer** (python.org; tick *Add to PATH*)
- **Node.js 20 LTS** (nodejs.org)
- **Git** (git-scm.com)
- A **Supabase** account (supabase.com, free) — or PostgreSQL 15+ with PostGIS installed locally

```powershell
git clone https://github.com/<you>/geoguard-eo.git
cd geoguard-eo
```

### 2. Database

**Supabase (default).** Create a project (region Mumbai `ap-south-1`), note the database
password. Dashboard → **Connect** → **Session pooler** → copy the URI. You will paste it
into `.env` in the next step with two edits: `postgresql://` → `postgresql+psycopg://` and
append `?sslmode=require`.

Free-tier notes: the project pauses after 7 idle days (un-pause in the dashboard); use the
*Session pooler* string on port 5432 — the direct string is IPv6-only and the transaction
pooler (6543) does not support migrations.

<details><summary>Local PostgreSQL instead</summary>

```powershell
.\scripts\check-postgis.ps1 -PgUser postgres
#  in psql:  CREATE DATABASE geoguard_db;  CREATE DATABASE geoguard_test;
```
Use the `localhost` URLs commented in `.env.example`.
</details>

### 3. Backend

```powershell
cd backend
python -m venv ..\.venv
..\.venv\Scripts\Activate.ps1      # if blocked: Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
pip install -e ".[dev,geo]"
Copy-Item .env.example .env
notepad .env
```

In `.env` set at least:

| Key | Value |
|---|---|
| `DATABASE_URL`, `TEST_DATABASE_URL` | the Supabase URI (edited as above) — same value for both |
| `JWT_SECRET` | `python -c "import secrets;print(secrets.token_hex(32))"` |
| `FIRST_ADMIN_EMAIL`, `FIRST_ADMIN_PASSWORD` | your e-mail and a temporary password (≥ 10 chars) |
| `SMTP_*` | see *Alerts* below — optional, can be done later |

Then create the schema, the first admin, the sample parcels **and a first completed scan**
so the app is not empty:

```powershell
alembic upgrade head
python scripts\composites_to_local_scenes.py ..\data          # offline sample scenes (once)
python scripts\seed.py --sample-parcels ..\data\samples\parcels.geojson --sample-scan
uvicorn app.main:app --reload --port 8000
```

`http://localhost:8000/health` should answer `{"status":"ok","database":"ok","postgis":"3.x",…}`.

### 4. Frontend

Second PowerShell window:

```powershell
cd geoguard-eo\frontend
npm install
npm run dev
```

Open **http://localhost:5173**, sign in with `FIRST_ADMIN_EMAIL` / `FIRST_ADMIN_PASSWORD`,
choose a new password when asked. From then on: `.\scripts\start-dev.ps1` from the repo root
starts both servers.

### 5. Alerts by e-mail (optional, 2 minutes)

Google Account → Security → 2-Step Verification → **App passwords** → create one named
`GeoGuard`. In `backend\.env`:

```
ALERT_PROVIDER=email
ALERT_RECIPIENTS=you@example.org        # comma-separated for several
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=you@gmail.com
SMTP_PASSWORD=<16-character app password>
SMTP_FROM=you@gmail.com
```

Restart the backend. **Settings → Alerts** shows *ON*; use **Send a test message** to check.
Every confirmed `high` detection then e-mails the recipients (threshold adjustable).

---

## Using it

| Step | Where | Notes |
|---|---|---|
| Add parcels | **Parcels → Add parcels** | Upload GeoJSON (WGS84, ≤ 5 MB, ≤ 500 features) or draw on the map. Invalid geometries are listed and skipped, never silently dropped. |
| Run a scan | **Scans → New scan** | Pick parcels and two periods. Same season in both periods gives the most reliable result. Progress shows live; a typical 1–2 km² area takes 1–3 min online, seconds offline. |
| Review | **Detections** | Sorted by confidence then size. Open a row: satellite map with the outline, before/after slider, change map, measurements. **Confirm**, **Plan field visit**, or **Dismiss** with a reason. Every change is in the history. |
| Report | Detection page → **Generate report** | One-page PDF with evidence, measurements, history and the disclaimer. |
| Export | **Detections → GeoJSON / CSV** | Honours the current filters. GeoJSON opens in QGIS; CSV (with WKT) opens in Excel. |
| Recurring scans | **Schedules** (admin) | Weekly / monthly / cron; baseline = same season last year by default. Missed runs are skipped, not replayed. |
| Users | **Users** (admin) | Admins manage everything; officers review. Temporary passwords must be changed at first sign-in. |

Roles, transitions and edge cases: `docs/03-appflow.md`.

## Backup and restore

```powershell
.\scripts\backup.ps1                          # → backups\<timestamp>\{db.dump, data\}
.\scripts\restore.ps1 -From .\backups\<timestamp> [-Clean]
```
Needs `pg_dump` / `pg_restore` on PATH. Verified once on 2026-09-20 (dump → empty database →
restore → 8 detections, 3 parcels, schema 0006). `backend\.env` is **not** included — keep it
safe separately.

## Quality checks

```powershell
cd backend;  ruff check .; ruff format --check .; mypy; pytest       # 120 tests
cd frontend; npm run lint; npm run typecheck; npm test; npm run build
pre-commit install                                                     # hooks
```

Tests need `TEST_DATABASE_URL` (they run in schema `geoguard_test` of the same database) and
skip themselves if it is unreachable. Accessibility: zero axe-core WCAG 2 A/AA violations on
all main pages at 1280 px and 390 px (2026-09-20).

## Security notes

argon2id passwords (≥ 10 chars), short-lived JWT, role checks on every route, five failed
logins → 5-minute cooldown per e-mail/IP, 6 MB request-body cap, strict security headers,
CORS limited to `CORS_ORIGINS`, evidence/report files served only to signed-in users from
fixed subfolders, opaque 500 responses, no secrets in the repository (`.env` is gitignored).

## Limitations (read before relying on results)

1. **Resolution.** 10 m pixels. Single houses under ~400 m² are not reported; scattered small
   buildings will be missed. Plots, sheds, fill, roads and compounds are the target.
2. **False positives.** Bare soil, ploughing, drying ponds and seasonal vegetation loss look
   like construction optically. `high` (optical + radar agree) is the class to trust first;
   treat `medium` and `low` as prompts to look, not as results.
3. **Clouds.** Monsoon months may have too few clear scenes; the scan warns when the
   composite is thin. Prefer dry-season windows.
4. **Timing.** A detection tells you change happened *between* the two windows, not when.
5. **Evidence base.** Precision figures come from one landscape and 9 labelled sites
   (`docs/evaluation.md`); they are indicative. Label more sites as you review.
6. **Dependencies.** Imagery comes from public catalogues whose terms and uptime can change;
   basemap tiles are third-party; a Supabase free project pauses when idle.
7. **Compute.** Runs on a laptop; one scan at a time. Very large AOIs (> ~50 km²) will be slow.

## Repository layout

`backend/` (FastAPI app, pipeline, worker, alerts, reports) · `frontend/` (React SPA) ·
`docs/` (PRD, techspec, appflow, design, schema, plan, tracker, rules, evaluation) ·
`data/` (gitignored: cache, evidence, reports; committed: samples, eval labels) ·
`scripts/` (PowerShell helpers: start-dev, db-migrate, check-postgis, backup, restore).

## License

TBD by the owner (open-source recommended).
