"""Turn the Phase 1 composites (data/composites/*.npz) into an offline `local_scenes` folder.

Each period composite becomes one synthetic "scene" (dated mid-window) readable by
`LocalFolderSource`, so the sample area can be scanned with IMAGERY_PROVIDER=local_folder and
no network. Reflectance is written back as DN x 10000 (processing baseline 02.14, no offset).

Usage (from backend/): python scripts/composites_to_local_scenes.py ..\\data
"""

import json
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.pipeline.aoi import build_aoi  # noqa: E402
from app.pipeline.grid import make_grid  # noqa: E402
from app.pipeline.radar import to_linear  # noqa: E402
from app.pipeline.sources.local_folder import write_manifest, write_scene  # noqa: E402


def main(data_dir: str) -> int:
    data = Path(data_dir).resolve()
    comp, out = data / "composites", data / "local_scenes"
    parcels = json.loads((data / "samples" / "parcels.geojson").read_text(encoding="utf-8"))
    windows = json.loads((data / "samples" / "windows.json").read_text(encoding="utf-8"))
    aoi = build_aoi(parcels["features"])
    grid = make_grid(aoi.bbox_utm, aoi.epsg_utm)
    records = []
    for period in ("baseline", "current"):
        a, b = (date.fromisoformat(d) for d in windows[period])
        mid = datetime.combine(a + (b - a) / 2, datetime.min.time(), tzinfo=UTC)
        with np.load(comp / f"{period}_s2.npz") as z:
            red, nir, swir = z["bands"]
            n_s2 = len(z["scene_ids"])
        scl = np.where(np.isnan(red), 0.0, 4.0)
        records.append(
            write_scene(
                out,
                f"composite_{period}_s2",
                "sentinel2",
                mid,
                {"B04": red * 10000, "B08": nir * 10000, "B11": swir * 10000, "SCL": scl},
                grid,
                cloud_cover=0.0,
                meta={"processing_baseline": "02.14", "source_scenes": int(n_s2)},
            )
        )
        with np.load(comp / f"{period}_s1.npz") as z:
            vv_db, vh_db = z["bands"]
            n_s1 = len(z["scene_ids"])
        records.append(
            write_scene(
                out,
                f"composite_{period}_s1",
                "sentinel1",
                mid + timedelta(hours=12),
                {"vv": to_linear(vv_db), "vh": to_linear(vh_db)},
                grid,
                meta={"source_scenes": int(n_s1)},
            )
        )
    write_manifest(out, records)
    sys.stdout.write(f"wrote {len(records)} local scenes to {out}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "../data"))
