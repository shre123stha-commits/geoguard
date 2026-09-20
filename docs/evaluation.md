# GeoGuard-EO — Evaluation of the detection method (v1.0)

*Written 2026-09-20 from the Phase 1 evaluation (tasks 1.9–1.11, tracker D39–D43). Re-run
with `python scripts\evaluate_detections.py ..\data\samples\parcels.geojson ..\data\composites ..\data\eval\labels.geojson`.*

## 1. What is being evaluated

The v1 detector (`idx-fusion-1.0.0`) flags **likely new built-up surface** inside protected
parcels by comparing two periods of free Sentinel imagery:

| Step | Data | Rule |
|---|---|---|
| Optical change | Sentinel-2 L2A, per-period cloud-free median composite (SCL mask) | built-up index rise `ΔBUI ≥ 0.15` **and** vegetation loss `ΔNDVI ≤ −0.10`; water-like pixels excluded; AOI-median centring; 3×3 opening |
| Radar change | Sentinel-1 RTC VV, per-period median in linear power → dB, 3×3 median speckle filter | `Δσ°VV ≥ 2.5 dB`, same water exclusion and opening |
| Fusion | both masks | optical region with ≥ 30 % radar overlap → **high**; optical only → **medium**; radar only → **low**; polygons < 400 m² dropped |

Score (0–1) = 0.4·norm(ΔBUI) + 0.3·norm(Δσ°) + 0.2·overlap + 0.1·compactness. It orders
detections within a class; it is not a probability.

## 2. Test area and labelled set

* **Area:** western edge of the Pallikaranai marsh, Chennai (AOI 1.5 km², UTM 44N).
  Three parcels: `Pallikaranai-West-1` (wetland, 19.8 ha, known encroachment),
  `Control-Marsh` (4.7 ha, should stay empty), `Control-Builtup` (3.4 ha, already built, should
  stay empty).
* **Windows:** baseline 2020-01-15 → 2020-03-31; current 2023-01-15 → 2023-03-31 (same dry season).
* **Labels** (`data/eval/labels.geojson`, 9 sites): the 8 v1 detections plus one known miss,
  judged against Esri Wayback imagery (releases 2020-12-16 and 2023-06-13). 7 `real`, 2 `unsure`,
  1 `missed` (a real change with no detection).
* **Matching:** IoU ≥ 0.3 or the smaller geometry ≥ 50 % covered. `unsure` sites are excluded
  from precision; a detection matching nothing counts as a false positive.

## 3. Results with the default thresholds

| Class | Detections | True | False | Unsure | Precision |
|---|---|---|---|---|---|
| high | 3 | 3 | 0 | 0 | **100 %** |
| medium | 2 | 1 | 0 | 1 | 100 % (n = 1) |
| low | 3 | 2 | 0 | 1 | 100 % (n = 2) |
| **all** | **8** | **6** | **0** | **2** | **100 %** |

* **Recall:** 6 / 7 real sites = **86 %**. The miss is a group of single houses < 400 m² each in
  the south of West-1 — below the minimum reliable size by design.
* **Controls:** 0 high, 0 medium in both control parcels. `Control-Builtup` produced one `low`
  (radar-only, 1 901 m²) that Wayback shows as a roof change on an existing building — correctly
  ranked lowest.
* **Marsh dynamics:** the control marsh went from dry (2020) to flooded (2023); the water
  exclusion prevented any optical false alarm there (ablation in tracker D31/D33: without it the
  marsh would be 43 % "candidate").

PRD target "≥ 80 % of `high` judged real" — **met (3/3)**, with the caveat that n is small.

## 4. Threshold sweep

48 settings (`T_bui` 0.10–0.25 × `T_sar` 2.0–3.5 dB × overlap 0.2–0.5); full table in
`docs/samples/eval_sweep.csv`.

* No setting produced a `high` false positive.
* `T_bui` 0.10 gives the same result as 0.15; 0.20 and above demote two real highs to low and
  recall falls to 57 %.
* `T_sar` 2.0 adds two unlabelled `low` polygons (counted as fp); 3.5 loses one real `low`
  (recall 71 %).
* Overlap 0.2–0.5 only moves detections between high and medium.

Conclusion: the defaults sit on a flat optimum; there is no evidence for tuning on this set.

## 5. Known failure modes and limits

1. **Size.** 10 m pixels: anything under ~400 m² (a single house) is unreliable and is dropped.
   Expect misses for scattered small buildings; expect catches for plots, sheds, roads, fill.
2. **Bare soil and ploughing** look like construction optically; radar agreement (`high`)
   separates most of it. Review `medium` with more scepticism.
3. **Seasonal water** changes reflectance and backscatter strongly. Same-season windows and the
   water exclusion handle most of it; a flooded baseline and dry current period is still the
   hardest case.
4. **Clouds.** Tile-wide cloud metadata is unreliable for a small AOI; the per-pixel SCL mask does
   the work. Fewer than ~3 clear scenes in a window makes the composite noisy — the scan warns.
5. **Time offset of reference imagery.** High-resolution reference releases rarely coincide with
   the Sentinel windows, so ground truth itself has months of uncertainty (the 2020 reference was
   9 months after the baseline window; this can only understate precision).
6. **Tiny sample.** 9 labelled sites in one landscape. Precision figures are indicative, not
   statistical. A wider label set (other land covers, coastal, hill) is the first thing to do in
   v1.1.

## 6. How to extend the evaluation

1. Label more sites in `data/eval/labels.geojson` (properties `label`: `real | not_real |
   unsure | missed`, `source`, `note`).
2. Re-run the script; it prints per-class precision, recall and the sweep table.
3. Record the row in tracker §7 and, if thresholds change, bump `ALGORITHM_VERSION`.
