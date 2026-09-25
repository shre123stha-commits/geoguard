# ruff: noqa: E501, T201
"""Blind labelling protocol, step 1: draw random 50 m cells inside the parcels (design note §6).

Usage:
  python scripts/make_blind_cells.py ../data/samples/parcels.geojson ../data/eval/blind_cells 40 --seed 7

Writes, in the output folder:
  cells.geojson   — the cells (EPSG:4326), one feature per cell with id, parcel, centre
  sheet.csv       — the labelling sheet you fill in (one row per cell)
  README.txt      — how to label, with one Esri Wayback link per cell (before / after)

Cells are drawn *stratified by parcel area* with a fixed seed, so the draw is reproducible and
independent of any detector output. Do not look at GeoGuard while labelling.
"""

import argparse
import csv
import json
import random
import sys
from pathlib import Path

from pyproj import Transformer
from shapely.geometry import box, mapping, shape
from shapely.ops import transform as shp_transform

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.pipeline.aoi import build_aoi  # noqa: E402

CELL_M = 50.0
BEFORE_RELEASE = "2020-12-16"  # Wayback releases used for the v1 labels (docs/evaluation.md)
AFTER_RELEASE = "2023-06-13"


def wayback_url(lon: float, lat: float, zoom: int = 19) -> str:
    # The Wayback app opens at the given centre; the user picks the release from the timeline.
    return f"https://livingatlas.arcgis.com/wayback/#active=all&mapCenter={lon:.6f}%2C{lat:.6f}%2C{zoom}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("parcels")
    ap.add_argument("out_dir")
    ap.add_argument("n", type=int)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--min-per-parcel", type=int, default=6)
    a = ap.parse_args()

    feats = json.loads(Path(a.parcels).read_text(encoding="utf-8"))["features"]
    aoi = build_aoi(feats)
    to_utm = Transformer.from_crs(4326, aoi.epsg_utm, always_xy=True).transform
    to_wgs = Transformer.from_crs(aoi.epsg_utm, 4326, always_xy=True).transform
    polys = [(f["properties"]["name"], shp_transform(to_utm, shape(f["geometry"]))) for f in feats]
    total = sum(p.area for _, p in polys)
    rng = random.Random(a.seed)

    # allocation: proportional to area, with a floor per parcel
    alloc = {n: max(a.min_per_parcel, round(a.n * p.area / total)) for n, p in polys}
    cells = []
    for name, poly in polys:
        minx, miny, maxx, maxy = poly.bounds
        got = 0
        tries = 0
        while got < alloc[name] and tries < 20000:
            tries += 1
            x = rng.uniform(minx, maxx - CELL_M)
            y = rng.uniform(miny, maxy - CELL_M)
            c = box(x, y, x + CELL_M, y + CELL_M)
            if c.intersection(poly).area < 0.8 * c.area:
                continue
            if any(c.intersects(o["geom_utm"]) for o in cells):
                continue  # no overlapping cells
            cells.append({"parcel": name, "geom_utm": c})
            got += 1
    rng.shuffle(cells)  # so the sheet order carries no parcel information

    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    features = []
    rows = []
    links = []
    for i, c in enumerate(cells, 1):
        g = shp_transform(to_wgs, c["geom_utm"])
        lon, lat = g.centroid.x, g.centroid.y
        cid = f"C{i:03d}"
        features.append(
            {
                "type": "Feature",
                "id": cid,
                "properties": {
                    "id": cid,
                    "parcel": c["parcel"],
                    "lon": round(lon, 6),
                    "lat": round(lat, 6),
                },
                "geometry": mapping(g),
            }
        )
        rows.append(
            {
                "id": cid,
                "lat": f"{lat:.6f}",
                "lon": f"{lon:.6f}",
                "label": "",
                "confidence": "",
                "note": "",
            }
        )
        links.append(f"{cid}  {lat:.5f}, {lon:.5f}\n   {wayback_url(lon, lat)}")

    (out / "cells.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": features}), encoding="utf-8"
    )
    with (out / "sheet.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    readme = (
        f"""BLIND LABELLING — {len(cells)} cells of {CELL_M:.0f} m x {CELL_M:.0f} m, seed {a.seed}
Draw: {", ".join(f"{k}: {v}" for k, v in alloc.items())}

RULES (read before starting)
1. Do NOT open GeoGuard, its detections, or docs/evaluation.md while labelling.
2. For each cell open the Wayback link, then in the timeline on the left compare the
   release nearest {BEFORE_RELEASE} with the one nearest {AFTER_RELEASE}. The map opens
   centred on the cell; the cell is the {CELL_M:.0f} m square around the centre (about one or two
   house plots at zoom 19). Judge only what is inside that square.
3. Fill sheet.csv:
     label       one of:  new_built   (a structure, paved lot, compound wall or fill that was
                                        not there before and is still there after)
                          no_change   (same land cover both dates, incl. seasonal water/grass)
                          other_change (cleared / dug / burnt / flooded but no structure)
                          cannot_tell (cloud, missing tile, too ambiguous)
     confidence  1 (guess) – 3 (certain)
     note        free text, optional
4. Do all cells in one or two sittings; ~1 minute each.
5. When done, run:  python scripts\\evaluate_blind.py  (see its header) — it scores every method
   against your labels and reports precision / recall with 95 % intervals.

CELLS
"""
        + "\n".join(links)
        + "\n"
    )
    (out / "README.txt").write_text(readme, encoding="utf-8")
    print(f"{len(cells)} cells → {out}")
    for k, v in alloc.items():
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
