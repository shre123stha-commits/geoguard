"""Per-parcel change timeline (Phase 9.3).

For every calendar month in a range, build a Sentinel-2 median composite over the parcel and
record the share of parcel pixels whose *absolute* built-up index (BUI = NDBI − NDVI) is at or
above `t_bui` (default 0.0: more built/bare than green — note this is NOT the scan's Δ-BUI
threshold, which is a change threshold), plus mean
NDVI and how much of the parcel was cloud-free. A rising `built_frac` step shows *when* a
change began — something the two-window scan cannot tell you (README limitation 4).

Runs in a daemon thread per parcel; progress is stored in `timeline_jobs`. Months already
computed with the same `t_bui` are skipped, so re-running only fills gaps / new months.
Monsoon months with no clear scene are stored with `n_scenes = 0` and null values so the chart
shows a gap rather than a false zero.
"""

import logging
import threading
import uuid
from calendar import monthrange
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

import numpy as np
from rasterio.features import rasterize
from shapely.geometry import shape
from shapely.ops import transform as shp_transform
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.db.models import Parcel, ParcelTimeseries, TimelineJob
from app.pipeline.aoi import build_aoi
from app.pipeline.composite import build_optical_composite
from app.pipeline.grid import make_grid
from app.pipeline.optical import compute_indices
from app.pipeline.sources.base import GridReader, ImageryError
from app.repositories.base import from_db
from app.services.scan_runner import default_source_factory

logger = logging.getLogger(__name__)

SourceFactory = Callable[[Settings], GridReader]
MAX_MONTHS = 72
DEFAULT_MONTHS = 36
DEFAULT_T_BUI = 0.0  # absolute BUI (NDBI − NDVI) cut: ≥ 0 means more built/bare than green
CLOUD_MAX = 60  # per-scene cloud cover; SCL masking does the rest
MIN_VALID_FRAC = 0.2  # below this the month is reported as "no clear view"

_lock = threading.Lock()
_running: dict[uuid.UUID, threading.Thread] = {}


@dataclass(frozen=True)
class MonthStat:
    month: date
    built_frac: float | None
    ndvi_mean: float | None
    valid_frac: float | None
    n_scenes: int


def month_range(end: date, months: int) -> list[date]:
    """`months` first-of-month dates ending with the month of `end` (oldest first)."""
    y, m = end.year, end.month
    out: list[date] = []
    for _ in range(months):
        out.append(date(y, m, 1))
        m -= 1
        if m == 0:
            m, y = 12, y - 1
    return list(reversed(out))


def compute_month(
    src: GridReader, parcel_geojson: dict[str, Any], month: date, t_bui: float
) -> MonthStat:
    """One month for one parcel: median composite → BUI/NDVI → parcel statistics."""
    aoi = build_aoi([{"geometry": parcel_geojson, "properties": {"name": "p"}}])
    grid = make_grid(aoi.bbox_utm, aoi.epsg_utm)
    last = monthrange(month.year, month.month)[1]
    rng = (month, date(month.year, month.month, last))
    scenes = src.search_optical(aoi.bbox_wgs84, rng, CLOUD_MAX)
    if not scenes:
        return MonthStat(month, None, None, 0.0, 0)
    try:
        comp = build_optical_composite(src, scenes, grid)
    except ImageryError:
        return MonthStat(month, None, None, 0.0, len(scenes))
    from pyproj import Transformer

    to_utm = Transformer.from_crs(4326, aoi.epsg_utm, always_xy=True).transform
    poly = shp_transform(to_utm, shape(parcel_geojson))
    pmask = rasterize([(poly, 1)], out_shape=grid.shape, transform=grid.transform).astype(bool)
    if not pmask.any():
        return MonthStat(month, None, None, 0.0, len(scenes))
    idx = compute_indices(*comp.bands)
    bui = idx.bui[pmask]
    ndvi = idx.ndvi[pmask]
    ok = np.isfinite(bui) & np.isfinite(ndvi)
    valid_frac = float(ok.mean())
    if valid_frac < MIN_VALID_FRAC:
        return MonthStat(month, None, None, valid_frac, len(scenes))
    return MonthStat(
        month,
        float((bui[ok] >= t_bui).mean()),
        float(ndvi[ok].mean()),
        valid_frac,
        len(scenes),
    )


def _months_todo(db: Session, parcel_id: uuid.UUID, months: list[date], t_bui: float) -> list[date]:
    done = set(
        db.scalars(
            select(ParcelTimeseries.month).where(
                ParcelTimeseries.parcel_id == parcel_id,
                func.abs(ParcelTimeseries.t_bui - t_bui) < 1e-4,
                ParcelTimeseries.n_scenes > 0,  # empty months are retried (new scenes may land)
            )
        )
    )
    return [m for m in months if m not in done]


def start(
    session_factory: sessionmaker[Session],
    settings: Settings,
    parcel_id: uuid.UUID,
    months: int = DEFAULT_MONTHS,
    t_bui: float = DEFAULT_T_BUI,
    source_factory: SourceFactory = default_source_factory,
    end: date | None = None,
    block: bool = False,
) -> bool:
    """Start (or, with block=True, run inline) the timeline job. False if already running."""
    with _lock:
        t = _running.get(parcel_id)
        if t is not None and t.is_alive():
            return False
        th = threading.Thread(
            target=_run,
            args=(session_factory, settings, parcel_id, months, t_bui, source_factory, end),
            name=f"timeline-{str(parcel_id)[:8]}",
            daemon=True,
        )
        _running[parcel_id] = th
    if block:
        th.run()
    else:
        th.start()
    return True


def is_running(parcel_id: uuid.UUID) -> bool:
    t = _running.get(parcel_id)
    return t is not None and t.is_alive()


def _run(
    session_factory: sessionmaker[Session],
    settings: Settings,
    parcel_id: uuid.UUID,
    months: int,
    t_bui: float,
    source_factory: SourceFactory,
    end: date | None,
) -> None:
    months = max(1, min(MAX_MONTHS, months))
    wanted = month_range(end or date.today(), months)
    with session_factory() as db:
        parcel = db.get(Parcel, parcel_id)
        if parcel is None:
            return
        geojson = from_db(parcel.geom) or {}
        todo = _months_todo(db, parcel_id, wanted, t_bui)
        job = db.get(TimelineJob, parcel_id) or TimelineJob(parcel_id=parcel_id, status="running")
        job.status = "running"
        job.progress = 0
        job.months_total = len(todo)
        job.months_done = 0
        job.message = f"{len(todo)} month(s) to compute" if todo else "up to date"
        job.started_at = datetime.now(UTC)
        job.finished_at = None
        db.merge(job)
        db.commit()
        try:
            src = source_factory(settings)
            for i, m in enumerate(todo):
                stat = compute_month(src, geojson, m, t_bui)
                db.merge(
                    ParcelTimeseries(
                        parcel_id=parcel_id,
                        month=m,
                        built_frac=stat.built_frac,
                        ndvi_mean=stat.ndvi_mean,
                        valid_frac=stat.valid_frac,
                        n_scenes=stat.n_scenes,
                        t_bui=t_bui,
                        computed_at=datetime.now(UTC),
                    )
                )
                job = db.get(TimelineJob, parcel_id) or job
                job.months_done = i + 1
                job.progress = int(100 * (i + 1) / max(1, len(todo)))
                job.message = f"{m.strftime('%b %Y')}: {stat.n_scenes} scene(s)"
                db.commit()
            job = db.get(TimelineJob, parcel_id) or job
            job.status = "done"
            job.progress = 100
            job.message = f"{len(todo)} month(s) computed"
            job.finished_at = datetime.now(UTC)
            db.commit()
        except Exception as exc:  # noqa: BLE001 - recorded on the job row
            logger.exception("timeline failed", extra={"parcel_id": str(parcel_id)})
            db.rollback()
            job = db.get(TimelineJob, parcel_id) or job
            job.status = "failed"
            job.message = f"{exc.__class__.__name__}: {exc}"[:500]
            job.finished_at = datetime.now(UTC)
            db.merge(job)
            db.commit()


def onset(rows: list[ParcelTimeseries], min_jump: float = 0.10) -> date | None:
    """First month where built_frac exceeds the median of all earlier clear months by
    `min_jump` and stays above it for the next clear month too (a step, not a blip)."""
    clear = sorted(
        ((r.month, float(r.built_frac)) for r in rows if r.built_frac is not None),
        key=lambda x: x[0],
    )
    for i in range(2, len(clear) - 1):
        before = float(np.median([v for _, v in clear[:i]]))
        if clear[i][1] - before >= min_jump and clear[i + 1][1] - before >= min_jump:
            return clear[i][0]
    return None
