"""Runs one scan end to end (techspec §5.2 steps 1–13) and persists the results.

Pure orchestration: the numerical work lives in `app.pipeline.*`; SQL lives in the
repositories. Progress is committed after every step so the API can show it live.
"""

import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.enums import ConfidenceClass, EvidenceKind, PeriodType, ScanStatus, SensorType
from app.db.models import Parcel, Scan
from app.pipeline.aoi import Aoi, AoiError, build_aoi
from app.pipeline.cache import RasterCache
from app.pipeline.composite import (
    PeriodComposites,
    build_optical_composite,
    build_radar_composite,
)
from app.pipeline.fusion import ALGORITHM_VERSION, FusedRegion, FusionParams, fuse
from app.pipeline.grid import TargetGrid, make_grid
from app.pipeline.optical import OpticalChangeParams, compute_indices, optical_change_mask
from app.pipeline.radar import RadarChangeParams, radar_change_mask
from app.pipeline.sources.base import GridReader, ImageryError, SceneRef
from app.pipeline.vectorize import Region, clean_mask, clip_to_parcels, mask_to_regions
from app.repositories import DetectionRepository, ParcelRepository, ScanRepository
from app.repositories.base import from_db
from app.services.evidence import EvidenceWriter

logger = logging.getLogger(__name__)

# Ordered pipeline steps: key -> (label, progress % when the step *starts*)
STEPS: list[tuple[str, str, int]] = [
    ("aoi", "Preparing area of interest", 2),
    ("search", "Searching satellite scenes", 5),
    ("baseline", "Building baseline composite", 15),
    ("current", "Building current composite", 45),
    ("change", "Detecting change", 75),
    ("fusion", "Combining optical and radar evidence", 85),
    ("persist", "Saving detections and evidence", 92),
]
_STEP_PROGRESS = {k: p for k, _, p in STEPS}
_STEP_LABEL = {k: lbl for k, lbl, _ in STEPS}


class ScanFailedError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ScanParams:
    """Tunable parameters stored in `scans.params` (techspec §5.2 defaults)."""

    t_bui: float = 0.15
    t_ndvi_drop: float = 0.10
    t_sar_db: float = 2.5
    overlap: float = 0.3
    min_area_m2: float = 400.0
    cloud_cover_max: int = 30

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ScanParams":
        known = {k: d[k] for k in cls.__dataclass_fields__ if k in d}
        return cls(**known)

    def to_dict(self) -> dict[str, Any]:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


@dataclass
class ScanResult:
    scan_id: uuid.UUID
    detections: int
    scenes: int
    seconds: float


SourceFactory = Callable[[Settings], GridReader]


def default_source_factory(settings: Settings) -> GridReader:
    if settings.imagery_provider == "local_folder":
        from app.pipeline.sources.local_folder import LocalFolderSource

        return LocalFolderSource(settings.data_dir / "local_scenes")
    from app.pipeline.sources.planetary_computer import PlanetaryComputerSource

    return PlanetaryComputerSource(
        settings.stac_api_url, cache=RasterCache(settings.data_dir / "cache")
    )


class ScanRunner:
    def __init__(
        self,
        db: Session,
        settings: Settings,
        source_factory: SourceFactory = default_source_factory,
        evidence_root: Path | None = None,
    ) -> None:
        self.db = db
        self.settings = settings
        self.scans = ScanRepository(db)
        self.detections = DetectionRepository(db)
        self.parcels = ParcelRepository(db)
        self._source_factory = source_factory
        self.evidence = EvidenceWriter(evidence_root or settings.data_dir / "evidence")

    # ---- progress -------------------------------------------------------------------------
    def _step(self, scan: Scan, key: str, message: str | None = None) -> None:
        self.scans.set_progress(scan, key, _STEP_PROGRESS[key], message or _STEP_LABEL[key])
        self.db.commit()
        logger.info("scan step", extra={"scan_id": str(scan.id), "step": key})

    # ---- main -----------------------------------------------------------------------------
    def run(self, scan: Scan) -> ScanResult:
        t0 = time.perf_counter()
        try:
            result = self._run(scan, t0)
        except ScanFailedError as exc:
            self._fail(scan, exc.code, str(exc))
            raise
        except (ImageryError, AoiError) as exc:
            code = "no_imagery" if isinstance(exc, ImageryError) else "bad_aoi"
            self._fail(scan, code, str(exc))
            raise ScanFailedError(code, str(exc)) from exc
        except Exception as exc:  # noqa: BLE001 - recorded on the scan row, then re-raised
            logger.exception("scan crashed", extra={"scan_id": str(scan.id)})
            self._fail(scan, "internal_error", f"{exc.__class__.__name__}: {exc}"[:500])
            raise ScanFailedError("internal_error", str(exc)) from exc
        return result

    def _fail(self, scan: Scan, code: str, message: str) -> None:
        self.db.rollback()
        scan = self.scans.get(scan.id) or scan
        self.scans.finish(scan, ScanStatus.failed, message=message, error_code=code)
        self.db.commit()

    def _run(self, scan: Scan, t0: float) -> ScanResult:
        params = ScanParams.from_dict(scan.params)
        parcels = self._scan_parcels(scan)
        feats = [
            {"geometry": from_db(p.geom), "properties": {"name": p.name, "id": str(p.id)}}
            for p in parcels
        ]

        self._step(scan, "aoi")
        aoi = build_aoi(feats)
        grid = make_grid(aoi.bbox_utm, aoi.epsg_utm)
        self._store_aoi(scan, aoi)
        self._warn_season(scan)

        self._step(scan, "search")
        src = self._source_factory(self.settings)
        periods = {
            PeriodType.baseline: (scan.baseline_start, scan.baseline_end),
            PeriodType.current: (scan.current_start, scan.current_end),
        }
        scenes: dict[PeriodType, tuple[list[SceneRef], list[SceneRef]]] = {}
        for period, rng in periods.items():
            s2 = src.search_optical(aoi.bbox_wgs84, rng, params.cloud_cover_max)
            s1 = src.search_radar(aoi.bbox_wgs84, rng)
            if not s2:
                raise ScanFailedError(
                    "no_optical_scenes",
                    f"No clear Sentinel-2 scenes for the {period.value} period "
                    f"({rng[0]}..{rng[1]}, cloud <= {params.cloud_cover_max}%). "
                    "Try a wider window or a higher cloud limit.",
                )
            if not s1:
                raise ScanFailedError(
                    "no_radar_scenes",
                    f"No Sentinel-1 scenes for the {period.value} period ({rng[0]}..{rng[1]}).",
                )
            scenes[period] = (s2, s1)
            for s in s2:
                self._add_scene(scan, SensorType.sentinel2, period, s)
            for s in s1:
                self._add_scene(scan, SensorType.sentinel1, period, s)
        self.db.commit()

        comps: dict[PeriodType, PeriodComposites] = {}
        for period in (PeriodType.baseline, PeriodType.current):
            s2, s1 = scenes[period]
            self._step(
                scan,
                period.value,
                f"{_STEP_LABEL[period.value]} ({len(s2)} optical, {len(s1)} radar scenes)",
            )
            comps[period] = PeriodComposites(
                optical=build_optical_composite(src, s2, grid),
                radar=build_radar_composite(src, s1, grid),
                optical_scenes=s2,
                radar_scenes=s1,
            )

        self._step(scan, "change")
        base, cur = comps[PeriodType.baseline], comps[PeriodType.current]
        base_s2 = tuple(base.optical.bands)
        cur_s2 = tuple(cur.optical.bands)
        ib, ic = compute_indices(*base_s2), compute_indices(*cur_s2)
        opt = optical_change_mask(
            ib,
            ic,
            base_s2,
            cur_s2,
            OpticalChangeParams(t_bui=params.t_bui, t_ndvi_drop=params.t_ndvi_drop),
        )
        base_s1 = (base.radar.bands[0], base.radar.bands[1])
        cur_s1 = (cur.radar.bands[0], cur.radar.bands[1])
        rad = radar_change_mask(
            base_s1, cur_s1, water=opt.water, params=RadarChangeParams(t_sar_db=params.t_sar_db)
        )

        self._step(scan, "fusion")
        rad_clean = clean_mask(rad.mask)
        optical = mask_to_regions(clean_mask(opt.mask), grid, min_area_m2=params.min_area_m2)
        radar = mask_to_regions(rad_clean, grid, min_area_m2=params.min_area_m2)
        fused = fuse(
            optical,
            radar,
            rad_clean,
            opt.d_bui,
            rad.d_sigma_vv_db,
            FusionParams(overlap_threshold=params.overlap),
        )

        self._step(scan, "persist")
        n = self._persist(scan, parcels, feats, fused, grid, opt.d_ndvi, base, cur, opt.d_bui)
        n_scenes = sum(len(a) + len(b) for a, b in scenes.values())
        msg = f"{n} detection{'s' if n != 1 else ''} in {len(parcels)} parcel(s)"
        self.scans.finish(scan, ScanStatus.succeeded, message=msg)
        self.db.commit()
        secs = time.perf_counter() - t0
        logger.info(
            "scan done",
            extra={"scan_id": str(scan.id), "detections": n, "scenes": n_scenes, "secs": secs},
        )
        return ScanResult(scan.id, n, n_scenes, secs)

    # ---- helpers --------------------------------------------------------------------------
    def _scan_parcels(self, scan: Scan) -> list[Parcel]:
        ids = self.scans.parcel_ids(scan)
        parcels = [p for pid in ids if (p := self.parcels.get(pid)) is not None]
        if not parcels:
            raise ScanFailedError("no_parcels", "The scan has no parcels")
        return parcels

    def _store_aoi(self, scan: Scan, aoi: Aoi) -> None:
        from shapely.geometry import box

        from app.repositories.base import to_db

        scan.aoi_geom = to_db(box(*aoi.bbox_wgs84))
        self.db.flush()

    def _warn_season(self, scan: Scan) -> None:
        """techspec §5.3: warn when the two windows are not the same season (±30 days of year)."""
        b = _mid_doy(scan.baseline_start, scan.baseline_end)
        c = _mid_doy(scan.current_start, scan.current_end)
        diff = min(abs(b - c), 365 - abs(b - c))
        if diff > 30:
            p = dict(scan.params)
            p["warnings"] = [
                *p.get("warnings", []),
                f"Baseline and current windows are {diff} days apart in the year; seasonal "
                "differences may look like change.",
            ]
            scan.params = p
            self.db.flush()

    def _add_scene(self, scan: Scan, sensor: SensorType, period: PeriodType, s: SceneRef) -> None:
        orbit = None
        if s.orbit_direction or s.relative_orbit is not None:
            orbit = f"{s.orbit_direction or ''}/{s.relative_orbit or ''}".strip("/")
        self.scans.add_scene(
            scan,
            sensor,
            period,
            s.scene_id,
            s.acquired_at,
            cloud_cover=s.cloud_cover,
            orbit=orbit,
            meta={k: v for k, v in s.meta.items() if isinstance(v, str | int | float | bool)},
        )

    def _persist(
        self,
        scan: Scan,
        parcels: list[Parcel],
        feats: list[dict[str, Any]],
        fused: list[FusedRegion],
        grid: TargetGrid,
        d_ndvi: np.ndarray,
        base: PeriodComposites,
        cur: PeriodComposites,
        d_bui: np.ndarray,
    ) -> int:
        n = 0
        for f in fused:
            clipped = clip_to_parcels(
                [Region(f.region.geom_utm, f.region.pixel_mask)],
                feats,
                grid,
                min_area_m2=ScanParams.from_dict(scan.params).min_area_m2,
            )
            for c in clipped:
                parcel = parcels[c.parcel_index]
                dn = (
                    float(np.nanmean(d_ndvi[f.region.pixel_mask]))
                    if f.region.pixel_mask.any()
                    else None
                )
                det = self.detections.create(
                    scan,
                    parcel,
                    geometry=_mapping(c.geom_wgs84),
                    area_m2=c.area_m2,
                    confidence=ConfidenceClass(f.confidence),
                    score=float(min(1.0, max(0.0, f.score))),
                    optical_detected="optical" in f.sources,
                    radar_detected="radar" in f.sources,
                    d_bui_mean=_finite(f.d_bui_mean),
                    d_ndvi_mean=_finite(dn),
                    d_sigma_vv_mean=_finite(f.d_sigma_vv_mean_db),
                    sar_overlap=float(min(1.0, max(0.0, f.sar_overlap))),
                )
                prev = self.detections.find_previous_match(det)
                if prev is not None:
                    det.matches_detection = prev.id
                try:
                    files = self.evidence.write_all(
                        scan.id, det.id, c.geom_utm.bounds, grid, base, cur, d_bui
                    )
                except Exception:  # noqa: BLE001 - evidence is best-effort
                    logger.exception("evidence failed", extra={"detection_id": str(det.id)})
                    files = []
                for kind, rel_path, (w, h), bounds_wgs in files:
                    self.detections.add_evidence(
                        det, EvidenceKind(kind), rel_path, w, h, bounds_wgs
                    )
                n += 1
        self.db.flush()
        return n


def _mid_doy(a: date, b: date) -> int:
    return (a.timetuple().tm_yday + b.timetuple().tm_yday) // 2


def _finite(x: float | None) -> float | None:
    if x is None or not np.isfinite(x):
        return None
    return float(x)


def _mapping(g: Any) -> dict[str, Any]:
    from shapely.geometry import mapping

    out: dict[str, Any] = dict(mapping(g))
    return out


__all__ = [
    "ALGORITHM_VERSION",
    "STEPS",
    "ScanFailedError",
    "ScanParams",
    "ScanResult",
    "ScanRunner",
]
