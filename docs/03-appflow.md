# GeoGuard-EO — App Flow

> Describes how users move through the product and how the system behaves behind each step. Visual styling lives in `04-design.md` (pending).

---

## 1. Roles

| Role | Can do |
|------|--------|
| `admin` | Everything: manage parcels, create/re-run scans, review, reports, export, manage alert settings |
| `officer` | View parcels/scans/detections, change detection status, generate reports |

Unauthenticated users can only see the login page.

## 2. Screen Map

```
/login
/                     Dashboard
/parcels              Parcel list + map
/parcels/new          Add parcels: upload GeoJSON or draw on the map (admin)
/parcels/:id          Parcel detail (+ detection history)
/scans                Scan list
/scans/new            Create scan (admin)
/scans/:id            Scan detail + progress + results
/detections           Detection list (map + table)
/detections/:id       Detection detail (review screen)
/settings             Alerts, default thresholds (admin)
/schedules            Recurring scans (admin)
/users                User management (admin)
```

Global layout: top bar (logo, user menu, role badge), left navigation (Dashboard, Parcels, Scans, Detections, Settings), main content area.

## 3. Primary User Flows

### Flow A — Sign in
1. User opens app → redirected to `/login` if no valid token.
2. Enters email + password → `POST /auth/login`.
3. Success: token stored (memory + httpOnly cookie or secure storage per techspec decision), redirect to `/`.
4. Failure: inline error, no detail about which field was wrong. After repeated failures show a cooldown message.
5. Token expiry: on `401`, clear session and redirect to `/login` with a “session expired” notice.

### Flow B — Add protected parcels (admin)
1. `/parcels` → **Add parcels**, which offers two tabs: **Upload** and **Draw**.
2. **Upload tab:** select a `.geojson` file (size limit shown).
3. Client-side quick check (extension, size). Server validates geometry.
4. Preview on map with a table of features; admin sets **name** and **category** per feature (or maps from GeoJSON properties).
5. Confirm → parcels saved. Invalid features are listed with reasons and skipped; user can fix and re-upload.
6. Empty state before the first parcel: friendly prompt with both options and a link to a sample GeoJSON.
7. **Draw tab:** the admin pans/zooms the basemap, clicks to place polygon vertices, double-clicks to finish, and can drag vertices to edit or delete the shape. Live area (m²) is shown while drawing. Self-intersecting shapes are rejected with an inline message.
8. After drawing (or after upload preview), the admin enters **name** and **category** and saves; the client sends the same GeoJSON payload to `POST /parcels`, with `source = drawn` or `upload`.
9. Existing parcels can be edited later (name, category, notes; geometry redraw for drawn parcels).

### Flow C — Run a scan (admin)
1. `/scans/new`.
2. Select parcels (multi-select, or “all”). Map highlights selection; shows total area.
3. Choose **baseline period** and **current period** (date range pickers). App suggests same-season windows and warns if seasons differ.
4. Optional **Advanced**: cloud cover max, min detection area, optical/radar thresholds (defaults prefilled).
5. Submit → `POST /scans` → redirect to `/scans/:id`.
6. Scan page polls status (every 3–5 s): `queued → running (with step + %) → succeeded | failed`.
7. On success: summary (scenes used, detections by confidence) with **View detections** button.
8. On failure: readable reason (e.g., “No cloud-free optical scenes in baseline period”) with **Adjust and re-run**.

### Flow D — Review detections (officer)
1. Dashboard shows latest scan and count of `new` detections; click through to `/detections?status=new`.
2. List/map split view: table on one side, map on the other; hovering a row highlights the polygon. Filters: scan, parcel, confidence, status, date. Default sort: confidence desc, area desc.
3. Open a detection → `/detections/:id`:
   - Map centered on the polygon with the parcel boundary.
   - **Before/After slider** (baseline vs current RGB).
   - Metrics: area (m²), confidence class + score, optical change magnitude, radar change magnitude, sensor agreement badge, parcel name/category, coordinates, scenes/dates used.
   - Status history and notes.
4. Officer chooses an action:
   - **Confirm** → optional note → status `confirmed`.
   - **Dismiss (false positive)** → reason required (dropdown + free text) → `dismissed`.
   - **Needs field visit** → note → `field_visit`.
5. Each action writes an audit row and updates the list without a full reload.
6. Keyboard shortcuts for review speed (next/previous detection, confirm/dismiss) are a v1.1 nicety.

### Flow E — Generate report and alert
1. On a `confirmed` detection: **Generate report**.
2. `POST /detections/:id/report` → PDF built server-side → download link appears (also stored in report history).
3. If the detection is `high` confidence and alerts are enabled, confirming triggers an alert through the configured provider (console by default; optionally Telegram or email) to the configured recipients: short message with detection ID, parcel name, coordinates, and a link. Delivery result (sent/failed/console-logged) is stored and shown on the detection page.
4. Failure to send an alert never blocks the status change; it shows a non-blocking warning and can be retried.

### Flow F — Re-run / compare over time
1. From a scan page: **Re-run with same parameters** or **Clone and edit**.
2. New scan is independent; detections already `confirmed`/`dismissed` at the same location are matched by spatial overlap and shown with a “previously reviewed” badge to avoid re-reviewing the same site (v1.1, but schema supports it).

### Flow G — First run and sample data
1. First start: the seed script creates the first admin from environment variables and, optionally, sample parcels plus a completed sample scan so screens are not empty.
2. The first admin must change the initial password at first login (`must_change_password`).
3. The dashboard shows an onboarding checklist: add a parcel → run a scan → review a detection → set up alerts.

### Flow H — Recurring scans (admin)
1. `/schedules` → **New schedule**: name, parcels, frequency (weekly/monthly or custom cron), current-window length in days, and baseline rule (default: same season, previous year), plus optional advanced thresholds.
2. Save → schedule is active; the page shows the next run time and the last run result.
3. When due, the scheduler creates a normal scan (Flow C, steps 6–8) tagged with the schedule. New `high` confidence detections appear on the dashboard as “new since your last visit”.
4. Admin can pause, edit, run now, or delete a schedule. Deleting keeps past scans and detections.
5. If the app was off at the due time, the run is skipped and the next due time is recomputed; the schedule page notes “missed run”.

### Flow I — User management (admin)
1. `/users` lists users with role and active state.
2. **Add user**: email, name, role, temporary password (user must change it at first login).
3. Admin can change role, deactivate/reactivate, or reset a password. An admin cannot deactivate or demote the last active admin.
4. Every user can change their own password from the user menu.

## 4. System Flow: Scan Pipeline

```
Client            API                 DB               Worker                Imagery source
  │  POST /scans   │                   │                  │                        │
  │───────────────▶│  validate+insert  │                  │                        │
  │                │──────────────────▶│ scan(queued)     │                        │
  │  201 {id}      │                   │                  │                        │
  │◀───────────────│                   │◀── poll ─────────│                        │
  │                │                   │ scan(running)    │                        │
  │                │                   │                  │── search scenes ──────▶│
  │                │                   │                  │◀─ scene refs ──────────│
  │                │                   │                  │── windowed read ──────▶│
  │                │                   │                  │◀─ bands ───────────────│
  │                │                   │                  │ mask→composite→indices │
  │                │                   │                  │ change→fusion→vectorize│
  │                │                   │◀── save results ─│                        │
  │  GET /scans/id │                   │ scan(succeeded)  │                        │
  │───────────────▶│  status+summary   │                  │                        │
```

Progress steps reported to the UI: `searching_scenes` → `downloading` → `optical_change` → `radar_change` → `fusion` → `saving`.

## 5. State Machines

**Scan status**
```
queued → running → succeeded
                └→ failed
queued/running → cancelled (admin action, v1.1)
```

**Detection status**
```
new → confirmed
new → dismissed
new → field_visit → confirmed | dismissed
confirmed → dismissed (with reason; audit logged)   # correction allowed
dismissed → new (admin reopen; audit logged)
```

**Alert delivery**
```
pending → sent | failed → (retry) → sent | failed
```

## 6. Edge Cases and Error States

| Situation | Behavior |
|-----------|----------|
| No detections found | Success state with “No new change found” and the parameters used; suggest widening periods. |
| Parcel upload has invalid geometry | Per-feature error list; valid features can still be imported. |
| No usable optical scenes (clouds) | Scan fails with reason; suggest a different window or radar-only mode (v1.1). |
| Imagery service unreachable | Scan fails with `provider_unavailable`; retry button. |
| Two admins start scans simultaneously | Second stays `queued` until the first finishes. |
| A scheduled scan fires while another is running | It is queued behind it; at most one queued scan per schedule (duplicates are skipped). |
| Detection deleted parcel | Parcel delete is blocked if detections exist unless admin confirms cascade. |
| Token expired mid-action | Redirect to login, preserve return URL. |
| Slow network | Skeleton loaders; polling backs off gracefully. |
| Large polygons on map | Simplified geometry for lists, full geometry only in detail. |

## 7. Empty, Loading, and Error UI Rules

- Every list has an **empty state** with the next action (e.g., “Upload your first parcel”).
- Every async view has a **loading state** (skeleton) and an **error state** with retry.
- Destructive actions require confirmation and explain consequences.

## 8. Notifications and Feedback

- Toasts for success/failure of quick actions (status change, upload).
- Persistent banner on the scan page for long-running jobs.
- Alerts (console, or optional Telegram/email) are optional and only sent for `high` confidence confirmed detections by default; the minimum confidence is configurable in settings.

## 9. Analytics (optional, privacy-safe)

No third-party trackers. Optional local counters (scans run, detections reviewed) shown on the dashboard only.
