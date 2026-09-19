# GeoGuard-EO — Progress Tracker

> Single source of truth for status. **Update this file at the end of every task.** Any AI assistant or human must read it before starting work.
> Status legend: `[ ]` todo · `[~]` in progress · `[x]` done · `[!]` blocked · `[-]` dropped

**Current phase:** Phase 0 — Foundation (code complete; 0.3 and 0.7 need manual verification on the Windows machine)
**Current task:** 1.1 (blocked on Q1 — test area choice)
**Last updated:** 2026-09-19
**Last updated by:** Arena Agent

---

## 1. Phase Overview

| Phase | Name | Status | Notes |
|-------|------|--------|-------|
| 0 | Foundation | [~] | Code done and verified in a Linux sandbox; 0.3 (PostGIS) and 0.7 (CI green) await the owner's Windows machine / first push |
| 1 | Detection Prototype | [ ] | Highest risk; go/no-go at 1.11; blocked on Q1 for task 1.1 |
| 2 | Database and Models | [ ] | |
| 3 | Auth, Users, and Parcels API | [ ] | |
| 4 | Scans, Worker, and Scheduler | [ ] | |
| 5 | Detections API and Review Logic | [ ] | |
| 6 | Frontend Core | [ ] | Needs `04-design.md` for final styling |
| 7 | Reports and Alerts | [ ] | Console alerts first; Telegram/email optional |
| 8 | Hardening and Release | [ ] | |
| 9 | v1.1 (optional) | [ ] | |
| 10 | v2 learned model (optional) | [ ] | |

## 2. Task Checklist

### Phase 0 — Foundation
- [x] 0.1 Repo, `.gitignore`, README skeleton, `docs/` (local git init done; **push pending**)
- [x] 0.2 Backend project + ruff/mypy/pytest
- [!] 0.3 PostgreSQL 15 + PostGIS installed; `geoguard_db` and `geoguard_test` ready — **owner must run on Windows**: `.\scripts\check-postgis.ps1` (sandbox had no PostgreSQL)
- [x] 0.4 Typed Settings, `.env.example`, logging
- [x] 0.5 FastAPI skeleton + `/health` (returns 200 `ok` with DB, 200 `degraded` without — verified only the degraded path so far)
- [x] 0.6 Frontend Vite + React + TS + Tailwind + tooling
- [~] 0.7 Pre-commit + CI — files written; **"CI green" unverified until first push to GitHub**
- [x] 0.8 Free-Services Audit (fill §6)

### Phase 1 — Detection Prototype
- [ ] 1.1 Test area, parcel boundaries (OSM export or hand-traced), date windows
- [ ] 1.2 `ImagerySource` + first concrete source; scene search
- [ ] 1.3 Windowed band reads + cache
- [ ] 1.4 Cloud mask + composites
- [ ] 1.5 Indices + unit tests
- [ ] 1.6 Optical change mask
- [ ] 1.7 Radar preprocessing + change mask
- [ ] 1.8 Vectorize, cleanup, clip to parcels, area
- [ ] 1.9 Fusion + score + tests
- [ ] 1.10 Labeled set + metrics + threshold tuning
- [ ] 1.11 Go/no-go decision

### Phase 2 — Database and Models
- [ ] 2.1 Models
- [ ] 2.2 Alembic + migrations 0001–0006
- [ ] 2.3 Repositories + integration tests
- [ ] 2.4 First-admin seed

### Phase 3 — Auth, Users, and Parcels API
- [ ] 3.1 Auth + roles + login throttling
- [ ] 3.2 Parcels API (upload and drawn GeoJSON)
- [ ] 3.3 Errors, pagination, CORS
- [ ] 3.4 Users API + last-admin protection

### Phase 4 — Scans, Worker, and Scheduler
- [ ] 4.1 Scans API
- [ ] 4.2 Worker loop + crash recovery
- [ ] 4.3 Pipeline integration + persistence
- [ ] 4.4 Evidence thumbnails
- [ ] 4.5 `LocalFolderSource` + offline fixtures
- [ ] 4.6 Scheduler + schedules API

### Phase 5 — Detections API and Review Logic
- [ ] 5.1 Detections list/detail
- [ ] 5.2 Status transitions + audit
- [ ] 5.3 Protected file serving
- [ ] 5.4 Export GeoJSON/CSV

### Phase 6 — Frontend Core
- [ ] 6.1 API client, auth, protected routes, forced password change
- [ ] 6.2 Layout + shared states
- [ ] 6.3 Parcels pages (upload + draw)
- [ ] 6.4 Scan create + detail
- [ ] 6.5 Detections list/map + export
- [ ] 6.6 Detection detail + review actions
- [ ] 6.7 Dashboard + onboarding checklist
- [ ] 6.8 Schedules, Users, Alerts settings pages

### Phase 7 — Reports and Alerts
- [ ] 7.1 PDF report (ReportLab)
- [ ] 7.2 Alert interface + console provider
- [ ] 7.3 Telegram / email providers (optional)

### Phase 8 — Hardening and Release
- [ ] 8.1 Sample data + first-run onboarding
- [ ] 8.2 Design system applied + a11y/responsive pass
- [ ] 8.3 Start scripts, README, user guide (optional Docker Compose)
- [ ] 8.4 Backup and restore verified
- [ ] 8.5 Evaluation write-up
- [ ] 8.6 Security/cleanup pass + tag `v1.0.0`

## 3. Decision Log

Record every meaningful decision here (append only).

| # | Date | Decision | Reason | Alternatives considered |
|---|------|----------|--------|-------------------------|
| D1 | (fill) | v1 change detection = Sentinel-2 index-based change (NDVI/NDBI/BUI) + Sentinel-1 backscatter change, fused at decision level; learned model deferred to v2 | Ships end to end fast, explainable, no labeled dataset needed to start | Train a DL model first; pretrained footprint model (does not transfer to 10 m data) |
| D2 | (fill) | Native PostgreSQL 15 + PostGIS on Windows; Docker optional | Docker Desktop setup problems on the dev machine | Docker Compose |
| D3 | (fill) | Terrain-corrected radar from a public catalog instead of manual SNAP processing | Removes heavy desktop tooling from the pipeline | ESA SNAP graphs |
| D4 | (fill) | DB-backed worker (`SKIP LOCKED`) plus APScheduler; no Celery/Redis | Simplicity for a solo local project | Celery + Redis |
| D5 | (fill) | **100% free resources and services only** | Owner requirement | Paid SMS, paid map/tile APIs, paid hosting |
| D6 | (fill) | Alerts default to `console`; optional free Telegram/email providers; no paid SMS | Free-only; SMS sender registration and cost | Paid SMS gateway |
| D7 | (fill) | Parcels can be added by GeoJSON upload **and** by drawing on the map | Officers may not have GeoJSON files | Upload-only |
| D8 | (fill) | Goal is a good working product, not a demo; scheduling, user management, export, backup docs are in v1 | Owner requirement | Demo/portfolio scope |
| D9 | (fill) | PDF reports with ReportLab | Pure Python; WeasyPrint needs extra system libraries on Windows | WeasyPrint |
| D10 | (fill) | Parcel boundaries for the test area from OpenStreetMap export or hand-tracing | Free and easy to verify visually | Official cadastral data (usually not public) |
| D11 | 2026-09-19 | Pinned React 18 (Vite's current template ships React 19) and replaced the template's `oxlint` with ESLint + Prettier | Match techspec §2 and rules §5 exactly | Accept React 19 (would need a doc change) |
| D12 | 2026-09-19 | Geospatial packages are an optional extra `pip install -e ".[geo]"`, separate from the core install | Phase 0 must work even if rasterio/GDAL wheels fail on Windows (rules §12); core API has no raster deps | Single requirements list |
| D13 | 2026-09-19 | `/health` is served both at `/health` and `/api/v1/health`; it returns HTTP 200 with `status: degraded` when the DB is unreachable (never 500) | Liveness must not depend on the DB; `database` field carries the DB state (techspec §9) | 503 when DB down |
| D14 | 2026-09-19 | Standard error format `{error:{code,message,details}}` is installed globally from task 0.5 (not deferred to 3.3) | Every response, including 404/422, should be consistent from day one | Add in 3.3 |
| D15 | 2026-09-19 | Vite dev server proxies `/api`, `/files`, `/health` to `localhost:8000`; browser code uses relative URLs only | Avoids CORS in dev and keeps the API host out of frontend code | Absolute API URL via env var |
| D16 | 2026-09-19 | Primary imagery: Microsoft Planetary Computer STAC (no account needed since June 2024, incl. Sentinel-1 RTC). Fallback: CDSE STAC v1 `https://stac.dataspace.copernicus.eu/v1` (free account for downloads) | Audit in §6 | CDSE as primary (needs token from day one) |

## 4. Open Questions

| # | Question | Owner | Needed by | Status |
|---|----------|-------|-----------|--------|
| Q1 | Which test area (and its parcel source) for development and evaluation? Pick a place you can verify easily against a satellite basemap. Suggested options near Chennai/Tambaram: (a) Pallikaranai marsh reserve edge, (b) Adyar/Cooum riverbed stretch, (c) a government plot the owner knows. Export boundaries from OSM (overpass-turbo.eu → export GeoJSON) or trace at geojson.io | Shrestha | Task 1.1 | open |
| Q6 | GitHub repo URL and visibility (public → free unlimited CI minutes) | Shrestha | Task 0.7 verification | open |
| Q7 | Project license (MIT recommended) | Shrestha | 8.3 | open |
| Q2 | SMS provider | — | — | resolved: console-only, optional Telegram/email (D6) |
| Q3 | Upload-only or also drawing | — | — | resolved: both (D7) |
| Q4 | Public demo hosting | — | — | dropped: working product, local run (D8) |
| Q5 | Design reference prompt for `04-design.md` | Shrestha | Task 6.2 (final styling at 8.2) | open |

## 5. Blockers

| Date | Blocker | Task | Resolution |
|------|---------|------|------------|
| 2026-09-19 | No PostgreSQL in the build sandbox, so 0.3 could not be executed and `/health` `ok` path is untested against a real PostGIS | 0.3, 0.5 | Owner runs `.\scripts\check-postgis.ps1` on Windows and hits `/health` |
| 2026-09-19 | CI not yet run (no remote) | 0.7 | Push to GitHub and check Actions |

## 6. Free-Services Audit (fill during Task 0.8)

| Service | Purpose | Free? | Account/token needed | Limits or rules to respect | Fallback | Checked on |
|---------|---------|-------|----------------------|----------------------------|----------|------------|
| Planetary Computer STAC (S2 L2A, S1 RTC) | Imagery | Yes (data + STAC API). Hub compute retired June 2024; data/API unchanged | **No** — anonymous SAS tokens work for all collections incl. `sentinel-1-rtc` (confirmed by MS maintainers, May 2024; token endpoint returned HTTP 200 anonymously on 2026-09-19) | Rate limits on anonymous SAS tokens (unpublished; be gentle, cache windows). S2 L2A license "proprietary" = Copernicus free-use terms; S1 RTC is CC-BY-4.0 → attribute Microsoft + Copernicus. Sign asset URLs with `planetary-computer` | Copernicus Data Space | 2026-09-19 |
| Copernicus Data Space (CDSE) | Imagery fallback (S2 L2A; S1 GRD is not terrain-corrected) | Yes | Free account (OAuth token) for asset download; STAC search anonymous. STAC v1 root `https://stac.dataspace.copernicus.eu/v1` reachable (HTTP 200) | Monthly free quota; **owner must read current quotas on dataspace.copernicus.eu** — needs manual check | Planetary Computer | 2026-09-19 |
| OpenStreetMap tiles | Basemap | Yes, for light dev use | no | Tile Usage Policy: valid User-Agent/Referer, no bulk download, attribution "© OpenStreetMap contributors", no heavy production use → self-host PMTiles if usage grows. Tile fetch HTTP 200 on 2026-09-19 | Self-hosted PMTiles (Protomaps, free) | 2026-09-19 |
| Telegram Bot API | Optional alerts | Yes | bot token (free via @BotFather) | ~30 msg/s per bot; recipients must start the bot first | console | not yet checked (Phase 7) — needs manual check |
| SMTP (free mailbox) | Optional alerts | Yes | app password | Gmail: ~500 mails/day for free accounts; app password requires 2FA | console | not yet checked (Phase 7) — needs manual check |
| GitHub Actions | CI | Yes | GitHub account | Unlimited minutes for public repos; 2,000 min/month on private free plan | local checks | 2026-09-19 (general knowledge; verify plan on github.com/pricing) |
| @fontsource Inter / Inter Tight / JetBrains Mono, Lucide icons | Fonts/icons | Yes (OFL / ISC) | no | Keep license files in node_modules; no CDN needed | system fonts | 2026-09-19 |

**Result of the Phase 0 risk checkpoint:** all required services are free for this project's usage. Two items are marked *needs manual check* (CDSE quotas; Telegram/SMTP terms before Phase 7). None blocks Phase 1.

## 7. Evaluation Results (fill during Task 1.10)

| Run | Date | Thresholds (`T_bui`, `T_ndvi_drop`, `T_sar`, min area) | Labeled sites | Precision | Recall | F1 | Notes |
|-----|------|-------------------------------------------------------|---------------|-----------|--------|----|-------|
| 1 | | | | | | | |

Also record precision separately for each confidence class (`high`, `medium`, `low`).

## 8. Release Readiness Checklist

- [ ] Fresh Windows setup works from README only
- [ ] Add parcel (upload and draw) → scan → review → report works without help
- [ ] Scheduled scan runs unattended and produces detections
- [ ] Export GeoJSON/CSV opens correctly in QGIS/Excel
- [ ] Alerts visible (console; Telegram/email if enabled)
- [ ] Backup and restore tested
- [ ] Limitations written clearly in README and in the app
- [ ] No secrets in git history; dependencies audited
- [ ] Evaluation write-up published in `docs/evaluation.md`
- [ ] All services confirmed free (audit up to date)

## 9. Change Log

| Date | Task | Summary | By |
|------|------|---------|----|
| 2026-09-19 | 0.1 | `git init`, `.gitignore`, `README.md`, `docs/` (all 9 md files), `AGENTS.md` copy of rules, `data/*/.gitkeep`, `scripts/` | Arena Agent |
| 2026-09-19 | 0.2 | `backend/pyproject.toml` (ruff line 100, mypy strict, pytest asyncio auto), `requirements.txt`, package skeleton per techspec §3 | Arena Agent |
| 2026-09-19 | 0.4 | `app/core/config.py` (pydantic-settings `Settings`, SecretStr for secrets, CORS list parsing), `app/core/logging.py` (key=value formatter with scan_id/detection_id/user_id context), `.env.example` | Arena Agent |
| 2026-09-19 | 0.5 | `app/main.py` factory + lifespan, `app/api/health.py`, `app/services/health.py` (SELECT 1, PostGIS_Version, alembic revision), `app/api/errors.py` standard error format, `app/db/session.py`; 7 pytest tests | Arena Agent |
| 2026-09-19 | 0.6 | Vite + React 18 + TS strict + Tailwind (tokens from 04-design §3), react-router, TanStack Query, MapLibre/terra-draw/fontsource deps installed, ESLint flat config + Prettier, Vitest + RTL; `HealthPage` with loading/error/data states; 2 Vitest tests | Arena Agent |
| 2026-09-19 | 0.7 | `.pre-commit-config.yaml` (ruff, prettier, private-key & large-file checks), `.github/workflows/ci.yml` (backend + frontend jobs) | Arena Agent |
| 2026-09-19 | 0.8 | Free-Services Audit table §6 filled with live checks | Arena Agent |

## 10. Session Handoff Notes

> Write 3–5 lines at the end of each working session: what was done, what is half-done, what to do next, gotchas. The next assistant reads this first.

- **Done (2026-09-19, Arena Agent):** Phase 0 code for 0.1, 0.2, 0.4, 0.5, 0.6, 0.7, 0.8. Verified in a Linux sandbox (Python 3.13, Node 20): `ruff check` / `ruff format --check` / `mypy` clean, `pytest` 7 passed; `eslint` / `tsc -b` clean, `vitest` 2 passed, `vite build` OK; uvicorn boots, `GET /health` → 200 `degraded` (no DB in sandbox); Vite proxy to `/api/v1/health` works.
- **Half-done:** 0.3 needs the owner's Windows PostGIS (`.\scripts\check-postgis.ps1`), then confirm `/health` returns `database: ok` and a PostGIS version. 0.7 needs the first push so Actions runs. Repo not pushed yet (Q6).
- **Next:** 1.1 — blocked on Q1 (test area). Owner picks the area and produces `data/samples/parcels.geojson`; then install geo extras `pip install -e ".[geo]"` on Windows and report any wheel errors.
- **Gotchas:** Docs say Python 3.11+ — sandbox used 3.13; verify `pip install -e ".[geo]"` on the owner's Python version (rasterio wheels for 3.13 on Windows may lag; 3.11/3.12 are safest). Vite's template now ships React 19 — we pinned 18 (D11). `vite.config.ts` has `allowedHosts: ['.e2b.app', 'localhost']` for sandbox previews; harmless but can be removed.
- **Resume commands (PowerShell):** `cd geoguard-eo; .\.venv\Scripts\Activate.ps1; cd backend; pytest; cd ..\frontend; npm test`
