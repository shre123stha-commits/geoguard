"""Task 1.8: masks -> polygons -> clipped to parcels -> GeoJSON with geodesic areas (offline).

Usage: python scripts/vectorize_masks.py ../data/samples/parcels.geojson ../data/composites
Writes data/previews/candidates_optical.geojson, candidates_radar.geojson,
and candidates_all_unclipped.geojson (for inspecting what lies outside the parcels).
"""

import json
import logging
import sys
from pathlib import Path

import numpy as np
from pyproj import Transformer
from shapely.geometry import mapping
from shapely.ops import transform

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.logging import setup_logging  # noqa: E402
from app.pipeline.aoi import build_aoi  # noqa: E402
from app.pipeline.grid import make_grid  # noqa: E402
from app.pipeline.vectorize import (  # noqa: E402
    clean_mask,
    clip_to_parcels,
    mask_to_regions,
    to_feature,
)

log = logging.getLogger("vectorize_masks")


def main(parcels_path: str, comp_dir: str) -> int:
    setup_logging("INFO")
    d = Path(comp_dir)
    prev = d.parent / "previews"
    feats = json.loads(Path(parcels_path).read_text(encoding="utf-8"))["features"]
    aoi = build_aoi(feats)
    grid = make_grid(aoi.bbox_utm, aoi.epsg_utm)
    to_wgs = Transformer.from_crs(aoi.epsg_utm, 4326, always_xy=True).transform

    with np.load(d / "optical_change.npz") as z:
        opt_mask, d_bui, d_ndvi = z["mask"], z["d_bui"], z["d_ndvi"]
    with np.load(d / "radar_change.npz") as z:
        rad_mask, d_vv = z["mask"], z["d_sigma_vv_db"]

    unclipped = []
    for name, mask, layer in (("optical", opt_mask, d_bui), ("radar", rad_mask, d_vv)):
        regions = mask_to_regions(clean_mask(mask), grid)
        clipped = clip_to_parcels(regions, feats, grid)
        log.info(
            "%s: %d regions >= 400 m2 in AOI; %d clipped pieces inside parcels",
            name,
            len(regions),
            len(clipped),
        )
        fc = []
        for c in clipped:
            stat = float(np.nanmean(layer[c.pixel_mask]))
            key = "d_bui_mean" if name == "optical" else "d_sigma_vv_mean_db"
            fc.append(
                to_feature(
                    c,
                    {
                        "source": name,
                        key: round(stat, 3),
                        "d_ndvi_mean": round(float(np.nanmean(d_ndvi[c.pixel_mask])), 3),
                    },
                )
            )
            log.info("  %-28s %7.0f m2  %s=%+.2f", c.parcel_name, c.area_m2, key, stat)
        (prev / f"candidates_{name}.geojson").write_text(
            json.dumps({"type": "FeatureCollection", "features": fc}, indent=1), encoding="utf-8"
        )
        for r in regions:
            unclipped.append(
                {
                    "type": "Feature",
                    "properties": {"source": name, "area_m2": round(r.geom_utm.area)},
                    "geometry": mapping(transform(to_wgs, r.geom_utm)),
                }
            )
        by_parcel: dict[str, float] = {}
        for c in clipped:
            by_parcel[c.parcel_name] = by_parcel.get(c.parcel_name, 0) + c.area_m2
        log.info("  total per parcel: %s", {k: f"{v:.0f} m2" for k, v in by_parcel.items()})
    (prev / "candidates_all_unclipped.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": unclipped}), encoding="utf-8"
    )
    log.info(
        "wrote candidates_{optical,radar}.geojson and candidates_all_unclipped.geojson to %s", prev
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
