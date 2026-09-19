# GeoGuard-EO — Progress Tracker

> Single source of truth for status. **Update this file at the end of every task.** Any AI assistant or human must read it before starting work.
> Status legend: `[ ]` todo · `[~]` in progress · `[x]` done · `[!]` blocked · `[-]` dropped

**Current phase:** Phase 0 — Foundation (code complete; 0.3 and 0.7 need manual verification on the Windows machine)
**Current task:** 2.1 (models) — prototype slice live (D42)
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
- [x] 1.1 Test area, parcel boundaries (OSM export or hand-traced), date windows — Pallikaranai marsh edge; 3 hand-traced parcels (1 change, 2 controls) in `data/samples/parcels.geojson`; windows 2020-01-15→03-31 vs 2023-01-15→03-31 in `windows.json`; validated (all valid, no overlaps, 19.8/4.7/3.4 ha, AOI 1.4×1.1 km)
- [x] 1.2 `ImagerySource` + first concrete source; scene search — Planetary Computer, anonymous; baseline 15 S2 / 6 S1, current 11 S2 / 6 S1 (all S1 descending rel-orbit 92)
- [x] 1.3 Windowed band reads + cache — **verified on owner's Windows over hotspot (13/8/18/9 s per scene, identical stats)**; `read_grid` via rasterio `reproject` onto a 143×108 px 10 m UTM-44N grid; ~2–4 s per scene; npz cache in `data/cache/`; previews in `docs/previews/1.3-first-reads.png`
- [x] 1.4 Cloud mask + composites — baseline 15 S2 (valid count p50 14) + 6 S1; current 11 S2 (p50 6) + 6 S1; 0 % NaN; offset-corrected reflectance on the same scale in both periods (B04 p50 0.129 vs 0.135); previews `docs/previews/1.4-composites.png`
- [x] 1.5 Indices + unit tests — `ndvi/ndbi/bui/compute_indices`, 5 synthetic tests (42 total); computed on composites; previews `docs/previews/1.5-indices-dbui.png`; naive default thresholds flag 17 % of AOI (too many — see D30)
- [x] 1.6 Optical change mask — water exclusion + median centering + 3×3 opening: West-1 4.7 %, Marsh 0 %, Builtup 0 %, outside 3.1 %; preview `docs/previews/1.6-optical-change-mask.png` (D31/D32)
- [x] 1.7 Radar preprocessing + change mask — 3×3 NaN-aware median speckle filter, dσ_VV centred, T_sar 2.5 dB, water excl., opening: West-1 7.2 %, Marsh 0 %, Builtup 5.6 %, outside 5.7 %; preview `docs/previews/1.7-radar-change-mask.png`
- [x] 1.8 Vectorize, cleanup, clip to parcels, area — optical 11 regions → 5 pieces in West-1 (0.94 ha); radar 35 → 6 pieces; `docs/samples/candidates_{optical,radar}.geojson`; preview `docs/previews/1.8-candidates-clipped.png` (D35/D36)
- [x] 1.9 Fusion + score + tests — `app/pipeline/fusion.py` (`idx-fusion-1.0.0`), 6 tests (61 total); test area: **3 high, 2 medium, 2 low in West-1; 1 low in Control-Builtup; 0 in Control-Marsh**; `docs/samples/detections.geojson`; preview `docs/previews/1.9-detections-confidence.png` (D37/D38)
- [x] 1.10 Labeled set + metrics + threshold tuning — 9 labelled sites (7 real, 2 unsure, 1 known miss); defaults: **high 3/3 = 100 %**, medium 1/1 (+1 unsure), low 2/2 (+1 unsure), overall precision 100 % (6 tp / 0 fp / 2 unsure), **recall 6/7 = 86 %**; 48-setting sweep shows defaults on the plateau; `app/pipeline/evaluate.py`, `scripts/evaluate_detections.py`, `docs/samples/{labels.geojson,eval_sweep.csv}` (D39–D41)
- [x] 1.11 Go/no-go — **GO** for Phase 2 with the index+fusion baseline (D43). Bonus: clickable prototype slice — `GET /parcels`, `GET /detections`, `POST /scans` (runs the real pipeline on saved composites in ~2 s), `POST /detections/{id}/status`; React/MapLibre review screen at `/` (D42)

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
| D17 | 2026-09-19 | Test area = Pallikaranai marsh edge, Chennai; parcels hand-traced at geojson.io; ≥1 change parcel + 2 control parcels (marsh interior, stable built-up); same dry-season windows (Jan–Mar) | Owner can verify locally; strong known construction pressure; dry season minimises cloud and seasonal-water false positives | Adyar/Cooum riverbed; unknown government plot |
| D18 | 2026-09-19 | Owner's Windows env verified: Python venv, `pip install -e ".[dev,geo]"` succeeded with wheels — rasterio 1.5.1, shapely 2.1.2, pyproj 3.8.0, numpy 2.5.3, pystac-client 0.9.0, planetary-computer 1.0.0, geoalchemy2 0.20.0, alembic 1.20.0 | Record real versions (techspec header asks for it) | conda |
| D19 | 2026-09-19 | mypy `python_version` set to 3.12 (project still `requires-python>=3.11`) | numpy ≥ 2.5 type stubs use PEP 695 `type` statements, which mypy rejects under a 3.11 target | Pin older numpy |
| D20 | 2026-09-19 | S2 search collapses reprocessed duplicates: one scene per (MGRS tile, acquisition time), keeping the newest processing baseline | PC catalog holds both original and 2024 Collection-1 reprocessed items for the same overpass; duplicates would double-weight scenes in the median composite | Keep both; prefer oldest |
| D21 | 2026-09-19 | S1: only the descending relative-orbit 92 track covers the AOI in both windows, so orbit matching (techspec §5.2 step 2) is automatically satisfied here; the source still records orbit fields for other AOIs | Observed in search results | — |
| D22 | 2026-09-19 | Common grid = north-up 10 m grid in the AOI's UTM zone, snapped outward to whole pixels (`app/pipeline/grid.py`). All bands (S2 10 m, S2 20 m B11, S1 RTC) are resampled onto it with rasterio `reproject`; bilinear for continuous bands, nearest for SCL. `reproject` computes the source window itself, so only the needed COG byte ranges are fetched | Techspec §5.2 step 3 and §5.3 (single target grid before arithmetic) | Read native windows and align later |
| D23 | 2026-09-19 | Cache = compressed `.npz` per (scene id, bands, crs, bounds, resolution) SHA-1 key under `data/cache/xx/`; atomic write via temp file | Simple, no extra deps, keyed by values we generate (never user input) | GeoTIFF cache; SQLite |
| D24 | 2026-09-19 | **S2 reflectance offset:** scenes with `s2:processing_baseline` ≥ 04.00 (from Jan 2022) carry a +1000 DN offset (BOA_ADD_OFFSET). Observed: baseline 2020 scenes are PB 02.12 (B04 p50 ≈ 1136), current 2023 scenes are PB 04.00/05.10 (B04 p50 ≈ 2332). `SceneRef.meta['processing_baseline']` is recorded; **task 1.4 must subtract 1000 for PB ≥ 04.00 before indices**, otherwise every pixel shows a fake brightening between periods | Would corrupt dBUI/dNDVI for every scan that spans 2022 | Ignore (wrong); use harmonized collection (not available on PC) |
| D25 | 2026-09-19 | SCL invalid set = {0 nodata, 1 saturated, 3 shadow, 8 cloud-med, 9 cloud-high, 10 cirrus, 11 snow}; keep 2 dark, 4 veg, 5 bare, 6 water, 7 unclassified | Techspec step 4 plus nodata/snow | Also drop 7 (would lose ~5 % of clear pixels) |
| D26 | 2026-09-19 | Per-scene STAC `eo:cloud_cover` is tile-wide (100×100 km) and unreliable for a 1.5 km AOI: e.g. 2023-01-30 says 26 % but the AOI is 100 % cloud; 2023-02-19 says 6.6 % but AOI is 67 % cloud/shadow. So the scene filter stays loose (≤ 30) and the **per-pixel SCL mask does the real work**; the median composite absorbs the rest | Observed in AOI SCL histograms | Compute AOI-local cloud % before reading full bands (possible optimisation, v1.1) |
| D27 | 2026-09-19 | Known quirk: SCL labels dark open water as "cloud shadow" (3) in some scenes, so water pixels get fewer valid observations (baseline count min = 2 over the ponds, land ≥ 10). Accepted for v1: water is not a construction target, and medians of ≥ 2 obs are still stable | Visible in valid-count preview | Custom water re-inclusion via NDWI |
| D28 | 2026-09-19 | Fast-fail on blocked storage: `GDAL_HTTP_CONNECTTIMEOUT=10`, `GDAL_HTTP_TIMEOUT=60`, retries 2; connection failures raise `ImageryError("Cannot reach imagery storage host …")` | Owner's Wi-Fi blocks Azure Blob (blocker §5); readable errors per FR-6 | Default 21 s hangs per band |
| D29 | 2026-09-19 | Indices are computed on **offset-corrected reflectance composites**, never on single scenes or raw DNs; safe division returns NaN for zero denominators | Composites are cloud-free and on one scale (1.4) | Per-scene indices then median |
| D30 | 2026-09-19 | **Finding, not yet a decision:** with defaults `T_bui=0.15`, `T_ndvi_drop=0.10` the candidate mask covers 17 % of the AOI (West-1 23 %, Control-Marsh 43 %, Control-Builtup 12 %, outside 16 %). Investigation: (a) two large ponds show as big dBUI blobs — water/wet-marsh in 2020 that was dry/bright in 2023 (water-like px 287 → 1014) — a **seasonal water-level false positive**, ~27 % of candidates; (b) the rest is salt-and-pepper noise at ±1 px that opening/min-area (1.8) should remove; (c) Control-Builtup at 12 % suggests a small radiometric shift between the two periods (dBUI p50 = +0.04 everywhere). **Task 1.6 must therefore add a water exclusion (pixels water-like in either period), consider subtracting the AOI-wide median dBUI (relative change), and apply 3×3 opening — then re-measure before any threshold tuning** | Honesty rule: do not tune blindly | Raise thresholds until it "looks right" (rejected) |
| D31 | 2026-09-19 | Optical change rule (`optical_change_mask`, `OpticalChangeParams`) = techspec step 7 **plus three refinements, all on by default**: (1) exclude pixels water-like in either period (NIR < 0.09 and SWIR < 0.07); (2) centre dBUI and dNDVI on their AOI-wide medians (removes the +0.04 radiometric shift); (3) 3×3 binary opening. Thresholds unchanged at `T_bui 0.15`, `T_ndvi_drop 0.10`. Ablation on real data (candidate % West-1 / Marsh / Builtup / outside): naive 22.9/42.7/12.1/16.0 → +water 16.4/2.4/12.1/12.6 → +centering 12.9/1.7/9.4/9.4 → +opening **4.7/0.0/0.0/3.1** | Each step targets a diagnosed failure (D30), not blind tuning; controls now clean without touching thresholds | Otsu adaptive threshold (kept as option for 1.10) |
| D32 | 2026-09-19 | Observed after 1.6: West-1 retains ~5 compact blobs (0.9 ha total ≈ 4.7 % of 20 ha) plus a large candidate region **outside** the parcels to the east and a small one in the north — plausible real construction on the marsh margin, to be checked against Wayback in 1.10. Nothing flagged in either control parcel | Visual check of preview | — |
| D33 | 2026-09-19 | Radar change rule (`radar_change_mask`, `RadarChangeParams`): speckle = 3×3 NaN-aware median **on the dB composites** (composites are already 6-scene medians, so a light filter suffices); `dσ = VV_cur − VV_base` centred on the AOI median (raw shift only +0.12 dB here); `T_sar = 2.5 dB`; optical water mask reused as exclusion; 3×3 opening. VV only for the decision; VH computed and reported | Techspec step 8; ablation West-1/Marsh/Builtup/outside: naive 16.4/0.0/25.9/17.5 → +speckle 12.9/0.0/19.4/13.6 → +centre 12.4/0.0/17.6/12.7 → +opening **7.2/0.0/5.6/5.7** | Lee filter; VV∧VH |
| D34 | 2026-09-19 | **Honest finding:** radar alone is noisy here — 42 radar regions (median 15 px) scattered over the AOI including 5.6 % of the *built-up control*. Dense urban fabric at 10 m gives large random dB swings between two 6-scene medians (p5/p95 of centred dσ = −4.2/+4.1 dB). Radar-only regions therefore belong in `low` confidence, exactly as the techspec fusion table says; radar's value is in **confirming** optical regions. Pre-computed fusion on 14 optical regions: 7 have radar overlap ≥ 0.3 (→ `high`), 7 do not (→ `medium`); 3 of the 6 regions inside West-1 would be `high` (mean dVV +1.3 to +2.5 dB). The large 2.85 ha optical region outside the parcels has **negative** dVV (−2.2 dB) → medium, likely land clearing/bare soil rather than structures | Numbers from `scripts/preview_radar_change.py` and an ad-hoc region analysis | Raise T_sar (would lose confirmations); drop radar (loses the high/medium split) |
| D35 | 2026-09-19 | Vectorize (`app/pipeline/vectorize.py`): closing+opening 3×3 → `rasterio.features.shapes` (8-connectivity) in the UTM grid → drop < 400 m² (projected) → `simplify(5 m)` → clip with shapely to each parcel (one piece per parcel; pieces < 400 m² dropped; anything outside all parcels discarded) → reproject to EPSG:4326 as MultiPolygon → geodesic area via pyproj `Geod` (WGS84). Each region keeps its pixel mask so per-region means (dBUI, dNDVI, dσ) are computed from the *same pixels*. In Phase 4 the service layer will redo the clip in PostGIS (`ST_Intersection`) for persistence; shapely here keeps Phase 1 DB-free | Techspec steps 10–11, rules §4 (area never in degrees). Geodesic vs projected differ by 0.06 % at 13° N | Vectorize in EPSG:4326 (wrong for areas) |
| D36 | 2026-09-19 | Region-level results on the test area: **optical** 5 detections in West-1 totalling 9,406 m² (901–3,302 m² each, mean dBUI +0.25 to +0.40), **none** in either control. **Radar** 5 pieces in West-1 (14,169 m², dσ +4 to +7.4 dB) and **1 in Control-Builtup** (1,901 m², +3.5 dB) — confirms D34: radar-only regions are `low` confidence, never standalone detections | — | — |
| D37 | 2026-09-19 | Fusion (`app/pipeline/fusion.py`, `ALGORITHM_VERSION = "idx-fusion-1.0.0"`): per optical region `sar_overlap` = fraction of its pixels inside the cleaned radar mask dilated 1 px; **high** if ≥ 0.3, else **medium**; radar regions touching no optical region → **low**; radar regions touching one are absorbed (not double-counted). **Score** = 0.4·norm(mean dBUI, 0.15→0.60) + 0.3·norm(mean dσ_VV, 0→6 dB) + 0.2·sar_overlap + 0.1·compactness (4πA/P²), clipped to [0,1], NaN inputs contribute 0. Score only orders regions within a class; it never changes the class. All constants live in `FusionParams` for 1.10 tuning | Techspec §5.2 step 9 table; "document the exact formula" requirement | Learned weights (no labels yet); score-based class (would hide the sensor-agreement logic from reviewers) |
| D38 | 2026-09-19 | First classed result on the test area: West-1 → 3 high (901/3,302/1,201 m², overlap 1.00/0.45/0.75, score 0.49/0.44/0.43), 2 medium (dBUI +0.34/+0.38 but dσ negative), 2 low (radar-only, +4 to +5.3 dB, dBUI ≈ 0); Control-Builtup → 1 low; Control-Marsh → 0. Scores cluster at 0.2–0.5 because the normalisation ranges are deliberately wide — do not rescale before 1.10 provides labels | — | — |
| D39 | 2026-09-19 | Labelled set (`data/eval/labels.geojson`, copy in `docs/samples/`): the 8 v1 detections + 1 known miss, judged from the owner's Wayback screenshots (releases **2020-12-16** and **2023-06-13**, 1:2,200) read by Arena Agent and accepted by the owner. Labels: #1 high real, #2 high real (clear construction site), #3 high real, #4 medium unsure (bare-earth patch, no structure), #5 medium real (yard → paved lot), #6 low real (new house + walls; box larger than structures), #7 low real, #8 low (Control-Builtup) unsure, #9 missed: long metal-roofed shed N of #8 (approx. position). **Only 9 sites, not the 20–50 the plan asks for** — statistically weak; treat as a smoke test of precision, not a measured precision | Plan 1.10; PRD ≥ 80 % high real | Waiting for a bigger label set (owner time) |
| D40 | 2026-09-19 | Evaluation rules (`app/pipeline/evaluate.py`): match = IoU ≥ 0.3 **or** smaller geometry ≥ 50 % covered; tp = matches a `real` label, fp = matches `not_real` **or matches nothing**, `unsure` excluded from precision; recall = matched real / all real (incl. `missed`). With defaults: high 3/3, medium 1/0 (+1 unsure), low 2/0 (+1 unsure), recall 6/7 (the shed near #8 is unmatched — its polygon is approximate, so this is a soft miss) | Plan §5.3 | Pixel-level IoU (labels are sites, not pixel masks) |
| D41 | 2026-09-19 | Threshold sweep (48 settings, T_bui 0.10–0.25 × T_sar 2.0–3.5 × overlap 0.2–0.5): **defaults (0.15 / 2.5 / 0.3) are on the flat optimum** — 0.10 gives identical results, 0.20+ drops two highs to low (recall 57 %), T_sar 2.0 adds 2 unlabelled low detections (counted fp under D40), T_sar 3.5 loses one real low. Overlap 0.5 demotes one high to medium. **No threshold change made** — a 9-site set cannot justify tuning; `FusionParams`/`OpticalChangeParams`/`RadarChangeParams` stay as documented | Plan 1.10 | Tuning to the sweep (would overfit 9 labels) |
| D42 | 2026-09-19 | **Prototype slice before Phase 2** (owner asked for a working prototype within 2 h): `app/services/prototype.py` (file-backed `PrototypeStore`: parcels from `data/samples/parcels.geojson`, detections seeded from `data/previews/detections.geojson`, `run_scan()` executes optical → radar → fusion → clip on `data/composites` offline) + `app/api/prototype.py` mounted under `/api/v1` with the techspec §6 paths (`/parcels`, `/detections`, `/detections/{id}`, `/detections/{id}/status`, `/scans`). Frontend `ReviewPage` at `/`: MapLibre + OSM raster (desaturated per design tokens), parcels outlined, detections filled by confidence colour, list with filter, detail panel with metrics + Confirm / Field visit / Dismiss (reason required), disclaimer footer. **No auth, no DB, in-memory status** — all replaced in Phases 2–3/5–6; endpoints keep the same paths so the frontend does not change. 3 API tests (68 total) | Owner request; tracker rule "docs are memory" | Wait for Phase 2/3 (owner needed something visible now) |
| D43 | 2026-09-19 | **1.11 decision: GO.** Evidence: (a) control parcels produce 0 high/medium detections while the marsh dried→flooded; (b) 3/3 high judged real, 6 tp / 0 fp overall, recall 6/7 on the 9-site set; (c) threshold sweep flat around defaults; (d) end-to-end runtime ~2 s on saved composites, ~2 min including downloads. Caveats carried forward: only 9 labels; Wayback 2020-12 is 9 months after baseline; single houses < 400 m² not resolvable at 10 m (disclaimer text now served by the API). ML variant remains optional per techspec | Plan 1.11 | No-go (nothing in the evidence supports it) |
| D44 | 2026-09-19 | Basemap: OSM's public tile server returns **403 "Access blocked"** for apps served through proxy hosts (tile usage policy). Default basemap switched to **Esri World Imagery** (free for basemap display with attribution; satellite is what a reviewer needs anyway) with a **Carto dark** toggle; `BASEMAP_URL`/attribution in settings remain the override. Also review layout: side-by-side from 640 px, list gets 45 dvh on phones | Owner screenshot; techspec §4 basemap keys | Self-hosted tiles (not free at this stage) |
| D16 | 2026-09-19 | Primary imagery: Microsoft Planetary Computer STAC (no account needed since June 2024, incl. Sentinel-1 RTC). Fallback: CDSE STAC v1 `https://stac.dataspace.copernicus.eu/v1` (free account for downloads) | Audit in §6 | CDSE as primary (needs token from day one) |

## 4. Open Questions

| # | Question | Owner | Needed by | Status |
|---|----------|-------|-----------|--------|
| Q1 | Which test area (and its parcel source) for development and evaluation? Pick a place you can verify easily against a satellite basemap. Suggested options near Chennai/Tambaram: (a) Pallikaranai marsh reserve edge, (b) Adyar/Cooum riverbed stretch, (c) a government plot the owner knows. Export boundaries from OSM (overpass-turbo.eu → export GeoJSON) or trace at geojson.io | Shrestha | Task 1.1 | **resolved 2026-09-19: Pallikaranai marsh edge** (D17); files pending in `data/samples/` |
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
| 2026-09-19 | Owner's regular Wi-Fi (172.20.x.x, likely campus/CGNAT) blocks TCP 443 to Azure Blob Storage (`*.blob.core.windows.net`), where Planetary Computer pixels live. DNS OK, STAC API OK, no proxy; `Test-NetConnection` fails on Wi-Fi, succeeds on phone hotspot | 1.3+ | **Workaround:** run scans that need new scenes on the hotspot; cache makes repeats offline. Ask network admin to allow `*.blob.core.windows.net:443`. If it ever fails everywhere: bring forward CDSE / Earth Search fallback source. 1.4 adds `GDAL_HTTP_CONNECTTIMEOUT` + readable "cannot reach imagery storage" error |

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
| 2026-09-19 | 1.11 | `ReviewPage.tsx`: Esri imagery default + Carto dark toggle, responsive grid (D44) | Arena Agent |
| 2026-09-19 | 1.11 | `app/services/prototype.py`, `app/api/prototype.py`, `tests/test_prototype_api.py`; `frontend/src/api/prototype.ts`, `frontend/src/pages/ReviewPage.tsx`, routes (`/` → ReviewPage); `@types/geojson` dev dep | Arena Agent |
| 2026-09-19 | 1.10 | `app/pipeline/evaluate.py` (`LabelledSite`, `ClassMetrics`, `Evaluation`, `load_labels`, `matches`, `evaluate`); `tests/pipeline/test_evaluate.py` (4 tests, 65 total); `scripts/evaluate_detections.py` (defaults + sweep → `eval_sweep.csv`); `data/eval/labels.geojson` (+ `docs/samples/` copies) | Arena Agent |
| 2026-09-19 | 1.9 | `app/pipeline/fusion.py` (`FusionParams`, `FusedRegion`, `norm`, `compactness`, `overlap_fraction`, `score_region`, `fuse`); `tests/pipeline/test_fusion.py` (6 tests: norm/NaN, square compactness π/4, dilated overlap, full high/medium/low table incl. absorption, tunable threshold, score known values); `scripts/fuse_detections.py` → `detections.geojson` | Arena Agent |
| 2026-09-19 | 1.8 | `app/pipeline/vectorize.py` (`clean_mask`, `mask_to_regions`, `clip_to_parcels`, `geodesic_area_m2`, `to_feature`, `Region`, `ClippedRegion`); `tests/pipeline/test_vectorize.py` (5 tests: exact 3,600 m² square, 400 m² threshold, gap/speck cleaning, split across two parcels + outside dropped, geodesic 1 km² check); `scripts/vectorize_masks.py` | Arena Agent |
| 2026-09-19 | 1.7 | `speckle_filter`, `radar_change_mask`, `RadarChangeParams`, `RadarChange` in `radar.py`; `tests/pipeline/test_radar_change.py` (3 synthetic tests: block found, speck + roughened water excluded, uniform moisture shift centred out, NaN-aware filter); `scripts/preview_radar_change.py` (ablation, optical overlap, `radar_change.npz`, preview) | Arena Agent |
| 2026-09-19 | 1.6 | `water_mask`, `binary_opening`, `optical_change_mask`, `OpticalChangeParams`, `OpticalChange` in `optical.py` (scipy.ndimage added — already in `[geo]` extras); `tests/pipeline/test_optical_change.py` (5 synthetic tests incl. built block found, drying marsh excluded, speck removed, global shift centred); `scripts/preview_optical_change.py` (ablation table + preview + `optical_change.npz`) | Arena Agent |
| 2026-09-19 | 1.5 | `ndvi`, `ndbi`, `bui`, `compute_indices`, `Indices` in `app/pipeline/optical.py`; `tests/pipeline/test_indices.py`; `scripts/preview_indices.py` (offline: NDVI/BUI/dBUI previews + `data/composites/indices.npz`) | Arena Agent |
| 2026-09-19 | 1.4 | `app/pipeline/optical.py` (`to_reflectance` with PB≥04.00 offset, `scl_valid_mask`, `median_composite`, `Composite`), `app/pipeline/radar.py` (`to_db`, `to_linear`, `median_composite_db` — median in linear power), `app/pipeline/composite.py` (orchestration), `scripts/build_composites.py` (npz + previews), fast-fail GDAL env; 13 new synthetic tests (37 total) | Arena Agent |
| 2026-09-19 | 1.3 | `app/pipeline/grid.py` (`TargetGrid`, `make_grid`), `app/pipeline/cache.py` (`RasterCache`), `PlanetaryComputerSource.read_grid/read_bands` + `_read_one`, `scripts/read_sample.py` (reads best S2 + mid-window S1 per period, prints band stats, writes false-colour/VV previews); 5 new tests on synthetic GeoTIFFs | Arena Agent |
| 2026-09-19 | 1.2 | `app/pipeline/sources/base.py` (`SceneRef`, `ImagerySource` Protocol, `ImageryError`), `app/pipeline/sources/planetary_computer.py` (`PlanetaryComputerSource`, anonymous signing, dedupe), `app/pipeline/aoi.py` (union + 100 m buffer in UTM, 100 km² guard), `scripts/search_scenes.py`; 12 new tests with mocked STAC (no network) | Arena Agent |
| 2026-09-19 | 1.1 | Owner traced 3 parcels at geojson.io from Esri Wayback comparison; validated with shapely/pyproj; `data/samples/{parcels.geojson,windows.json,README.md}` (gitignored — owner keeps copy in OneDrive workspace) | Shrestha + Arena Agent |

## 10. Session Handoff Notes

> Write 3–5 lines at the end of each working session: what was done, what is half-done, what to do next, gotchas. The next assistant reads this first.

- **Done (2026-09-19, Arena Agent):** Phase 0 (except manual 0.3/0.7), Phase 1 complete (1.1–1.11, GO). Prototype slice runs: backend `uvicorn app.main:app` (with `DATA_DIR=../data`) + frontend `npm run dev`; open `/`, click **Run scan**, click detections. pytest **68 passed**, tsc/eslint clean, vitest 2 passed.
- **Half-done:** 0.3 PostGIS + 0.7 CI still need the owner's machine / first push. Owner should run `python scripts\search_scenes.py ..\data\samples\parcels.geojson ..\data\samples\windows.json` on Windows to confirm the same counts.
- **Next:** 2.1 — SQLAlchemy models per `05-schema.md` (users, parcels, scans, scan_scenes, detections, detection_status_history, schedules, alert_settings) + 2.2 Alembic migrations; then replace `PrototypeStore` reads with repositories (keep `run_scan` pipeline calls). Owner actions still open: push to GitHub; PostGIS check 0.3; CI 0.7; more labels for 1.10. (Old 1.11 plan: go/no-go: write the decision in tracker §3 (recommendation: **GO** for Phase 2 with the index+fusion baseline; ML variant stays optional per techspec) with the evidence list (control parcels 0 high/medium, 3/3 high real, sweep plateau) and the caveats (9 labels, small-house recall, Wayback date offset); update README status; then Phase 2.1 models. Owner actions still open: push to GitHub, PostGIS check 0.3, CI 0.7, optionally label 10–20 more sites to firm up 1.10. (Old 1.10 plan: labelled evaluation. (a) Owner labels each of the 8 detections in `docs/samples/detections.geojson` as real / not real / unsure using Wayback (nearest releases to early 2020 and early 2023; note the exact dates) and reports obvious missed new buildings in West-1. (b) Write `data/samples/labels.geojson` (owner) + `scripts/evaluate.py`: precision per class, recall vs. labelled misses, IoU-based matching (≥ 0.3), and a small threshold sweep (T_bui 0.10–0.25, T_sar 2.0–3.5, overlap 0.2–0.5) printing a table. (c) Record metrics in tracker; PRD target ≥ 80 % of `high` judged real. Do NOT tune before labels exist. (Old 1.9 plan: `fusion.py`: for each optical region compute `sar_overlap` = fraction of its pixels inside the (dilated 1 px) radar mask; class = high if ≥ 0.3 else medium; radar-only regions = low; score = 0.4·norm(dBUI, 0.15→0.6) + 0.3·norm(dσ, 0→6 dB) + 0.2·sar_overlap + 0.1·compactness (4πA/P²), clipped to [0,1]; tests with synthetic regions; `scripts/fuse.py` → `detections.geojson` with confidence + score. Also: `algorithm_version = 'idx-fusion-1.0.0'`. (Old 1.8 plan: `vectorize.py`: `mask_to_polygons(mask, grid)` via `rasterio.features.shapes`, closing+opening, min area 400 m² (in UTM), light `simplify(5 m)`, clip to each parcel with shapely (per-parcel `overlap_area_m2`), geodesic area via pyproj `Geod`, reproject to EPSG:4326, write `data/previews/detections_optical.geojson` + radar equivalent; tests on synthetic masks (one square → one polygon with exact area; sub-min-area speck dropped; polygon straddling two parcels → two clipped pieces). (Old 1.7 plan: `radar.py`: speckle filter (3×3 median on dB composites), `d_sigma_vv = VV_cur_db − VV_base_db` (and VH), `radar_change_mask(d_sigma > T_sar=2.5 dB)` with the same water exclusion and opening; preview; per-parcel table like 1.6. Note water in radar is dark and wind-roughened water can jump several dB → water exclusion matters here too. (Old 1.6 plan: `optical_change_mask(...)` in `optical.py` + water exclusion + optional median-centering + 3×3 opening; preview; measure per-parcel fractions again (target: Control-Builtup and Control-Marsh near 0 %, West-1 a few compact blobs). See D30. (Old: indices in `app/pipeline/optical.py`: `ndvi(nir, red)`, `ndbi(swir, nir)`, `bui = ndbi − ndvi`, safe division (NaN where denominator ≈ 0), synthetic tests with known answers (pure veg → NDVI≈+0.8, BUI negative; bare/built → NDVI≈0.1, BUI ≈ 0 to +0.3). Then compute them on the saved composites and preview BUI per period. (Old 1.4 notes: `scl_valid_mask` (drop SCL 0,1,3,8,9,10,11 per techspec step 4 — note SCL 1 saturated, 3 shadow, 8/9 cloud, 10 cirrus, 11 snow), apply the PB ≥ 04.00 −1000 offset (D24), per-period nanmedian composite over all scenes; S1 median in linear power then dB. Preview composites. Then 1.3's old plan: `read_bands` in `PlanetaryComputerSource` via rasterio windowed reads of signed COG hrefs (S2 B04/B08/B11/SCL → 10 m UTM grid, B11 20→10 m nearest/bilinear, SCL nearest; S1 vv/vh linear power), file cache under `data/cache/` keyed by scene id + bbox + band. Write a `LocalFolderSource` stub only if needed for tests.
- **Gotchas:** `.venv` and `data/` are not persisted in the sandbox snapshot — recreate venv each session (`python3 -m venv .venv && pip install -e ".[dev,geo]"`); `data/samples/*` is checked into the sandbox working tree only via the owner's copy — if missing, re-paste. Script inserts `backend/` on `sys.path` so it runs without `pip install -e .`. Repo on owner PC: `%USERPROFILE%\OneDrive\Desktop\workspace-01a0b883-c2f0-73bd-94c6-a1c108ea92da\geoguard-eo`.
