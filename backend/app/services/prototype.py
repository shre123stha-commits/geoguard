"""Phase-1 prototype service: file-backed parcels + detections (no database yet).

Temporary by design (tracker D42): reads `data/samples/parcels.geojson`, and runs the real
pipeline (optical + radar change → fusion → clip) on the saved composites in `data/composites`.
Phase 2 replaces the storage with PostGIS; the pipeline calls stay the same.
"""

import json
import logging
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from app.pipeline.aoi import build_aoi
from app.pipeline.fusion import fuse
from app.pipeline.grid import make_grid
from app.pipeline.optical import compute_indices, optical_change_mask
from app.pipeline.radar import radar_change_mask
from app.pipeline.vectorize import Region, clean_mask, clip_to_parcels, mask_to_regions, to_feature

log = logging.getLogger(__name__)

DISCLAIMER = (
    "Satellite detection is a screening aid. Minimum reliable detection size is about 400 m² "
    "(Sentinel 10 m pixels). Verify on the ground before acting."
)


@dataclass
class PrototypeStore:
    data_dir: Path
    parcels: list[dict[str, Any]] = field(default_factory=list)
    detections: list[dict[str, Any]] = field(default_factory=list)
    scans: list[dict[str, Any]] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def load(self) -> None:
        p = self.data_dir / "samples" / "parcels.geojson"
        if p.exists():
            feats = json.loads(p.read_text(encoding="utf-8"))["features"]
            self.parcels = [
                {
                    "id": i + 1,
                    "name": f["properties"].get("name", f"parcel-{i + 1}"),
                    "category": f["properties"].get("category", "unknown"),
                    "geometry": f["geometry"],
                }
                for i, f in enumerate(feats)
            ]
        prev = self.data_dir / "previews" / "detections.geojson"
        if prev.exists():
            fc = json.loads(prev.read_text(encoding="utf-8"))
            self._ingest(fc["features"], scan_id=0)
        log.info(
            "prototype store: %d parcels, %d detections", len(self.parcels), len(self.detections)
        )

    def _ingest(self, features: list[dict[str, Any]], scan_id: int) -> None:
        by_name = {p["name"]: p["id"] for p in self.parcels}
        start = len(self.detections)
        for k, f in enumerate(features):
            pr = f["properties"]
            self.detections.append(
                {
                    "id": start + k + 1,
                    "scan_id": scan_id,
                    "parcel_id": by_name.get(pr.get("parcel"), None),
                    "parcel_name": pr.get("parcel"),
                    "confidence": pr["confidence"],
                    "score": pr["score"],
                    "area_m2": pr["area_m2"],
                    "sources": pr.get("sources", []),
                    "metrics": {
                        "d_bui_mean": pr.get("d_bui_mean"),
                        "d_sigma_vv_mean_db": pr.get("d_sigma_vv_mean_db"),
                        "sar_overlap": pr.get("sar_overlap"),
                        "compactness": pr.get("compactness"),
                    },
                    "algorithm_version": pr.get("algorithm_version"),
                    "status": "new",
                    "geometry": f["geometry"],
                }
            )

    def composites_available(self) -> bool:
        d = self.data_dir / "composites"
        return all(
            (d / n).exists()
            for n in ("baseline_s2.npz", "current_s2.npz", "baseline_s1.npz", "current_s1.npz")
        )

    def run_scan(
        self, t_bui: float = 0.15, t_sar_db: float = 2.5, overlap: float = 0.3
    ) -> dict[str, Any]:
        """Run the real change pipeline on the saved composites (offline) and store results."""
        from app.pipeline.fusion import FusionParams
        from app.pipeline.optical import OpticalChangeParams
        from app.pipeline.radar import RadarChangeParams

        with self._lock:
            scan_id = len(self.scans) + 1
            scan: dict[str, Any] = {
                "id": scan_id,
                "status": "running",
                "created_at": datetime.now(UTC).isoformat(),
                "params": {"t_bui": t_bui, "t_sar_db": t_sar_db, "overlap": overlap},
                "detections": 0,
                "error": None,
            }
            self.scans.append(scan)
        try:
            d = self.data_dir / "composites"
            feats = [
                {"geometry": p["geometry"], "properties": {"name": p["name"]}} for p in self.parcels
            ]
            aoi = build_aoi(feats)
            grid = make_grid(aoi.bbox_utm, aoi.epsg_utm)
            with np.load(d / "baseline_s2.npz") as z:
                base_s2 = tuple(z["bands"])
            with np.load(d / "current_s2.npz") as z:
                cur_s2 = tuple(z["bands"])
            with np.load(d / "baseline_s1.npz") as z:
                base_s1 = (z["bands"][0], z["bands"][1])
            with np.load(d / "current_s1.npz") as z:
                cur_s1 = (z["bands"][0], z["bands"][1])
            ib, ic = compute_indices(*base_s2), compute_indices(*cur_s2)
            opt = optical_change_mask(ib, ic, base_s2, cur_s2, OpticalChangeParams(t_bui=t_bui))
            rad = radar_change_mask(
                base_s1, cur_s1, water=opt.water, params=RadarChangeParams(t_sar_db=t_sar_db)
            )
            rad_clean = clean_mask(rad.mask)
            optical = mask_to_regions(clean_mask(opt.mask), grid)
            radar = mask_to_regions(rad_clean, grid)
            fused = fuse(
                optical,
                radar,
                rad_clean,
                opt.d_bui,
                rad.d_sigma_vv_db,
                FusionParams(overlap_threshold=overlap),
            )
            features = []
            for f in fused:
                for c in clip_to_parcels(
                    [Region(f.region.geom_utm, f.region.pixel_mask)], feats, grid
                ):
                    features.append(to_feature(c, f.properties()))
            with self._lock:
                self.detections = [x for x in self.detections if x["scan_id"] != 0]  # replace seed
                self._ingest(features, scan_id=scan_id)
                scan["status"] = "done"
                scan["detections"] = len(features)
                scan["finished_at"] = datetime.now(UTC).isoformat()
        except Exception as exc:  # noqa: BLE001 - surfaced to the client as scan status
            log.exception("scan failed")
            with self._lock:
                scan["status"] = "failed"
                scan["error"] = str(exc)
        return scan

    def detection_feature_collection(
        self, confidence: str | None = None, parcel_id: int | None = None
    ) -> dict[str, Any]:
        feats = []
        for det in self.detections:
            if confidence and det["confidence"] != confidence:
                continue
            if parcel_id and det["parcel_id"] != parcel_id:
                continue
            props = {k: v for k, v in det.items() if k != "geometry"}
            feats.append(
                {
                    "type": "Feature",
                    "id": det["id"],
                    "properties": props,
                    "geometry": det["geometry"],
                }
            )
        return {"type": "FeatureCollection", "features": feats}

    def parcel_feature_collection(self) -> dict[str, Any]:
        return {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "id": p["id"],
                    "properties": {k: v for k, v in p.items() if k != "geometry"},
                    "geometry": p["geometry"],
                }
                for p in self.parcels
            ],
        }
