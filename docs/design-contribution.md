# GeoGuard-EO — Design contribution

*What in this project is a design decision rather than an off-the-shelf part, and the evidence
for each. Written 2026-09-24 for the v1.2 review. Every number below is reproducible with the
scripts named in §7; nothing here was run outside this repository.*

## 1. The problem as actually posed

A district office wants to know, every few weeks, whether new built-up surface has appeared
inside protected wetland parcels around Chennai. The constraints are the design problem:

| Constraint | Consequence for the design |
|---|---|
| Monsoon: June–December is cloudy; the marsh floods and dries every year | A single "before/after" pair is unreliable; seasonal change looks like construction |
| No ground truth, no training set, no budget | Cannot train a classifier; must be explainable and verifiable by an officer |
| Sentinel-2 at 10 m | Anything below ~400 m² is unreliable by construction |
| Legal sensitivity | The tool must never assert a violation; it screens and hands over to a human |
| Zero cost, one laptop, no Docker, no cloud account | Free STAC data, free database tier, e-mail alerts, phone browser for field work |

The individual components (Sentinel-1/2, NDBI/NDVI, PostGIS, FastAPI, React) are standard. The
contribution is the set of decisions that make them work under these constraints, and the
measurements that show each decision matters.

## 2. The six design decisions

1. **Agreement-based optical/radar fusion instead of a classifier.** Optical change (built-up
   index rise *and* vegetation loss) proposes; Sentinel-1 backscatter rise (a structure) corroborates.
   Confidence is the *agreement*: ≥ 30 % radar overlap → high; optical only → medium; radar only →
   low. No training data, every class explainable in one sentence.
2. **Physically motivated exclusions rather than thresholds alone:** water-like pixels in either
   period are never candidates (a drying pond is the single biggest false-positive source in a
   marsh); AOI-median centring removes scene-wide radiometric or moisture shifts; a 3×3
   morphological opening removes single-pixel speckle; 400 m² minimum matches the sensor.
3. **Screening workflow, not verdicts.** Statuses *new → field visit → confirmed / dismissed*,
   dismissals need a reason code, every change is audited, wording rules forbid "illegal".
   A phone page lets the officer confirm on site with a geotagged photo (EXIF stripped).
4. **Temporal persistence as a false-alarm filter.** A site can be required to be flagged in
   2–3 consecutive scans before an e-mail is sent; the count is derived from the existing
   detection-matching chain, so it costs nothing and stays consistent.
5. **The system calibrates itself from officer decisions, without ML.** Confirm/dismiss
   history becomes per-class precision, dismiss-reason mix and plain-language threshold
   suggestions. Thresholds are never changed automatically.
6. **Dating change, not just detecting it (this note's §5).** A per-pixel seasonal model fitted
   to the parcel's own history turns "changed between the two windows" into "changed in
   month *m*", and removes the same-season requirement that the two-window method imposes.

## 3. Evaluation set (and its limits)

Western edge of the Pallikaranai marsh, 1.5 km², three parcels (one wetland with known
encroachment, a marsh control, a built-up control). Labels: 9 sites judged against Esri Wayback
imagery of 2020-12 and 2023-06 — 7 real changes (one of them missed by v1), 2 unsure.
Any detection matching no labelled site counts as a false positive. The set is small and was
seeded from v1's own output, so **it over-states v1's precision and under-states any method
that finds change v1 did not**; see §6.

**Blind protocol (prepared 2026-09-25, labels pending).** To remove that bias,
`scripts/make_blind_cells.py` drew 41 random 50 m cells (28 in West-1, 7 in the marsh control,
6 in the built-up control; seed 7) *before* looking at any output; `docs/samples/blind_cells/`
holds the cells, a labelling sheet with a Wayback link per cell, and a README. Each cell is
labelled from Wayback 2020-12-16 vs 2023-06-13 as new_built / no_change / other_change /
cannot_tell. `scripts/evaluate_blind.py` then scores every method in §4–§5 by whether it flags
≥ 2 pixels of a cell, with Wilson 95 % intervals. The numbers will replace this paragraph once
the owner has labelled the sheet — they are not estimated here.

## 4. Ablation — each element removed in turn

`scripts/ablation.py`, same composites as the shipped scan (baseline Jan–Mar 2020, current
Jan–Mar 2023). Figure: `docs/figures/ablation.png`, `pr_curve.png`; table `ablation.csv`.

| Variant | n | tp | fp | unsure | Precision | Recall |
|---|---|---|---|---|---|---|
| **Full method (optical + radar fusion)** | 8 | 6 | 0 | 2 | **100 %** | **86 %** |
| Full method, high + medium only | 5 | 4 | 0 | 1 | 100 % | 57 % |
| Optical only (ΔBUI ∧ ΔNDVI) | 5 | 4 | 0 | 1 | 100 % | 57 % |
| Radar only (Δσ°VV) | 6 | 3 | 2 | 1 | 60 % | 43 % |
| − water exclusion | 11 | 6 | 3 | 2 | 67 % | 86 % |
| − AOI-median centring | 7 | 5 | 0 | 2 | 100 % | 71 % |
| − 3×3 opening | 17 | 6 | 11 | 0 | 35 % | 71 % |
| − 400 m² minimum (100 m²) | 8 | 6 | 0 | 2 | 100 % | 86 % |

What it shows: neither sensor alone reaches the fused result (optical alone misses two real
sites that only radar caught; radar alone has 60 % precision). Water exclusion and the opening
are each worth a third to two-thirds of the precision. The 400 m² floor changes nothing here
because the opening already removes small specks — it is a *communication* rule (what the tool
promises), not a filter that does work. Over the ΔBUI threshold (`pr_curve.png`), fusion keeps
100 % precision up to 0.15 while recall falls steadily above it; 0.15 is the knee, which is why
it is the default.

## 5. Phenology-normalised change detection (new method)

**Why.** The marsh's own seasonal cycle of the built-up index is 0.40 between May and
September (`seasonal_cycle.png`) — 2.7× the change threshold. The two-window method therefore
only works if the operator picks same-season windows, which the monsoon makes impossible for
half the year, and it can never say *when* the change happened.

**Method** (`app/pipeline/phenology.py`, 150 lines of NumPy). For every pixel, fit a
two-harmonic seasonal model to a reference period (here 2019–2020, 23 clear months):

BUI(t) ≈ a + b cos(2πt/12) + c sin(2πt/12) + d cos(4πt/12) + e sin(4πt/12)

then in every later month compute the anomaly *observed − expected* for BUI and NDVI. A pixel
becomes a change when (i) BUI anomaly ≥ 0.15 and NDVI anomaly ≤ −0.10 in two consecutive
*clear* months (cloudy months are skipped, not counted), (ii) the condition still holds in
≥ 40 % of the clear months after that — **permanence**: built surface stays built, a dry year or
a cleared-then-regrown plot does not — and (iii) the pixel is not water-like in that month.
The first month of the run is the **onset**. Months with < 50 % clear pixels are discarded.

**Experiment** (`scripts/phenology_change.py`, on a 60-month Sentinel-2 stack Jan 2019 – Dec 2023
fetched by `scripts/fetch_monthly_indices.py`; optical only on both sides).

| Method | n | tp | fp | Precision | Recall |
|---|---|---|---|---|---|
| Two-window, same season (Jan–Mar 2020 → Jan–Mar 2023) | 5 | 4 | 1 | 80 % | 71 % |
| Two-window, wet → dry (Sep–Nov 2019 → Mar–May 2023) | 6 | 4 | 2 | 67 % | 86 % |
| Two-window, dry → wet (Mar–May 2020 → Sep–Nov 2023) | 6 | 2 | 4 | 33 % | 43 % |
| **Phenology-normalised, defaults (no season choice needed)** | 7 | 4 | 3 | 57 % | **86 %** |
| Phenology-normalised, 3-month persistence | 6 | 4 | 2 | 67 % | 86 % |

Read with §3's caveat. The two-window method degrades sharply when seasons are mismatched
(33 % precision, 43 % recall dry→wet); the phenology method has no season to mismatch. It reaches
the highest recall of any optical-only run (the same six sites as the full fused method). Site 9
— the shed v1 missed — is flagged at pixel level (67 % of its pixels, onset Aug 2023) but its
approximate label sits on the parcel edge and is clipped away, so it is not counted for any
method. Of the three "false positives", one (onset Oct 2021) lies ~50 m from that approximate
position, one has onset Aug 2023, *after* the June 2023 imagery the labels were judged on, and
one is unverified. Its true precision is
therefore between 57 % and 86 %; establishing which needs imagery we do not have here.

**Onset dating** (`onsets.csv`, `site_anomalies.png`): site 2 Nov 2021, site 5 Apr 2022, site 7
Apr 2022, site 1 May 2022, site 3 Aug 2022, site 6 Oct 2022 — all inside the Dec 2020 – Jun 2023
interval the labels allow, and the anomaly panels show clean permanent steps for the large
sites. The built-up control (site 8) stays within ±0.05 of its expected season for five years,
which is the negative control the method needs.

**Cost.** One month of one parcel takes ~10 s from Planetary Computer; the 60-month AOI stack
took 10 minutes and is cached.

**In the product (v1.3).** The method is a scan mode: *New scan → Seasonal model*. The runner
builds one Sentinel-2 and one Sentinel-1 composite per month (`app/services/monthly_stack.py`,
cached per grid and month), fits the seasonal model on the reference months, flags anomalies
that persist ≥ 3 months in the monitored months, and applies the **same** radar-overlap
confidence rule as two-window mode — with the radar side now also a seasonal anomaly
(`phenology.detect_radar`: VV backscatter ≥ 2.5 dB above its own seasonal expectation for
2 months), so wet-season soil moisture cannot confirm an optical false alarm. Each detection
carries the month its change began (`onset_month`, median pixel onset), shown as a chip on the
detail page. A synthetic 36-month test dates a planted April step to April exactly and flags
no pixel outside it (`tests/integration/test_seasonal_phase9.py`).

## 6. Limitations, stated plainly

* Nine labelled sites is a pilot, not a benchmark; confidence intervals would be wide.
  The labels came from v1's detections plus one known miss, which biases every comparison
  toward v1. The remedy is an independent label set (e.g. 30 random 100 m cells judged blind).
* Precision counts unlabelled detections as false — conservative for v1, unfair to §5.
* The seasonal model needs ≥ 8 clear reference months per pixel and assumes the reference period
  itself is stable; a parcel already changing in 2019–2020 will have its early change absorbed.
* Sentinel-2 cannot see under clouds; July–October usually leaves 1–3 usable months.
* No ML anywhere — deliberate, but it means the method will not improve from data by itself
  beyond the threshold suggestions in Settings.

## 7. Reproduce

```powershell
cd backend; .\.venv\Scripts\Activate.ps1
python scripts\ablation.py ..\data\samples\parcels.geojson ..\data\composites ..\data\eval\labels.geojson ..\docs\figures
python scripts\fetch_monthly_indices.py ..\data\samples\parcels.geojson ..\data\phenology 2019-01 2023-12   # ~10 min online
python scripts\phenology_change.py ..\data\samples\parcels.geojson ..\data\phenology ..\data\eval\labels.geojson ..\docs\figures
pytest tests\test_phenology.py
```

## 8. Three-minute live demonstration (workflow design)

1. **Zones** → the wetland boundary layer is listed with source and date.
2. **Detections** → filter *Inside / near a reference zone* → the list is ranked by priority
   and confidence; chips show "seen in N scans in a row".
3. Open a high-confidence detection → before/after slider, metrics, zone context.
4. Click **On site? Open field page** (or open the same URL on a phone) → distance to the site,
   **Take a photo** (position and distance saved), **Confirm change** with a note.
5. The confirmation e-mail arrives (Alerts) — or waits, if *Seen in scans* is set to 2.
6. **Settings → What your reviews say** → the confirmed decision has moved the per-class
   precision; the threshold suggestion updates.
7. **Parcels → Pallikaranai-West-1 → Change over time** → the monthly built-up share and the
   month the change began.
