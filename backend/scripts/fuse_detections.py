"""Task 1.9: fuse optical + radar candidates into confidence-classed detections (offline).

Usage: python scripts/fuse_detections.py ../data/samples/parcels.geojson ../data/composites
Reads optical_change.npz + radar_change.npz, writes data/previews/detections.geojson
(clipped to parcels, EPSG:4326, geodesic area, confidence, score, algorithm_version).
"""

import json
import logging
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.logging import setup_logging  # noqa: E402
from app.pipeline.aoi import build_aoi  # noqa: E402
from app.pipeline.fusion import fuse  # noqa: E402
from app.pipeline.grid import make_grid  # noqa: E402
from app.pipeline.vectorize import (  # noqa: E402
    Region,
    clean_mask,
    clip_to_parcels,
    mask_to_regions,
    to_feature,
)

log = logging.getLogger("fuse_detections")


def main(parcels_path: str, comp_dir: str) -> int:
    setup_logging("INFO")
    d = Path(comp_dir)
    prev = d.parent / "previews"
    feats = json.loads(Path(parcels_path).read_text(encoding="utf-8"))["features"]
    aoi = build_aoi(feats)
    grid = make_grid(aoi.bbox_utm, aoi.epsg_utm)

    with np.load(d / "optical_change.npz") as z:
        opt_mask, d_bui = z["mask"], z["d_bui"]
    with np.load(d / "radar_change.npz") as z:
        rad_mask, d_vv = z["mask"], z["d_sigma_vv_db"]

    rad_clean = clean_mask(rad_mask)
    optical = mask_to_regions(clean_mask(opt_mask), grid)
    radar = mask_to_regions(rad_clean, grid)
    fused = fuse(optical, radar, rad_clean, d_bui, d_vv)
    log.info(
        "AOI-level: %d optical + %d radar regions -> %d fused", len(optical), len(radar), len(fused)
    )

    features = []
    counts: dict[str, dict[str, int]] = {}
    for f in fused:
        # clip each fused region to parcels; one feature per (region, parcel) piece
        pieces = clip_to_parcels([Region(f.region.geom_utm, f.region.pixel_mask)], feats, grid)
        for c in pieces:
            features.append(to_feature(c, f.properties()))
            counts.setdefault(c.parcel_name, {}).setdefault(f.confidence, 0)
            counts[c.parcel_name][f.confidence] += 1
            log.info(
                "  %-6s score=%.2f  %-18s %6.0f m2  dBUI=%+.2f dVV=%+.1f dB overlap=%.2f",
                f.confidence,
                f.score,
                c.parcel_name,
                c.area_m2,
                f.d_bui_mean,
                f.d_sigma_vv_mean_db,
                f.sar_overlap,
            )
    log.info("per parcel: %s", counts)
    out = prev / "detections.geojson"
    out.write_text(
        json.dumps({"type": "FeatureCollection", "features": features}, indent=1), encoding="utf-8"
    )
    log.info("wrote %d detections to %s", len(features), out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
