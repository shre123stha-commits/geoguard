# GeoGuard-EO

Watch protected land from above. Verify on the ground.

GeoGuard-EO watches user-defined government or protected land parcels with free
Sentinel-1 (radar) and Sentinel-2 (optical) imagery, flags **possible new construction**
or land-cover change inside those parcels, fuses optical and radar evidence into a
confidence class (`high` / `medium` / `low`), and gives reviewers a map, before/after
imagery, area, PDF reports, exports, scheduled scans, and a review workflow.

> **Satellite detection is a screening aid. Verify on the ground before acting.**
> Sentinel-2 is 10 m per pixel; structures under roughly 200–400 m² are unreliable.
> A detection is never proof of a violation.

Built with **100% free** data, software, and services. See `docs/` for the full spec.

## Status

Phases 0–6 done (backend API, worker, scheduler, detections + review, full web UI). Phase 7 (PDF reports, alerts) next — see `docs/07-tracker.md` for the exact state.

## Stack

Python 3.11+ · FastAPI · SQLAlchemy 2 + GeoAlchemy2 + Alembic · PostgreSQL 15 + PostGIS ·
rasterio / numpy / shapely · STAC (Planetary Computer, CDSE fallback) · APScheduler · ReportLab ·
React 18 + Vite + TypeScript + Tailwind · MapLibre GL + terra-draw · TanStack Query · pytest · Vitest

## Setup (Windows, PowerShell)

### 1. Prerequisites (all free)

- Python 3.11 or newer, Node.js 20 LTS, Git
- A **Supabase** project (free tier; managed PostgreSQL with PostGIS) — or a native PostgreSQL 15 + PostGIS 3 install if you prefer on-prem

### 2. Database (Supabase, default)

1. Create a free project at supabase.com (region: Mumbai `ap-south-1`); note the database password.
2. Dashboard → **Connect** (top bar) → **Session pooler** → copy the URI.
3. In `backend\.env` set **both** `DATABASE_URL` and `TEST_DATABASE_URL` to that URI with two edits:
   `postgresql://` → `postgresql+psycopg://` and append `?sslmode=require`.
   Keep `TEST_DATABASE_SCHEMA=geoguard_test` (tests run in their own schema of the same database).
4. From the repo root with the venv active: `.\scripts\db-migrate.ps1` (migrations enable PostGIS
   and create the first admin from `FIRST_ADMIN_EMAIL` / `FIRST_ADMIN_PASSWORD`).

Free-tier notes: the project pauses after 7 days without traffic (un-pause in the dashboard); use
the Session pooler string (port 5432) — the direct string is IPv6-only and the transaction pooler
(6543) does not support Alembic.

<details><summary>Alternative: native PostgreSQL 15 + PostGIS</summary>

```powershell
.\scripts\check-postgis.ps1 -PgUser postgres
#   CREATE DATABASE geoguard_db;  CREATE DATABASE geoguard_test;
```
Then use the `localhost` URLs commented in `.env.example`.
</details>

### 3. Backend

```powershell
cd backend
python -m venv ..\.venv
..\.venv\Scripts\Activate.ps1      # if blocked: Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
pip install -e ".[dev,geo]"
Copy-Item .env.example .env        # then edit DATABASE_URL, TEST_DATABASE_URL, JWT_SECRET, FIRST_ADMIN_*
uvicorn app.main:app --reload --port 8000
# http://localhost:8000/health  → {"status":"ok","database":"ok","postgis":"3.x", ...}
# http://localhost:8000/docs
```

Geospatial extras (Phase 1+): `pip install -e ".[geo]"`. If `rasterio`/`GDAL` wheels fail on
Windows, stop and report the error (see `docs/08-rules.md` §12) — a conda env is the fallback.

### 4. Frontend

```powershell
cd frontend
npm install
npm run dev        # http://localhost:5173 (proxies /api to the backend)
```

Open http://localhost:5173 and sign in with `FIRST_ADMIN_EMAIL` / `FIRST_ADMIN_PASSWORD` from
`backend\.env` (created by `scripts\seed.py`). The first sign-in asks you to choose a new
password. Admins create further accounts through `POST /api/v1/users` (UI arrives in Phase 6);
five failed logins pause that email/IP for five minutes.

### 4b. Running scans

Scans are queued through the API (or the **Run scan** button) and processed by a worker thread
inside the backend process (`WORKER_ENABLED=true`). Recurring scans (`/api/v1/schedules`) are
fired by a scheduler tick every minute (`SCHEDULER_ENABLED=true`).

Imagery comes from the public Planetary Computer STAC by default (`IMAGERY_PROVIDER=stac_public`).
For a no-network demo on the sample area, convert the Phase 1 composites once and switch provider:

```powershell
cd backend
python scripts\composites_to_local_scenes.py ..\data     # writes data\local_scenes\
# in .env:  IMAGERY_PROVIDER=local_folder
```

Evidence thumbnails land in `data\evidence\<scan>\<detection>\` (before/after false colour + change map)
and are served only to signed-in users via `/api/v1/files/...`. Export the filtered detections with
`GET /api/v1/detections/export?format=geojson|csv` (or the buttons in the review screen).

### 5. Quality checks

```powershell
# backend
cd backend; ruff check .; ruff format --check .; mypy; pytest
# frontend
cd frontend; npm run lint; npm run typecheck; npm test; npm run build
# hooks
pre-commit install
```

## Repository layout

See `docs/02-techspec.md` §3. Short version: `backend/` (FastAPI app, pipeline, worker),
`frontend/` (React SPA), `docs/` (PRD, techspec, appflow, design, schema, plan, tracker, rules),
`data/` (gitignored cache, evidence, reports, samples, eval labels), `scripts/` (PowerShell helpers).

## Limitations

See `docs/01-PRD.md` §10. In short: 10 m resolution, seasonal and bare-soil false positives,
cloud cover in monsoon months, dependence on public catalogs, laptop-bound compute.

## License

TBD by the owner (open-source recommended).
