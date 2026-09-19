(Copy of docs/08-rules.md — keep docs/08-rules.md as the single source of truth.)
# GeoGuard-EO — Rules for AI Assistants and Contributors

> Tool-agnostic rules. If your tool expects a specific filename, copy or link this file to it (e.g., `CLAUDE.md`, `AGENTS.md`, `.cursorrules`, `GEMINI.md`) at the repo root. Keep **one** source of truth: this file.

---

## 1. Read Order (every session, before writing code)

1. `docs/07-tracker.md` — current phase, current task, blockers, handoff notes.
2. `docs/06-implementation-plan.md` — the task you are about to do and its “done when”.
3. `docs/01-PRD.md` — what and why.
4. `docs/02-techspec.md` — how (architecture, algorithm, API).
5. `docs/05-schema.md` — data model.
6. `docs/03-appflow.md` — behavior of screens and flows.
7. `docs/04-design.md` — visual system (only when it exists; needed for UI styling).

If two documents conflict, stop and ask; do not guess. Precedence: schema and techspec decide backend behavior; appflow decides UI behavior; PRD decides scope.

## 2. Working Method

- Work on **one task ID at a time** from the implementation plan. Do not start the next task without being asked.
- Before coding: restate the task in 2–3 lines, list the files you will create or change, and note any assumption. If the task is ambiguous or affects the schema or API contract, ask first.
- Make the **smallest change** that satisfies “done when”. No drive-by refactors, no unrequested features.
- After coding: run linters and tests, then update `docs/07-tracker.md` (status, change log, decisions, handoff notes) in the same change.
- If you discover the plan is wrong or incomplete, propose the fix and record it in the Decision Log; do not silently deviate.
- Never claim something works without having run it. State exactly what you ran and what happened. If you could not run it, say so.

## 3. Scope Guardrails

- **In scope for v1:** see PRD §11. **Out of scope:** multi-tenant, payments, mobile app, real-time monitoring, custom-trained ML (v2).
- **100% free resources only.** Never introduce a paid API, subscription, or metered service, and never write code that requires one. If a free option looks unreliable or its terms are unclear, stop and ask (see techspec §0).
- Do not add new dependencies or external services without stating why, confirming they are free, and recording them in the tracker. Prefer the stack in the techspec.
- Do not change public API shapes, DB schema, or enum values without updating `02-techspec.md` / `05-schema.md` and creating an Alembic migration.
- Satellite detection is a **screening aid**. Never write UI copy, reports, or code comments that present a detection as proof of a violation. Reports must include the disclaimer.

## 4. Backend Conventions (Python)

- Python 3.11+, full type hints; `mypy` clean on `app/`.
- Format/lint with `ruff` (line length 100). No unused imports or commented-out code.
- Layering: `api` (routers) → `services` → `repositories` → DB. Routers contain no business logic and no SQL. Pipeline code in `app/pipeline/` is **pure** where possible (arrays in, arrays out) and never imports FastAPI.
- Config only through the typed `Settings` object. No `os.getenv` in modules, no hard-coded paths or secrets.
- Database: SQLAlchemy 2.x style, parameterized queries only, migrations via Alembic only. Never mutate tables manually. Geometries are EPSG:4326 in storage; compute area with `geography` or a projected CRS.
- Errors: raise domain exceptions in services; translate to the standard error format `{ "error": { "code", "message", "details" } }` in one place.
- Logging: use the logger, never `print`. Include `scan_id` / `detection_id` context. Do not log secrets, tokens, or passwords.
- Raster work: windowed reads only, never load full scenes. Always confirm CRS, resolution, and grid alignment before arithmetic. Document units (dB vs linear power) in variable names (`vv_db`, `vv_lin`).
- Async: keep CPU-bound raster work out of the event loop (run in the worker process).
- Idempotency: a re-run with the same parameters must be safe and must not corrupt earlier results.

## 5. Frontend Conventions (TypeScript/React)

- TypeScript `strict` on. No `any` without a comment explaining why.
- Function components and hooks only. Server state through TanStack Query; local UI state via React state. No global state library unless recorded as a decision.
- API access only through the typed client in `src/api/`; no `fetch` calls scattered in components.
- Every data view implements **loading, empty, and error** states (see appflow §7).
- Accessibility: semantic HTML, labels on inputs, keyboard operability, sufficient contrast, alt text for imagery.
- Styling: follow `docs/04-design.md` when present. Until then, use Tailwind utilities consistently and isolate styles in reusable components so a later restyle is cheap. Do not invent a design language on your own.
- Format with Prettier; lint with ESLint; `tsc --noEmit` must pass.

## 6. Testing Rules

- New logic ships with tests in the same change. Bug fixes ship with a regression test.
- Algorithm functions (indices, thresholds, fusion, vectorize, area) are tested with **small synthetic arrays** with known answers.
- Tests must not need internet access. Use `LocalFolderSource` fixtures for pipeline tests.
- Integration tests use the separate `geoguard_test` database and clean up after themselves.
- Do not weaken or delete a failing test to make it pass; fix the cause or ask.

## 7. Security Rules

- Never commit `.env`, keys, tokens, or real credentials. Only `.env.example` with placeholders.
- Hash passwords with argon2/bcrypt; never store or log plaintext.
- Enforce roles server-side on every protected route; never rely on the UI to hide actions.
- Validate and bound all inputs: file size, geometry validity, vertex counts, string lengths, date ranges, AOI size.
- Build file paths from IDs you generate, never from raw user input; serve files only through authorized routes.
- Treat all data from the imagery provider and uploads as untrusted.

## 8. Git Rules

- Branch per task: `feat/<task-id>-<short-name>` (e.g., `feat/1.5-indices`), `fix/...`, `docs/...`.
- Conventional commits: `feat(pipeline): add NDBI/BUI indices (1.5)`. Reference the task ID.
- Small, reviewable commits. Do not mix formatting-only changes with logic changes.
- Never force-push shared branches. Never commit large binaries or raster data; `data/` is gitignored.
- Tag `v1.0.0` only after the Release Readiness Checklist in the tracker is complete.

## 9. Definition of Done (per task)

- [ ] Meets the “done when” in the implementation plan
- [ ] Linters and type checks pass
- [ ] Tests written and passing (state the command and result)
- [ ] Docs updated if behavior, API, schema, or config changed
- [ ] `07-tracker.md` updated (status, change log, decisions, handoff notes)
- [ ] No secrets, debug prints, or dead code

## 10. When to Stop and Ask

Stop and ask the human before proceeding if:
- Requirements conflict or are missing (e.g., an open question in the tracker blocks the task).
- You would need to change the schema, API contract, or stack.
- You are about to delete data or files, rewrite history, or install system-level software.
- Results look wrong (e.g., every pixel flagged, zero detections, implausible areas). Investigate and report; do not tune numbers blindly until it “looks right”.
- Anything involves real credentials, real personal data, or any service that is not clearly free.

## 11. Communication Style

- Be concise and concrete. Lead with what changed and how to verify it.
- Show exact commands to run (Windows PowerShell for this project) and expected output.
- Report limitations and uncertainty honestly, especially about detection accuracy. Do not overstate what 10 m imagery can detect.
- End each session by writing handoff notes in the tracker: done, half-done, next, gotchas.

## 12. Environment Notes

- Dev machine: Windows; shell is PowerShell. Activate venv with `venv\Scripts\Activate.ps1`. If script execution is blocked, use `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` for that session only.
- Database: native PostgreSQL 15 with PostGIS; Docker is optional and not required for any task.
- Geospatial Python packages can be hard to install on Windows; if `pip` wheels fail for `rasterio`/`shapely`/`pyproj`, report the error and propose a fix (matching wheels or a conda environment) rather than working around it silently.
