# GeoGuard-EO — Product Requirements Document (PRD)

> Status: v1.1 · Owner: Shrestha Agarwal · Goal: a **good, working product** built with **100% free resources and services**
> Companion docs: `02-techspec.md`, `03-appflow.md`, `04-design.md` (pending), `05-schema.md`, `06-implementation-plan.md`, `07-tracker.md`, `08-rules.md`

---

## 1. Overview

**GeoGuard-EO** is a web application that watches user-defined government or protected land parcels using free satellite imagery (Sentinel-1 radar and Sentinel-2 optical), detects new construction or land-cover change inside those parcels, and gives a reviewer the evidence needed to act on it: map location, before/after imagery, estimated area, and a confidence score.

It replaces slow, manual field inspection with a repeatable, automated, auditable pipeline. Satellite detection is a **screening tool**: it flags places worth a human look. It does not prove a violation.

## 2. Problem Statement

Unauthorized construction and encroachment on government land, riverbeds, wetlands, and reserved plots is usually found late, after a complaint or after the structure is built. Manual inspection covers only a small fraction of land, is slow, and leaves no consistent evidence trail.

## 3. Product Principles

1. **Works for real users, not just a demo.** Anyone can add their own parcels, run and schedule scans, review results, and export evidence.
2. **100% free.** Free data, free software, free services. No paid APIs, no subscriptions (see §9).
3. **Honest about accuracy.** Show confidence, limitations, and always keep a human in the loop.
4. **Reproducible and auditable.** Every result stores its parameters, scenes, and review history.

## 4. Goals

| ID | Goal |
|----|------|
| G1 | Detect new built-up change inside user-defined protected parcels from Sentinel imagery. |
| G2 | Reduce false alarms by fusing optical (S2) and radar (S1) evidence at the decision level. |
| G3 | Let a reviewer work fast: see detections on a map, inspect before/after imagery, confirm or dismiss. |
| G4 | Let admins add parcels by uploading files or drawing on the map, and run scans on demand or on a schedule. |
| G5 | Produce shareable evidence (PDF report, GeoJSON/CSV export) and free alerts (console; optional Telegram/email). |
| G6 | Be reliable, secure, well-documented, and easy to install and back up on a normal Windows laptop. |

## 5. Non-Goals (v1)

- Not a legal or enforcement system; a detection is not proof of a violation.
- No real-time or sub-daily monitoring (Sentinel revisit is days).
- No reliable detection of small structures below the resolution limit (see §10).
- No multi-organization tenancy, billing, or public self-sign-up.
- No paid SMS, paid maps, or paid hosting.
- No mobile app; responsive web only.
- No custom-trained deep-learning model in v1 (planned as v2).

## 6. Users and Personas

**P1 — Field/Land Officer (primary).** Reviews flagged sites, confirms or dismisses, downloads evidence. Not a GIS expert. Wants a clear map and simple actions.

**P2 — Admin/Analyst.** Adds parcels (upload or draw), configures scans and schedules, manages users and alert settings. Comfortable with maps; may know GeoJSON.

## 7. User Stories

1. As an Admin, I upload a GeoJSON of protected parcels, or draw a parcel directly on the map, and label it with a category (e.g., riverbed, wetland, government plot).
2. As an Admin, I start a scan by choosing parcels, a baseline period, and a current period.
3. As an Admin, I schedule a scan to repeat weekly or monthly so new construction is found without me remembering.
4. As an Officer, I see a dashboard of recent scans and new detections since my last visit.
5. As an Officer, I open a detection and see it on a map with a before/after comparison, area, confidence, and which sensors agreed.
6. As an Officer, I mark a detection **Confirmed**, **Dismissed (false positive)**, or **Needs field visit**, with a note.
7. As an Officer, I generate a PDF evidence report and export detections as GeoJSON/CSV.
8. As an Admin, I configure alerts (console by default; optionally Telegram or email) for confirmed high-confidence detections.
9. As an Admin, I create and manage users and roles.
10. As an Admin, I can re-run a scan with the same parameters and get reproducible results.

## 8. Functional Requirements

### 8.1 Parcels
- **FR-1** Create parcels by **uploading GeoJSON** (Polygon/MultiPolygon, EPSG:4326) or by **drawing on the map**; validate geometry and reject invalid or self-intersecting shapes with a clear message.
- **FR-2** Drawing supports adding vertices, dragging to edit, deleting, and shows live area.
- **FR-3** List, view, edit metadata, and delete parcels. Each has name, category, optional notes, and source (`upload` or `drawn`).
- **FR-4** Display parcels on a map. Deleting a parcel with scans or detections requires explicit confirmation.

### 8.2 Scans and Scheduling
- **FR-5** Create a scan: parcels, baseline range, current range, cloud-cover limit, thresholds (defaults provided).
- **FR-6** Scans run asynchronously with status `queued`, `running`, `succeeded`, `failed`, and progress messages and readable errors.
- **FR-7** Store parameters, scene IDs, and algorithm version with each scan.
- **FR-8** Imagery is found and read automatically from the configured free public source; the user never handles raw files.
- **FR-9** **Recurring scans:** create, pause, edit, run now, and delete schedules (weekly/monthly or custom cron). A schedule creates ordinary scans.

### 8.3 Detection
- **FR-10** Optical change from Sentinel-2 NDVI/NDBI-based indices between baseline and current periods.
- **FR-11** Radar backscatter change from Sentinel-1 as an independent signal.
- **FR-12** Decision-level fusion into a confidence class (`high`, `medium`, `low`) and a numeric score.
- **FR-13** Vectorize change into polygons, drop those below a minimum area, clip to parcels.
- **FR-14** Compute area in m² with geodesic or projected math, never in degrees.

### 8.4 Review
- **FR-15** Detection list with filters (scan, parcel, confidence, status, date) and sorting; map/list split view.
- **FR-16** Detection detail: map, before/after slider, metrics, sensor agreement, status history.
- **FR-17** Status workflow: `new` → `confirmed` | `dismissed` | `field_visit`, each with user, time, and note stored (audit trail). Dismissals require a reason.

### 8.5 Reporting, Export, Alerts
- **FR-18** PDF report per detection (location, coordinates, dates, before/after, area, confidence, parameters, disclaimer).
- **FR-19** Export the filtered detection list as GeoJSON or CSV.
- **FR-20** Alerts through a pluggable provider: `console` (default), optional `telegram` and `email`. Fires on confirmation of a detection at or above a configurable minimum confidence (default `high`). Failures never block the review action and can be retried.

### 8.6 Users and Auth
- **FR-21** Email + password login, JWT session, roles `admin` and `officer`.
- **FR-22** Admin user management: create, change role, deactivate, reset password; the last active admin cannot be removed. Users can change their own password.
- **FR-23** Role checks enforced server-side on every protected endpoint; login throttling after repeated failures.

## 9. Free-Resources Requirement

Everything the product depends on must be free for this project's usage:

- **Data:** Sentinel-1 and Sentinel-2 from free public catalogs (free account/token allowed).
- **Software:** open-source only (PostgreSQL/PostGIS, FastAPI, React, MapLibre, etc.).
- **Services:** no paid APIs. Alerts use console output, or free Telegram/email.
- **Maps:** free basemap tiles used within their usage policies, with attribution and a configurable tile URL.
- **Hosting/compute:** runs on the user's own machine.

Any new external service must be checked against its current terms and logged in the tracker's Free-Services Audit before use. If a free tier changes, the abstraction layers (imagery source, basemap URL, alert provider) let it be swapped without redesign.

## 10. Constraints and Known Limitations (state these in the product and README)

- **Resolution:** Sentinel-2 is 10 m per pixel (20 m for the SWIR band). Structures smaller than roughly 200–400 m² are unreliable; small huts and sheds will often be missed. Position accuracy is about 10–20 m.
- **False positives:** bare soil, harvested fields, seasonal water changes, construction staging, cloud shadow. Mitigations: same-season comparisons, cloud masking, minimum area, radar fusion, mandatory human review.
- **Cloud cover:** optical scenes can be unusable in monsoon months; radar is unaffected by cloud and helps fill gaps.
- **Data availability:** depends on the free public catalog being reachable; revisit dates vary.
- **Compute:** raster processing runs on the user's laptop; large areas are limited by an AOI size cap.
- **No ground truth included:** accuracy figures come from a hand-labeled evaluation set for the chosen test area.

## 11. Non-Functional Requirements

| Area | Requirement |
|------|-------------|
| Performance | A scan over ≤ 10 km² of parcels completes in about 10 minutes on a normal laptop with internet. UI pages load in under 2 s on local data. |
| Reliability | A failed scan never corrupts data; it ends `failed` with a readable reason. Re-running is safe. Worker restarts recover stuck scans. |
| Reproducibility | Same inputs and version give the same outputs. |
| Security | Hashed passwords, secrets in `.env`, validated inputs, parameterized SQL, role checks, login throttling, protected file routes. |
| Usability | Clear empty/loading/error states; keyboard-usable; responsive at ≥ 360 px. |
| Maintainability | Typed Python and TypeScript, linted, unit-tested algorithms, OpenAPI docs. |
| Operability | Documented setup and start scripts for Windows; backup and restore procedure for the database and data folder. |
| Portability | Native PostgreSQL/PostGIS on Windows; Docker optional, never required. |

## 12. Success Metrics

**Product quality (measured on a hand-labeled set in the chosen test area):**
- Precision ≥ 0.6 and recall ≥ 0.5 for structures ≥ 400 m² (targets; report actual results honestly).
- ≥ 80% of `high` confidence detections judged real on review.

**Working-product acceptance:**
- A new user completes the loop **add parcel → scan → review → report** in under 15 minutes, without help.
- A scheduled scan runs unattended and surfaces new detections.
- Setup from a clean Windows machine works following the README only.
- Backup and restore verified once.

## 13. Scope and Phasing

| Phase | Scope |
|-------|-------|
| **v1** | Parcels (upload + draw), index-based S2 change + S1 backscatter change + decision fusion, scan on demand and on schedule, review workflow, PDF report, GeoJSON/CSV export, console alerts (optional Telegram/email), auth, user management, first-run sample data, setup/backup docs. |
| **v1.1** | Match repeated detections across scans (“previously reviewed”), radar-only mode for cloudy periods, review keyboard shortcuts, statistics dashboard. |
| **v2** | Learned model for built-up segmentation trained on labeled tiles, evaluated against the index baseline. |
| **Later** | Multi-organization support, more alert channels, field-verification mobile flow. |

## 14. Assumptions

- Free public Sentinel-1/2 data remains accessible (terms verified at build time).
- Parcel boundaries come from the user: uploaded, drawn, or exported from OpenStreetMap or a hand-traced file.
- One test area is chosen for development and evaluation (open decision Q1).
- Development machine: Windows laptop with native PostgreSQL 15 + PostGIS.

## 15. Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Too many false positives | High | Same-season baselines, min area, fusion, mandatory review, honest metrics. |
| Free data/tile service limits or terms change | Medium | Provider abstractions; caching; Free-Services Audit; fallback catalog. |
| Scope growth (ML too early, extra channels) | High | ML is v2; MVP loop must work end to end first. |
| Heavy raster processing on a laptop | Medium | Windowed reads, caching, AOI size cap, one scan at a time. |
| Environment setup pain on Windows | Medium | Documented native path; problem packages get explicit fallbacks (see rules §12). |
| Scheduler only runs while the app is on | Medium | Document it; recompute next run on startup; show “missed run”. |

## 16. Open Questions

1. **Q1** Which test area will be used for development and evaluation, and which source for its parcel boundaries (OpenStreetMap export or hand-traced)? Needed before task 1.1.
2. **Q5** The design reference prompt for `04-design.md`. Needed before final UI styling.
