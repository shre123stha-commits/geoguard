"""Phase 9.6 — seasonal-model scan mode end to end through ScanRunner (needs PostGIS)."""

import math
import uuid
from datetime import UTC, date, datetime

import numpy as np
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.enums import ConfidenceClass, ScanStatus
from app.pipeline.sources.base import SceneRef
from app.repositories import DetectionRepository, ParcelRepository, ScanRepository
from app.services.scan_runner import ScanFailedError, ScanRunner

from .conftest import ADMIN

ONSET = date(2023, 4, 1)


class SeasonalSource:
    """One S2 + one S1 scene per month over any grid; a block in the grid centre (~100 m × 100 m)
    turns built from ONSET on. Vegetation and backscatter follow a yearly cycle."""

    def search_optical(self, bbox, rng, cloud_max):  # type: ignore[no-untyped-def]
        m = rng[0]
        return [
            SceneRef(f"s2-{m:%Y-%m}", "sentinel2", datetime(m.year, m.month, 10, tzinfo=UTC), 5.0)
        ]

    def search_radar(self, bbox, rng):  # type: ignore[no-untyped-def]
        m = rng[0]
        return [SceneRef(f"s1-{m:%Y-%m}", "sentinel1", datetime(m.year, m.month, 12, tzinfo=UTC))]

    def read_grid(self, scene, bands, grid):  # type: ignore[no-untyped-def]
        h, w = grid.shape
        blk = (slice(h // 2 - 5, h // 2 + 5), slice(w // 2 - 5, w // 2 + 5))
        m = date(scene.acquired_at.year, scene.acquired_at.month, 1)
        phase = 2 * math.pi * (m.month - 1) / 12
        veg = 0.5 + 0.2 * math.cos(phase - 0.8)
        built = m >= ONSET
        if scene.sensor == "sentinel2":
            red = np.full((h, w), 0.08, np.float32)
            nir = np.full((h, w), 0.10 + 0.35 * veg, np.float32)
            swir = np.full((h, w), 0.12, np.float32)
            scl = np.full((h, w), 4.0, np.float32)
            if built:
                red[blk], nir[blk], swir[blk] = 0.20, 0.22, 0.30
            return np.concatenate([np.stack([red, nir, swir]) * 10000, scl[None]]).astype(
                np.float32
            )
        vv_db = np.full((h, w), -12.0 + math.cos(phase), np.float32)
        if built:
            vv_db[blk] += 4.0
        lin = 10 ** (vv_db / 10)
        return np.stack([lin, lin * 0.3]).astype(np.float32)


def _queue(db: Session, pid: str, **params) -> uuid.UUID:  # type: ignore[no-untyped-def]
    parcel = ParcelRepository(db).get(uuid.UUID(pid))
    assert parcel is not None
    scan = ScanRepository(db).create(
        [parcel],
        (date(2021, 1, 1), date(2022, 12, 31)),
        (date(2023, 1, 1), date(2023, 12, 31)),
        {"mode": "seasonal", "persist": 3, **params},
        "idx-fusion-1.0.0",
    )
    db.flush()
    return scan.id


def test_seasonal_scan_dates_the_onset(
    seeded: tuple[TestClient, Session, str], settings: Settings
) -> None:
    _, db, pid = seeded
    scan = ScanRepository(db).get(_queue(db, pid))
    assert scan is not None
    runner = ScanRunner(db, settings, source_factory=lambda _s: SeasonalSource())
    res = runner.run(scan)

    assert scan.status == ScanStatus.succeeded and scan.progress == 100
    assert scan.params["months"] == {
        "total": 36,
        "reference": 24,
        "with_optical": 36,
        "with_radar": 36,
    }
    assert "seasonal model" in (scan.message or "")
    assert len(scan.scenes) == 36  # one monthly-composite row per month
    dets = DetectionRepository(db).list_all(scan_id=scan.id)
    assert res.detections == len(dets) == 1
    d = dets[0]
    assert d.onset_month == ONSET
    assert d.confidence == ConfidenceClass.high and d.optical_detected and d.radar_detected
    assert 8_000 < d.area_m2 < 12_500
    assert d.d_sigma_vv_mean is not None and d.d_sigma_vv_mean > 3
    ev = DetectionRepository(db).evidence_for(d)
    assert {e.kind.value for e in ev} == {"before_rgb", "after_rgb", "change_map"}
    # monthly cache was written and is keyed by grid
    assert len(list((settings.data_dir / "cache" / "monthly").rglob("*.npz"))) == 36

    # API surfaces the onset month
    client = seeded[0]
    r = client.post("/api/v1/auth/login", json={"email": ADMIN[0], "password": ADMIN[1]})
    hdr = {"Authorization": f"Bearer {r.json()['access_token']}"}
    body = client.get(f"/api/v1/detections/{d.id}", headers=hdr).json()
    assert body["properties"]["onset_month"] == "2023-04-01"


def test_seasonal_api_rejects_short_reference(
    seeded: tuple[TestClient, Session, str],
) -> None:
    client, _, pid = seeded
    r = client.post("/api/v1/auth/login", json={"email": ADMIN[0], "password": ADMIN[1]})
    hdr = {"Authorization": f"Bearer {r.json()['access_token']}"}
    r = client.post(
        "/api/v1/scans",
        json={
            "parcel_ids": [pid],
            "baseline_start": "2022-06-01",
            "baseline_end": "2022-12-31",
            "current_start": "2023-01-01",
            "current_end": "2023-06-30",
            "params": {"mode": "seasonal"},
        },
        headers=hdr,
    )
    assert r.status_code == 422 and "12 months" in r.text


def test_seasonal_runner_fails_cleanly_on_short_current(
    seeded: tuple[TestClient, Session, str], settings: Settings
) -> None:
    _, db, pid = seeded
    parcel = ParcelRepository(db).get(uuid.UUID(pid))
    assert parcel is not None
    scan = ScanRepository(db).create(
        [parcel],
        (date(2021, 1, 1), date(2022, 12, 31)),
        (date(2023, 1, 1), date(2023, 1, 31)),
        {"mode": "seasonal", "persist": 3},
        "idx-fusion-1.0.0",
    )
    db.flush()
    try:
        ScanRunner(db, settings, source_factory=lambda _s: SeasonalSource()).run(scan)
    except ScanFailedError as exc:
        assert exc.code == "short_current"
    else:  # pragma: no cover
        raise AssertionError("expected ScanFailedError")
    assert scan.status == ScanStatus.failed and scan.error_code == "short_current"
