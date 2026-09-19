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

Phase 0 (Foundation) — see `docs/07-tracker.md` for the exact state.

## Stack

Python 3.11+ · FastAPI · SQLAlchemy 2 + GeoAlchemy2 + Alembic · PostgreSQL 15 + PostGIS ·
rasterio / numpy / shapely · STAC (Planetary Computer, CDSE fallback) · APScheduler · ReportLab ·
React 18 + Vite + TypeScript + Tailwind · MapLibre GL + terra-draw · TanStack Query · pytest · Vitest

## Setup (Windows, PowerShell)

### 1. Prerequisites (all free)

- Python 3.11 or newer, Node.js 20 LTS, Git
- PostgreSQL 15 with PostGIS 3 (native install via the EDB installer + Stack Builder → PostGIS)

### 2. Database

```powershell
.\scripts\check-postgis.ps1 -PgUser postgres
# or manually in psql:
#   CREATE DATABASE geoguard_db;  CREATE DATABASE geoguard_test;
#   \c geoguard_db   CREATE EXTENSION postgis; CREATE EXTENSION pgcrypto;
#   SELECT PostGIS_Full_Version();
```

### 3. Backend

```powershell
cd backend
python -m venv ..\.venv
..\.venv\Scripts\Activate.ps1      # if blocked: Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
pip install -e ".[dev]"
Copy-Item .env.example .env        # then edit DATABASE_URL and JWT_SECRET
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
