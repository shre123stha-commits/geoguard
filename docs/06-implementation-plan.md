# GeoGuard-EO — Implementation Plan

> Build in small vertical slices. Each phase ends with something runnable and a passing test suite. Work the phases **in order** and update `07-tracker.md` after every task.
> Sizes are rough effort for one developer: S ≈ ≤ 2 h, M ≈ half a day, L ≈ 1–2 days.
> **All tools and services must be free** (techspec §0).

---

## Strategy

1. **Prove the science first.** The riskiest part is the detection pipeline, not the CRUD. Phase 1 validates it with scripts before any UI depends on it.
2. **Then wrap it** with database, API, worker, scheduler, and UI.
3. **Finish like a product:** onboarding, docs, backup, packaging, and evaluation, not just features.

## Phase 0 — Foundation (M)

| # | Task | Done when |
|---|------|-----------|
| 0.1 | Create repo `geoguard-eo`, `.gitignore` (venv, node_modules, `.env`, `data/`), README skeleton, `docs/` with these files | Repo pushed |
| 0.2 | Backend project: venv, `pyproject.toml`/requirements, ruff + mypy + pytest configured | `pytest` runs (0 tests OK) |
| 0.3 | Native PostgreSQL 15 + PostGIS installed; `geoguard_db` and `geoguard_test` created; `CREATE EXTENSION postgis` works | `SELECT PostGIS_Full_Version()` returns |
| 0.4 | Typed `Settings` (pydantic-settings), `.env.example`, logging setup | App boots reading config |
| 0.5 | FastAPI skeleton with `/health` (checks DB) | `GET /health` → 200 |
| 0.6 | Frontend: Vite + React + TS + Tailwind + router + ESLint/Prettier + Vitest | `npm run dev` and `npm test` work |
| 0.7 | Pre-commit hooks (ruff, prettier) and a simple CI workflow (lint + tests) | CI green |
| 0.8 | **Free-Services Audit:** check current terms/limits of the imagery catalog(s), basemap tiles, and any alert channel; record in tracker | Table filled in tracker §6 |

## Phase 1 — Detection Prototype (L) ⭐ highest risk

Work in `backend/app/pipeline/` with scripts or a notebook; no DB needed yet.

| # | Task | Done when |
|---|------|-----------|
| 1.1 | Pick the test area (Q1). Get parcel boundaries as GeoJSON (OpenStreetMap export or hand-traced, e.g., with geojson.io). Choose baseline/current windows in the same season | Files in `data/samples/` |
| 1.2 | `ImagerySource` interface + first concrete source; search S2/S1 scenes for the area | Scene lists printed with dates and cloud cover |
| 1.3 | Windowed band reads for S2 (B04, B08, B11, SCL) and S1 (VV, VH); cache to `data/cache/` | Arrays returned on a common grid |
| 1.4 | Cloud mask + median composites per period | Composite previews look sane |
| 1.5 | Indices NDVI, NDBI, BUI + unit tests on synthetic arrays | Tests pass |
| 1.6 | Optical change mask with default thresholds + preview | Visual check against a basemap |
| 1.7 | Radar preprocessing (dB, speckle filter) and change mask | Visual check |
| 1.8 | Vectorize, cleanup, min area; clip to parcels; geodesic area | GeoJSON opens correctly in QGIS or geojson.io |
| 1.9 | Decision-level fusion table + score formula + unit tests | Tests pass; confidence classes assigned |
| 1.10 | Hand-label ~20–50 sites; compute precision/recall; tune thresholds; record in tracker | Metrics table filled |
| 1.11 | **Go/no-go:** if quality is poor, adjust season, thresholds, min area, or area before continuing | Decision Log entry |

**Exit criteria:** an end-to-end script that takes parcels + two periods and outputs detection GeoJSON with confidence, reproducibly.

## Phase 2 — Database and Models (M)

| # | Task | Done when |
|---|------|-----------|
| 2.1 | SQLAlchemy 2 + GeoAlchemy2 models for all tables in `05-schema.md` | Models import cleanly |
| 2.2 | Alembic setup; migrations `0001`–`0006` | `alembic upgrade head` works on an empty DB |
| 2.3 | Repositories for users, parcels, scans, schedules, detections + integration tests on `geoguard_test` | Tests pass |
| 2.4 | Seed script: first admin from env vars (must change password at first login) | Admin can be created on a fresh DB |

## Phase 3 — Auth, Users, and Parcels API (M)

| # | Task | Done when |
|---|------|-----------|
| 3.1 | Password hashing, JWT, `/auth/login`, `/auth/me`, role dependencies, login throttling | Auth tests pass |
| 3.2 | Parcels API: create from GeoJSON (upload or drawn), validate, list/get/patch/delete, area calc | Tests pass incl. invalid and self-intersecting geometry |
| 3.3 | Standard error format, pagination helpers, CORS | Consistent errors in tests |
| 3.4 | Users API: create, list, change role, deactivate, reset password, change own password, last-admin protection | Tests pass |

## Phase 4 — Scans, Worker, and Scheduler (L)

| # | Task | Done when |
|---|------|-----------|
| 4.1 | `POST/GET /scans`, `GET /scans/{id}`, `rerun` | Endpoints tested |
| 4.2 | Worker loop (`SKIP LOCKED` polling), status/progress updates, crash recovery | Worker processes a queued scan |
| 4.3 | Integrate the Phase 1 pipeline behind the worker; persist scenes, detections, evidence | A scan on the test area produces DB rows |
| 4.4 | Evidence thumbnails (before/after/change) stored under `data/evidence/` | Files exist |
| 4.5 | `LocalFolderSource` + fixtures so pipeline tests run offline | Pipeline integration test passes without network |
| 4.6 | Scheduler (APScheduler): schedules API (`/schedules`), cron parsing, next-run computation, duplicate-queue guard, missed-run handling | A schedule due in a minute creates a scan |

## Phase 5 — Detections API and Review Logic (M)

| # | Task | Done when |
|---|------|-----------|
| 5.1 | `GET /detections` with filters, bbox, pagination; `GET /detections/{id}` | Tested |
| 5.2 | `PATCH /detections/{id}/status` with allowed transitions, notes, reason codes, audit rows | Invalid transitions rejected in tests |
| 5.3 | Protected file-serving route for evidence and reports | Unauthorized access returns 401/403 |
| 5.4 | `GET /detections/export` (GeoJSON and CSV) | Files open correctly in QGIS/Excel |

## Phase 6 — Frontend Core (L)

> Apply `04-design.md` once it exists. Until then, use plain, consistent Tailwind in reusable components so restyling is cheap.

| # | Task | Done when |
|---|------|-----------|
| 6.1 | Typed API client, TanStack Query, auth context, protected routes, forced password change screen | Login works end to end |
| 6.2 | App layout, navigation, shared empty/loading/error components | Used across pages |
| 6.3 | Parcels pages: list + map; **Add parcels** with Upload tab (preview + error list) and **Draw** tab (terra-draw: add, edit, delete, live area) | Admin can add parcels both ways |
| 6.4 | Scan create form and scan detail with progress polling | Admin can run a scan |
| 6.5 | Detections list/map split view with filters and export button | Filters and export work |
| 6.6 | Detection detail: map, before/after slider, metrics, status actions, history | Officer can review |
| 6.7 | Dashboard: latest scan, “new since last visit”, onboarding checklist | Shows real data |
| 6.8 | Schedules page and Users page (admin) and Alerts settings | Admin can manage them |

## Phase 7 — Reports and Alerts (M)

| # | Task | Done when |
|---|------|-----------|
| 7.1 | PDF report builder (ReportLab) with template and disclaimer | PDF downloads with all fields |
| 7.2 | Alert provider interface + `console` provider; alert rows, minimum confidence setting, retry | Confirming a `high` detection logs an alert |
| 7.3 | Optional free providers: Telegram bot and SMTP email | Test message received (optional) |

## Phase 8 — Hardening and Release (M–L)

| # | Task | Done when |
|---|------|-----------|
| 8.1 | Sample data seed and first-run onboarding flow | A fresh install shows a useful first screen |
| 8.2 | Apply `04-design.md`; responsive and accessibility pass | Lighthouse accessibility ≥ 90 on key pages |
| 8.3 | Start scripts (`scripts/start-dev.ps1`), README with setup, user guide, limitations; optional Docker Compose | New machine setup works from README only |
| 8.4 | Backup and restore (`pg_dump`/`pg_restore` + `data/` folder), verified once | Restore test passes |
| 8.5 | Evaluation write-up (`docs/evaluation.md`): method, labeled set, precision/recall, failure cases | Written |
| 8.6 | Security and cleanup pass: secrets scan, dependency audit, dead code, error-message review; tag `v1.0.0` | Release tagged |

## Phase 9 — v1.1 (optional)

Match repeated detections across scans, radar-only mode for cloudy periods, review keyboard shortcuts, statistics dashboard.

## Phase 10 — v2: Learned Model (optional)

1. Build a labeled tile dataset from the test area.
2. Train a small segmentation model (U-Net family) on stacked S2 (+ S1) tiles using free tooling (local machine or a free notebook tier).
3. Evaluate against the index baseline; keep the better one per confidence class.
4. Swap in through the same `optical` interface; record results.

## Dependencies Between Phases

```
0 → 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8
         └──────────────┘ (2 can start once 1 has stable output shapes)
```
Frontend Phase 6 can begin in parallel with Phase 5 using mocked API responses.

## Risk Checkpoints

| Checkpoint | Question | If “no” |
|------------|----------|---------|
| End of Phase 0 | Are all needed services confirmed free with acceptable limits? | Choose alternatives before writing code that depends on them. |
| End of Phase 1 | Are detections believable in the test area and season? | Change area/season, raise min area, adjust radar weighting; do not proceed to UI. |
| End of Phase 4 | Does a full scan finish in reasonable time on the laptop? | Reduce AOI, add caching, work at lower resolution for previews. |
| End of Phase 6 | Can a new user finish add parcel → scan → review without help? | Simplify the UI before adding features. |

## Working Agreement for AI Assistants

- Implement **one task ID at a time**; put the task ID in the commit message.
- Read `08-rules.md` first and follow it.
- After finishing, update `07-tracker.md` (status, notes, decisions, handoff) in the same change.
