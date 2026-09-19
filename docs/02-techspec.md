# GeoGuard-EO — Technical Specification

> Read after `01-PRD.md`. Source of truth for architecture, algorithms, APIs, and conventions.
> Versions below are targets; verify the latest compatible versions when installing and record any change in `07-tracker.md` (Decision Log).

---

## 0. Hard Constraint: 100% Free Resources

No paid APIs, subscriptions, or metered services anywhere in the project. Every external service must be free for the usage this project needs, or be self-hostable. Before adding any service, check its **current** terms and limits and record the result in the tracker's *Free-Services Audit* table.

| Need | Free choice | Caveat to verify |
|------|-------------|------------------|
| Satellite imagery | Public STAC catalog serving Sentinel-2 L2A and terrain-corrected Sentinel-1 (Microsoft Planetary Computer as primary; Copernicus Data Space Ecosystem as fallback for Sentinel-2) | Free, may need a free account/token; rate limits and terms can change |
| Basemap tiles | OpenStreetMap standard tiles for development, configurable via `BASEMAP_URL` | Usage policy forbids heavy use; attribution required; for heavier use self-host free PMTiles. Any satellite basemap must have terms that allow this use |
| Database | Local PostgreSQL 15 + PostGIS | none |
| Compute | The user's own machine | Raster work is CPU/RAM heavy; keep AOIs small |
| Alerts | `console` provider (default); optional Telegram Bot API or SMTP email | No paid SMS |
| Hosting | Local for v1 | Free tiers typically have small storage/CPU and sleeping or ephemeral instances, so they suit the web app at most, not the raster worker |
| CI | GitHub Actions (free for public repos) | Minutes limits on private repos |
| Fonts/icons | Open-source (e.g., Inter, Lucide) | Check licenses |

## 1. Architecture Overview

```
┌────────────────────┐        HTTPS/JSON        ┌───────────────────────────┐
│  React + Vite SPA  │ ───────────────────────▶ │      FastAPI backend       │
│  (MapLibre/Leaflet)│ ◀─────────────────────── │  routers → services → repos│
└────────────────────┘                          └──────────┬────────────────┘
                                                            │
                          ┌─────────────────────────────────┼───────────────────────────────┐
                          │                                 │                               │
                 ┌────────▼────────┐             ┌──────────▼─────────┐         ┌───────────▼───────────┐
                 │ PostgreSQL 15   │             │  Job runner         │         │ File storage (local)  │
                 │ + PostGIS 3.x   │◀────────────│  (background worker)│────────▶│ data/scenes, thumbs,  │
                 │ (metadata,      │  results    │  scan pipeline      │         │ reports                │
                 │  geometries)    │             └──────────┬──────────┘         └───────────────────────┘
                 └─────────────────┘                        │
                                                 ┌──────────▼───────────┐
                                                 │ Public STAC catalog  │
                                                 │ Sentinel-1 / Sentinel-2│
                                                 └──────────────────────┘
```

Principles: thin routers, logic in services, DB access in repositories, pure functions for the raster/algorithm code so it can be unit-tested without a database or network.

## 2. Tech Stack

| Layer | Choice | Notes |
|-------|--------|-------|
| Language (backend) | Python 3.11+ | Type hints everywhere |
| API | FastAPI + Uvicorn | OpenAPI auto-docs at `/docs` |
| ORM/DB | SQLAlchemy 2.x, GeoAlchemy2, Alembic | Migrations are mandatory |
| Database | PostgreSQL 15 + PostGIS 3.x | Native Windows install; Docker optional |
| Geo/raster | rasterio, numpy, shapely, geopandas, pyproj, scikit-image / scipy | Windowed reads, no full-scene loads |
| Satellite data | STAC client (`pystac-client`) against a free public catalog; `planetary-computer` signing if that catalog is used | Provider is behind an interface (see §5.1) |
| Jobs | DB-backed worker (polls the `scans` table) + in-process scheduler (APScheduler) for recurring scans | No Celery/Redis |
| Reports | ReportLab (pure Python; WeasyPrint needs extra system libraries on Windows) | PDF generation |
| Alerts | Provider interface; `console` (default); optional free `telegram` and `email` (SMTP) providers | No paid SMS; never hard-code a vendor |
| Auth | JWT (access token), argon2/bcrypt hashing | Roles: `admin`, `officer` |
| Frontend | React 18 + TypeScript + Vite | |
| Map | MapLibre GL JS + `terra-draw` (polygon drawing and vertex editing) | Before/after slider component |
| UI | Tailwind CSS (final styling from `04-design.md`) | |
| Server state | TanStack Query | |
| Testing | pytest, pytest-asyncio, httpx; Vitest + React Testing Library | |
| Quality | ruff, mypy (backend); ESLint, Prettier, `tsc --noEmit` (frontend) | |

## 3. Repository Layout

```
geoguard-eo/
├── docs/                      # these .md files
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── core/              # config, security, logging
│   │   ├── db/                # session, base, models/, migrations via alembic/
│   │   ├── api/               # routers (auth, parcels, scans, detections, reports, alerts)
│   │   ├── schemas/           # Pydantic request/response models
│   │   ├── services/          # business logic
│   │   ├── repositories/      # DB queries
│   │   ├── pipeline/          # scan pipeline (pure + orchestration)
│   │   │   ├── sources/       # imagery provider interface + implementations
│   │   │   ├── optical.py     # S2 indices + change
│   │   │   ├── radar.py       # S1 backscatter change
│   │   │   ├── fusion.py      # decision-level fusion
│   │   │   ├── vectorize.py   # raster → polygons, cleanup
│   │   │   └── evidence.py    # before/after thumbnails
│   │   ├── reports/           # PDF builder
│   │   ├── alerts/            # alert provider interface + impls (console, telegram, email)
│   │   └── scheduler.py       # recurring scans (APScheduler)
│   ├── alembic/
│   ├── tests/
│   ├── pyproject.toml         # or requirements.txt
│   └── .env.example
├── frontend/
│   └── src/ (app, pages, components, features, api, hooks, lib)
├── data/                      # gitignored: scenes cache, thumbnails, reports, sample data, eval labels
└── README.md
```

## 4. Configuration (`backend/.env.example`)

```
DATABASE_URL=postgresql+psycopg://postgres:CHANGE_ME@localhost:5432/geoguard_db
JWT_SECRET=CHANGE_ME
JWT_EXPIRE_MINUTES=480
DATA_DIR=./data
IMAGERY_PROVIDER=stac_public
STAC_API_URL=
CLOUD_COVER_MAX=30
ALERT_PROVIDER=console          # console | telegram | email
TELEGRAM_BOT_TOKEN=
SMTP_HOST=
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
SMTP_FROM=
BASEMAP_URL=https://tile.openstreetmap.org/{z}/{x}/{y}.png
BASEMAP_ATTRIBUTION=© OpenStreetMap contributors
SCHEDULER_ENABLED=true
FIRST_ADMIN_EMAIL=
FIRST_ADMIN_PASSWORD=CHANGE_ME
CORS_ORIGINS=http://localhost:5173
```

All settings load through a single typed `Settings` class (pydantic-settings). No `os.getenv` scattered in code.

## 5. Scan Pipeline (core algorithm)

### 5.1 Imagery source interface

```python
class ImagerySource(Protocol):
    def search_optical(self, bbox, date_range, max_cloud) -> list[SceneRef]: ...
    def search_radar(self, bbox, date_range) -> list[SceneRef]: ...
    def read_bands(self, scene: SceneRef, bands: list[str], bbox, out_crs, resolution) -> np.ndarray: ...
```

Implement one concrete source first (public STAC catalog serving Sentinel-2 L2A and terrain-corrected Sentinel-1). Use terrain-corrected radar (e.g., RTC products) so ESA SNAP is **not** required. A `LocalFolderSource` implementation is used for tests and offline sample data.

### 5.2 Steps

1. **Define AOI:** union bounding box of selected parcels, buffered ~100 m. Work in a projected CRS (UTM zone of the AOI) for area and distance.
2. **Search scenes:** baseline and current periods for S2 (cloud ≤ `CLOUD_COVER_MAX`) and S1 (same orbit direction/relative orbit where possible).
3. **Read windowed bands** (never entire scenes):
   - S2: B04 (red), B08 (NIR), B11 (SWIR1, resampled 20→10 m), SCL (scene classification).
   - S1: VV and VH backscatter.
4. **Cloud/shadow mask (S2):** drop pixels where SCL ∈ {cloud shadow, cloud medium/high, cirrus, saturated/defective}. Keep a per-pixel valid mask.
5. **Temporal composite:** per period, take the per-pixel **median** of valid observations (reduces noise/clouds). S1: median in linear power, then convert to dB.
6. **Optical indices per period:**
   - `NDVI = (B08 − B04) / (B08 + B04)`
   - `NDBI = (B11 − B08) / (B11 + B08)`
   - `BUI = NDBI − NDVI` (built-up index; higher = more built-up/bare-impervious)
7. **Optical change:** `dBUI = BUI_current − BUI_baseline`. Candidate pixels satisfy `dBUI > T_bui` **and** `NDVI_baseline − NDVI_current > T_ndvi_drop` (vegetation/soil turned built). Thresholds: start with defaults (`T_bui = 0.15`, `T_ndvi_drop = 0.10`) or scene-adaptive Otsu on `dBUI` within the parcels; expose in scan parameters and tune on the labeled evaluation set.
8. **Radar change:** convert to dB; `dSigma = VV_current_dB − VV_baseline_dB` (and VH). New built structures commonly raise backscatter (double-bounce). Candidate pixels: `dSigma > T_sar` (default ~ +2 to +3 dB) after speckle filtering (e.g., 3×3 median or Lee filter). Compute on a common grid with the optical data.
9. **Decision-level fusion (per candidate region, not per pixel):**
   - Vectorize the optical mask and the radar mask separately after cleanup.
   - For each optical region, compute the fraction of its area also covered by the radar mask (`sar_overlap`), and vice versa for radar-only regions.
   - Confidence rules (defaults, tunable):

     | Optical | Radar (overlap ≥ 0.3) | Class |
     |---------|-----------------------|-------|
     | yes | yes | `high` |
     | yes | no  | `medium` |
     | no  | yes | `low` (radar-only, often vegetation/moisture change) |
   - Numeric score in [0,1]: weighted combination of normalized optical magnitude, radar magnitude, overlap, and region compactness. Document the exact formula in code and in `07-tracker.md` when finalized.
10. **Vectorize + cleanup:** morphological opening/closing (3×3), remove regions below `MIN_AREA_M2` (default 400 m²), simplify polygons lightly, reproject to EPSG:4326 for storage.
11. **Clip and classify against parcels:** `ST_Intersection` with parcel geometry; keep only the intersecting part; store `parcel_id` and `overlap_area_m2`. Detections outside all parcels are discarded (v1).
12. **Evidence:** render before/after RGB thumbnails (cropped around each detection with margin) plus a small index-change preview; store paths.
13. **Persist:** write scan record, scene references, detections, and evidence in one transaction; set scan status.

### 5.3 Known failure modes to handle explicitly
- No valid scenes in a period → scan fails with a clear message (or widens the window if configured).
- Mismatched CRS/grids → resample to a single target grid before any arithmetic.
- Seasonal mismatch → warn if baseline and current periods are not the same season (±30 days of year).
- Huge AOI → reject above a configured limit (e.g., 100 km²) with a helpful error.

### 5.4 Evaluation
- Hand-label 20–50 sites in the test area (true new construction / not) using high-resolution basemap comparison.
- Report precision, recall, and F1 by confidence class in the tracker and README. Keep the labeled set in `data/eval/` as GeoJSON.

## 6. API Design

Base path `/api/v1`. JSON. Errors use `{ "error": { "code": str, "message": str, "details": any } }`. Pagination: `?page=1&page_size=20`, response includes `total`.

| Method | Path | Role | Description |
|--------|------|------|-------------|
| POST | `/auth/login` | public | email + password → JWT |
| GET | `/auth/me` | any | current user |
| GET/POST | `/parcels` | admin (POST), any (GET) | list / create from GeoJSON (uploaded file or a polygon drawn in the UI; stored with `source` = `upload` or `drawn`) |
| GET/PATCH/DELETE | `/parcels/{id}` | admin (PATCH/DELETE) | manage |
| POST | `/scans` | admin | create scan (parcels, periods, params) |
| GET | `/scans` | any | list with status |
| GET | `/scans/{id}` | any | detail incl. params, scenes, progress |
| POST | `/scans/{id}/rerun` | admin | new scan with same params |
| GET | `/detections` | any | filterable list (scan, parcel, class, status, date, bbox) |
| GET | `/detections/{id}` | any | detail with geometry, metrics, evidence URLs |
| PATCH | `/detections/{id}/status` | officer/admin | set status + note (writes audit row) |
| POST | `/detections/{id}/report` | officer/admin | generate PDF, return URL |
| GET | `/detections/export` | any | GeoJSON/CSV export of the filtered list |
| GET/POST | `/users` | admin | list / create users |
| PATCH | `/users/{id}` | admin | change role, activate/deactivate, reset password |
| POST | `/auth/change-password` | any | change own password |
| GET/POST | `/schedules` | admin | list / create recurring scans |
| PATCH/DELETE | `/schedules/{id}` | admin | edit, pause, delete |
| GET/PUT | `/settings/alerts` | admin | alert provider, recipients, minimum confidence |
| GET | `/health` | public | liveness + DB check |

Geometry is exchanged as GeoJSON (`Feature`/`FeatureCollection`) in EPSG:4326. Files (thumbnails, PDFs) are served from a protected `/files/...` route.

## 7. Background Jobs

- Creating a scan inserts a row with status `queued`; a worker picks it up (poll every few seconds, `SELECT ... FOR UPDATE SKIP LOCKED`), sets `running`, updates `progress` and `message`, then `succeeded`/`failed`.
- One scan at a time in v1; concurrency limit is configurable.
- Crashes: on startup, any `running` scan older than a timeout is marked `failed` with reason `worker_restart`.
- **Scheduler:** each active row in `scan_schedules` has a cron expression. When due, the scheduler creates a normal `queued` scan (so it follows the same worker path), with the current window ending today and the baseline chosen by the schedule's rule (default: same season, previous year). Missed runs (app was off) are not replayed; the next due time is recomputed on startup. Sentinel revisit is a few days, so weekly or monthly schedules are typical.

## 8. Security

- Hash passwords (argon2 preferred). Enforce minimum length.
- JWT signed with `JWT_SECRET`; short-lived; validate role on every protected route via dependencies.
- Validate all uploads: size limit, geometry validity, CRS, vertex count cap.
- CORS restricted to configured origins.
- Basic login throttling (for example, 5 failures then a cooldown); first-admin password must be changed at first login.
- No secrets in the repository; `.env` gitignored, `.env.example` committed.
- Sanitize and bound all user text (notes) and filenames; never build file paths from raw user input.

## 9. Logging and Observability

- Structured logs (JSON or key=value) with `scan_id`, `detection_id`, `user_id` where relevant.
- Each pipeline step logs duration and pixel/feature counts.
- `/health` reports DB connectivity and migration state.

## 10. Testing Strategy

| Level | What | Tools |
|-------|------|-------|
| Unit | index math, thresholds, masks, fusion table, area calc, vectorize | pytest with small synthetic numpy rasters |
| Integration | repositories with a test PostGIS DB; API routes with auth | pytest + httpx; separate `geoguard_test` DB |
| Pipeline | end-to-end on a small local fixture scene set using `LocalFolderSource` (no network) | pytest |
| Frontend | components and key flows | Vitest + RTL |
| Manual | release readiness checklist in tracker | — |

Minimum bar for a phase to be “done”: tests written and passing, linters clean, docs and tracker updated.

## 11. Performance Notes

- Use windowed reads on Cloud-Optimized GeoTIFFs; avoid full-scene downloads.
- Cache fetched windows under `data/cache/` keyed by scene ID + bbox + bands.
- Use a spatial (GiST) index on all geometry columns.
- Return simplified geometries for list views and full geometry only in detail views.

## 12. Deployment

- v1: local run (Uvicorn + Vite dev server). Document the exact commands in README.
- Optional: Dockerfile/Compose for reproducibility; not required to start.
- Hosting is out of scope for v1. If ever hosted, use only free tiers and keep the worker/pipeline on a machine you control (see §0).
- Provide PowerShell start scripts (`scripts/start-dev.ps1`) and a documented backup/restore procedure using `pg_dump` / `pg_restore`.

## 13. v2 Extension: Learned Model

- Frame as semantic segmentation of built-up areas on stacked S2 (+ optional S1) tiles.
- Data: hand-labeled tiles from the test area plus an open labeled built-up dataset for pretraining; report IoU/F1 against the index baseline.
- Keep the same `fusion` and `vectorize` interfaces so the model is a drop-in replacement for the optical step.
- Note: models trained for high-resolution imagery do not transfer directly to 10 m Sentinel data; do not claim building-footprint-level accuracy from Sentinel.

## 14. Definition of Done (global)

A task is done only if: code merged on a feature branch with a clear commit message, typed, linted, tested, documented where behavior changed, tracker updated, and no secrets committed.
