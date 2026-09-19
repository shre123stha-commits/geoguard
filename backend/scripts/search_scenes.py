"""Task 1.2: print S2/S1 scene lists for the sample parcels and windows (needs internet).

Usage: python scripts/search_scenes.py ../data/samples/parcels.geojson ../data/samples/windows.json
"""

import json
import logging
import sys
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(
    0, str(Path(__file__).resolve().parents[1])
)  # allow running without `pip install -e .`

from app.core.config import get_settings  # noqa: E402
from app.core.logging import setup_logging  # noqa: E402
from app.pipeline.aoi import build_aoi  # noqa: E402
from app.pipeline.sources.base import DateRange, ImageryError, SceneRef  # noqa: E402
from app.pipeline.sources.planetary_computer import PlanetaryComputerSource  # noqa: E402

log = logging.getLogger("search_scenes")


def _range(pair: list[str]) -> DateRange:
    return date.fromisoformat(pair[0]), date.fromisoformat(pair[1])


def _print(title: str, scenes: list[SceneRef]) -> None:
    log.info("%s: %d scenes", title, len(scenes))
    for s in scenes:
        extra = (
            f"cloud={s.cloud_cover:5.1f}%  tile={s.meta.get('tile')}"
            if s.sensor == "sentinel2"
            else f"orbit={s.orbit_direction} rel_orbit={s.relative_orbit}"
        )
        log.info("  %s  %s  %s", s.acquired_at.date(), extra, s.scene_id)


def main(parcels_path: str, windows_path: str) -> int:
    settings = get_settings()
    setup_logging(settings.log_level)
    parcels = json.loads(Path(parcels_path).read_text(encoding="utf-8"))["features"]
    windows = json.loads(Path(windows_path).read_text(encoding="utf-8"))
    aoi = build_aoi(parcels)
    log.info("AOI bbox=%s utm=EPSG:%d area=%.2f km2", aoi.bbox_wgs84, aoi.epsg_utm, aoi.area_km2)

    src = PlanetaryComputerSource(settings.stac_api_url)
    ok = True
    for period in ("baseline", "current"):
        rng = _range(windows[period])
        try:
            s2 = src.search_optical(aoi.bbox_wgs84, rng, settings.cloud_cover_max)
            s1 = src.search_radar(aoi.bbox_wgs84, rng)
        except ImageryError as exc:
            log.error("%s: %s", period, exc)
            return 2
        _print(f"{period} S2 L2A (cloud<={settings.cloud_cover_max})", s2)
        _print(f"{period} S1 RTC", s1)
        orbits = Counter((s.orbit_direction, s.relative_orbit) for s in s1)
        log.info("%s S1 orbits: %s", period, dict(orbits))
        if not s2 or not s1:
            ok = False
            log.warning(
                "%s has no %s scenes; widen the window or raise cloud limit",
                period,
                "S2" if not s2 else "S1",
            )
    return 0 if ok else 1


if __name__ == "__main__":
    if len(sys.argv) != 3:
        log.error("usage: search_scenes.py PARCELS.geojson WINDOWS.json")
        sys.exit(64)
    sys.exit(main(sys.argv[1], sys.argv[2]))
