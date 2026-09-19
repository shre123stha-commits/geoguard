"""Phase 4: scans API (4.1), worker (4.2), pipeline-in-DB (4.3), evidence (4.4), offline
source (4.5). Integration tests on geoguard_test; skipped without a DB."""

import uuid
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.enums import ConfidenceClass, ScanStatus
from app.pipeline.aoi import build_aoi
from app.pipeline.grid import make_grid
from app.pipeline.sources.local_folder import LocalFolderSource
from app.repositories import DetectionRepository, ParcelRepository, ScanRepository
from app.services.scan_runner import ScanFailedError, ScanRunner
from app.services.worker import ScanWorker
from tests.integration.conftest import ADMIN, OFFICER, PARCEL, Login, make_local_scenes

BASE = {"baseline_start": "2020-01-15", "baseline_end": "2020-03-31"}
CUR = {"current_start": "2023-01-15", "current_end": "2023-03-31"}


def test_local_folder_source_roundtrip(tmp_path: Path) -> None:
    root = make_local_scenes(tmp_path / "scenes", PARCEL)
    src = LocalFolderSource(root)
    aoi = build_aoi([{"geometry": PARCEL, "properties": {"name": "p"}}])
    from datetime import date

    s2 = src.search_optical(aoi.bbox_wgs84, (date(2020, 1, 1), date(2020, 3, 31)), 30)
    s1 = src.search_radar(aoi.bbox_wgs84, (date(2023, 1, 1), date(2023, 3, 31)))
    assert [s.scene_id for s in s2] == ["S2_baseline_0", "S2_baseline_1"]
    assert [s.scene_id for s in s1] == ["S1_current_0", "S1_current_1"]
    assert src.search_optical(aoi.bbox_wgs84, (date(2020, 1, 1), date(2020, 3, 31)), 1) == []
    assert src.search_optical((0, 0, 1, 1), (date(2020, 1, 1), date(2020, 3, 31)), 30) == []
    grid = make_grid(aoi.bbox_utm, aoi.epsg_utm)
    arr = src.read_grid(s2[0], ["B04", "B08", "SCL"], grid)
    assert arr.shape == (3, *grid.shape)
    assert 450 < np.nanmedian(arr[0]) < 550 and np.nanmedian(arr[2]) == 4


# ---------- 4.1 scans API ----------


def test_scan_create_validation_and_roles(
    seeded: tuple[TestClient, Session, str], login: Login
) -> None:
    client, _, pid = seeded
    adm, off = login(*ADMIN), login(*OFFICER)
    body = {"parcel_ids": [pid], **BASE, **CUR}
    assert client.post("/api/v1/scans", json=body, headers=off).status_code == 403

    bad = {**body, "baseline_end": "2023-02-01"}  # overlaps current
    r = client.post("/api/v1/scans", json=bad, headers=adm)
    assert r.status_code == 422 and "baseline period must end" in r.text
    short = {**body, "current_end": "2023-01-16"}
    assert client.post("/api/v1/scans", json=short, headers=adm).status_code == 422
    unknown = {**body, "parcel_ids": [str(uuid.uuid4())]}
    assert client.post("/api/v1/scans", json=unknown, headers=adm).status_code == 404
    weird = {**body, "params": {"t_bui": 5}}
    assert client.post("/api/v1/scans", json=weird, headers=adm).status_code == 422

    r = client.post("/api/v1/scans", json=body, headers=adm)
    assert r.status_code == 201, r.text
    s = r.json()
    assert s["status"] == "queued" and s["progress"] == 0
    assert s["params"]["t_bui"] == 0.15 and s["algorithm_version"].startswith("idx-fusion")
    assert s["parcels"][0]["id"] == pid and s["detection_count"] == 0

    lst = client.get("/api/v1/scans", headers=off).json()
    assert lst["total"] == 1 and lst["items"][0]["id"] == s["id"]
    assert client.get("/api/v1/scans?status=failed", headers=off).json()["total"] == 0
    assert client.get(f"/api/v1/scans/{s['id']}", headers=off).status_code == 200
    assert client.get(f"/api/v1/scans/{uuid.uuid4()}", headers=off).status_code == 404

    # rerun refused while queued; cancel works once; second cancel 409
    assert client.post(f"/api/v1/scans/{s['id']}/rerun", headers=adm).status_code == 409
    c = client.post(f"/api/v1/scans/{s['id']}/cancel", headers=adm)
    assert c.status_code == 200 and c.json()["status"] == "cancelled"
    assert client.post(f"/api/v1/scans/{s['id']}/cancel", headers=adm).status_code == 409
    # rerun of a cancelled scan creates a fresh queued one
    rr = client.post(f"/api/v1/scans/{s['id']}/rerun", headers=adm)
    assert rr.status_code == 201 and rr.json()["rerun_of"] == s["id"]
    # delete needs confirm
    assert client.delete(f"/api/v1/scans/{s['id']}", headers=adm).status_code == 409
    assert client.delete(f"/api/v1/scans/{s['id']}?confirm=true", headers=adm).status_code == 204
    assert client.get(f"/api/v1/scans/{s['id']}", headers=adm).status_code == 404


# ---------- 4.2–4.5 runner + worker ----------


def _queue(db: Session, pid: str, **params: float) -> uuid.UUID:
    from datetime import date

    parcel = ParcelRepository(db).get(uuid.UUID(pid))
    assert parcel is not None
    scan = ScanRepository(db).create(
        [parcel],
        (date(2020, 1, 15), date(2020, 3, 31)),
        (date(2023, 1, 15), date(2023, 3, 31)),
        {"t_bui": 0.15, "t_sar_db": 2.5, "overlap": 0.3, **params},
        "idx-fusion-1.0.0",
    )
    db.flush()
    return scan.id


def test_runner_produces_detections_and_evidence(
    seeded: tuple[TestClient, Session, str], settings: Settings
) -> None:
    _, db, pid = seeded
    scans = ScanRepository(db)
    scan_id = _queue(db, pid)
    scan = scans.get(scan_id)
    assert scan is not None
    result = ScanRunner(db, settings).run(scan)

    assert scan.status == ScanStatus.succeeded and scan.progress == 100
    assert scan.aoi_geom is not None and scan.step == "persist"
    assert result.scenes == 8 and len(scan.scenes) == 8
    assert {s.sensor.value for s in scan.scenes} == {"sentinel1", "sentinel2"}

    dets = DetectionRepository(db).list_all(scan_id=scan_id)
    assert result.detections == len(dets) == 1
    d = dets[0]
    assert d.confidence == ConfidenceClass.high and d.optical_detected and d.radar_detected
    assert 8_000 < d.area_m2 < 12_500  # 100 m x 100 m block (+/- pixel edges)
    assert d.d_bui_mean is not None and d.d_bui_mean > 0.3
    assert d.d_sigma_vv_mean is not None and d.d_sigma_vv_mean > 4
    assert d.sar_overlap is not None and d.sar_overlap > 0.9
    assert d.parcel_id == uuid.UUID(pid) and d.matches_detection is None
    assert "1 detection" in (scan.message or "")

    ev = DetectionRepository(db).evidence_for(d)
    assert {e.kind.value for e in ev} == {"before_rgb", "after_rgb", "change_map"}
    for e in ev:
        p = settings.data_dir / e.path
        assert p.exists() and p.stat().st_size > 200 and e.path.startswith("evidence/")
        assert e.width_px and e.height_px and e.bounds is not None

    # a second run on the same site links back to the first detection (schema 05 §6)
    scan2 = scans.get(_queue(db, pid))
    assert scan2 is not None
    ScanRunner(db, settings).run(scan2)
    d2 = DetectionRepository(db).list_all(scan_id=scan2.id)[0]
    assert d2.matches_detection == d.id


def test_runner_no_change_yields_no_detections(
    seeded: tuple[TestClient, Session, str], settings: Settings
) -> None:
    _, db, pid = seeded
    make_local_scenes(settings.data_dir / "local_scenes", PARCEL, built_block=False)
    scan = ScanRepository(db).get(_queue(db, pid))
    assert scan is not None
    res = ScanRunner(db, settings).run(scan)
    assert res.detections == 0 and scan.status == ScanStatus.succeeded
    assert scan.message == "0 detections in 1 parcel(s)"


def test_runner_fails_cleanly_without_scenes(
    seeded: tuple[TestClient, Session, str], settings: Settings
) -> None:
    _, db, pid = seeded
    from datetime import date

    parcel = ParcelRepository(db).get(uuid.UUID(pid))
    assert parcel is not None
    scan = ScanRepository(db).create(
        [parcel], (date(2019, 1, 1), date(2019, 3, 1)), (date(2023, 1, 15), date(2023, 3, 31)),
        {}, "idx-fusion-1.0.0",
    )  # fmt: skip
    db.flush()
    with pytest.raises(ScanFailedError) as exc:
        ScanRunner(db, settings).run(scan)
    assert exc.value.code == "no_optical_scenes"
    db.refresh(scan)
    assert scan.status == ScanStatus.failed and scan.error_code == "no_optical_scenes"
    assert "2019-01-01..2019-03-01" in (scan.message or "")


def test_season_warning_recorded(
    seeded: tuple[TestClient, Session, str], settings: Settings
) -> None:
    _, db, pid = seeded
    from datetime import date

    parcel = ParcelRepository(db).get(uuid.UUID(pid))
    assert parcel is not None
    scan = ScanRepository(db).create(
        [parcel], (date(2020, 1, 15), date(2020, 3, 31)), (date(2023, 7, 1), date(2023, 9, 30)),
        {}, "idx-fusion-1.0.0",
    )  # fmt: skip
    db.flush()
    with pytest.raises(ScanFailedError):  # no summer scenes in the fixture, fine
        ScanRunner(db, settings).run(scan)
    db.refresh(scan)
    assert any("seasonal" in w for w in scan.params.get("warnings", []))


def test_worker_claims_runs_and_recovers(
    pg_engine: object, settings: Settings, tmp_path: Path
) -> None:
    """The worker uses its own sessions, so this test commits real rows and cleans up after."""
    from sqlalchemy import text
    from sqlalchemy.orm import sessionmaker

    factory = sessionmaker(bind=pg_engine, expire_on_commit=False)  # type: ignore[call-overload]
    make_local_scenes(settings.data_dir / "local_scenes", PARCEL)
    worker = ScanWorker(factory, settings, poll_seconds=0.1, stale_after=timedelta(hours=1))
    try:
        with factory() as s:
            pid = str(ParcelRepository(s).create("Worker parcel", "wetland", PARCEL).id)
            scan_id = _queue(s, pid)
            # a stale "running" scan from a previous crash
            stale = ScanRepository(s).get(_queue(s, pid))
            assert stale is not None
            stale.status = ScanStatus.running
            stale.started_at = datetime.now(UTC) - timedelta(hours=3)
            stale_id = stale.id
            s.commit()

        assert worker.recover() == 1
        assert worker.run_once() is True
        assert worker.run_once() is False  # nothing left

        with factory() as s:
            done = ScanRepository(s).get(scan_id)
            assert done is not None and done.status == ScanStatus.succeeded
            assert DetectionRepository(s).count(scan_id=scan_id) == 1
            st = ScanRepository(s).get(stale_id)
            assert st is not None and st.error_code == "worker_restart"
    finally:
        with factory() as s:
            for tbl in ("detections", "scan_scenes", "scan_parcels", "scans", "parcels"):
                s.execute(text(f"DELETE FROM {tbl}"))
            s.commit()


def test_scan_end_to_end_via_api(
    seeded: tuple[TestClient, Session, str], settings: Settings, login: Login
) -> None:
    client, db, pid = seeded
    adm = login(*ADMIN)
    r = client.post("/api/v1/scans", json={"parcel_ids": [pid], **BASE, **CUR}, headers=adm)
    scan_id = r.json()["id"]
    scan = ScanRepository(db).get(uuid.UUID(scan_id))
    assert scan is not None
    ScanRunner(db, settings).run(scan)  # what the worker thread does in production
    detail = client.get(f"/api/v1/scans/{scan_id}", headers=adm).json()
    assert detail["status"] == "succeeded" and detail["detection_count"] == 1
    assert len(detail["scenes"]) == 8 and detail["aoi"]["type"] == "Polygon"
    assert detail["progress"] == 100 and "1 detection" in detail["message"]


# ---------- 4.6 schedules ----------


def test_schedules_api_and_tick(seeded: tuple[TestClient, Session, str], login: Login) -> None:
    from app.repositories import ScheduleRepository
    from app.services.scheduler import fire_schedule

    client, db, pid = seeded
    adm, off = login(*ADMIN), login(*OFFICER)
    body = {"name": "Weekly marsh check", "parcel_ids": [pid], "cron": "weekly"}
    assert client.post("/api/v1/schedules", json=body, headers=off).status_code == 403
    bad = {**body, "cron": "every tuesday"}
    assert client.post("/api/v1/schedules", json=bad, headers=adm).status_code == 422
    fixed = {"mode": "fixed", "baseline_start": "2030-01-01", "baseline_end": "2030-02-01"}
    bad_rule = {**body, "baseline_rule": fixed}
    assert client.post("/api/v1/schedules", json=bad_rule, headers=adm).status_code == 422

    r = client.post("/api/v1/schedules", json=body, headers=adm)
    assert r.status_code == 201, r.text
    s = r.json()
    assert s["is_active"] and s["cron"] == "weekly" and s["next_run_at"] is not None
    assert s["parcels"][0]["id"] == pid and s["last_scan_id"] is None
    sid = s["id"]
    assert client.get("/api/v1/schedules", headers=adm).json()["total"] == 1

    # run now → queued scan tagged with the schedule, windows computed from today
    run = client.post(f"/api/v1/schedules/{sid}/run", headers=adm)
    assert run.status_code == 201, run.text
    scan = run.json()
    assert scan["schedule_id"] == sid and scan["status"] == "queued"
    cur_end = date.fromisoformat(scan["current_end"])
    assert cur_end == datetime.now(UTC).date()
    assert (cur_end - date.fromisoformat(scan["current_start"])).days == 29
    assert date.fromisoformat(scan["baseline_end"]).year == cur_end.year - 1
    # duplicate-queue guard
    assert client.post(f"/api/v1/schedules/{sid}/run", headers=adm).status_code == 409
    got = client.get(f"/api/v1/schedules/{sid}", headers=adm).json()
    assert got["last_scan_id"] == scan["id"] and got["last_scan_status"] == "queued"

    # pause + patch cron recomputes next_run_at
    p = client.patch(
        f"/api/v1/schedules/{sid}", json={"is_active": False, "cron": "monthly"}, headers=adm
    )
    assert p.status_code == 200 and p.json()["is_active"] is False and p.json()["cron"] == "monthly"

    # a due schedule fires once per tick and advances next_run_at
    sched = ScheduleRepository(db).get(uuid.UUID(sid))
    assert sched is not None
    client.post(f"/api/v1/scans/{scan['id']}/cancel", headers=adm)  # clear the open scan
    now = datetime.now(UTC)
    new_id = fire_schedule(db, sched, now)
    assert new_id is not None and sched.next_run_at is not None and sched.next_run_at > now
    assert sched.last_run_at == now

    # delete keeps past scans
    assert client.delete(f"/api/v1/schedules/{sid}", headers=adm).status_code == 204
    assert client.get(f"/api/v1/scans/{scan['id']}", headers=adm).json()["schedule_id"] is None
