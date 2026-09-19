"""Repository integration tests on geoguard_test (skipped when the DB is unavailable)."""

import uuid
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.enums import (
    ConfidenceClass,
    DetectionStatus,
    PeriodType,
    ScanStatus,
    SensorType,
    UserRole,
)
from app.repositories import (
    DetectionRepository,
    ParcelInUseError,
    ParcelRepository,
    ScanRepository,
    ScheduleRepository,
    UserRepository,
)

# ~1 km x 1 km near Pallikaranai (lon/lat)
SQUARE = {
    "type": "Polygon",
    "coordinates": [
        [[80.19, 12.935], [80.2, 12.935], [80.2, 12.945], [80.19, 12.945], [80.19, 12.935]]
    ],
}
SMALL = {
    "type": "Polygon",
    "coordinates": [
        [[80.192, 12.937], [80.193, 12.937], [80.193, 12.938], [80.192, 12.938], [80.192, 12.937]]
    ],
}
BOWTIE = {"type": "Polygon", "coordinates": [[[0, 0], [1, 1], [1, 0], [0, 1], [0, 0]]]}


def test_migrations_created_all_tables(db: Session) -> None:
    names = set(db.scalars(text("SELECT tablename FROM pg_tables WHERE schemaname='public'")))
    expected = {
        "users", "parcels", "scans", "scan_parcels", "scan_scenes", "detections",
        "detection_status_history", "evidence_files", "reports", "alerts", "app_settings",
        "scan_schedules", "schedule_parcels", "alembic_version",
    }  # fmt: skip
    assert expected <= names
    assert db.scalar(text("SELECT postgis_version()"))


def test_users_create_lookup_and_admin_count(db: Session) -> None:
    repo = UserRepository(db)
    u = repo.create("Admin@Example.com", "Admin", "correct-horse-battery", UserRole.admin, True)
    assert u.email == "admin@example.com" and u.must_change_password
    assert u.password_hash.startswith("$argon2")
    assert repo.get_by_email("ADMIN@example.com") is not None
    assert repo.count_active_admins() == 1
    with pytest.raises(ValueError):
        repo.create("x@example.com", "X", "short")


def test_parcel_area_is_geodesic_and_invalid_rejected(db: Session) -> None:
    repo = ParcelRepository(db)
    p = repo.create("Square", "wetland", SQUARE)
    # 0.01° lon × 0.01° lat at 12.94° N ≈ 1.084 km × 1.106 km ≈ 1.2 km²
    assert 1.15e6 < p.area_m2 < 1.25e6
    assert p.source == "upload"
    with pytest.raises(ValueError):
        repo.create("Bad", "x", BOWTIE)
    assert [x.id for x in repo.intersecting(SMALL)] == [p.id]


def test_scan_detection_status_history_and_delete_rules(db: Session) -> None:
    users, parcels, scans, dets = (
        UserRepository(db), ParcelRepository(db), ScanRepository(db), DetectionRepository(db),
    )  # fmt: skip
    officer = users.create("o@example.com", "Officer", "officer-pass-123")
    parcel = parcels.create("West-1", "wetland", SQUARE)
    scan = scans.create(
        [parcel],
        (date(2020, 1, 15), date(2020, 3, 31)),
        (date(2023, 1, 15), date(2023, 3, 31)),
        {"t_bui": 0.15},
        "idx-fusion-1.0.0",
        created_by=officer.id,
    )
    assert scan.status == ScanStatus.queued and scans.parcel_ids(scan) == [parcel.id]
    scans.set_progress(scan, "search", 10)
    assert scan.status == ScanStatus.running and scan.started_at is not None
    scans.add_scene(
        scan,
        SensorType.sentinel2,
        PeriodType.baseline,
        "S2A_X",
        datetime(2020, 2, 1, tzinfo=UTC),
        3.0,
    )

    d = dets.create(
        scan, parcel, SMALL, 12000.0, ConfidenceClass.high, 0.49, True, True, sar_overlap=1.0
    )
    assert d.status == DetectionStatus.new
    assert dets.count(parcel_id=parcel.id) == 1
    assert dets.count(confidence=ConfidenceClass.low) == 0
    assert dets.count(bbox=(80.19, 12.93, 80.2, 12.95)) == 1
    assert dets.count(bbox=(81.0, 13.0, 81.1, 13.1)) == 0

    with pytest.raises(ValueError):
        dets.set_status(d, DetectionStatus.dismissed, officer.id, note="")
    h = dets.set_status(d, DetectionStatus.confirmed, officer.id, note="seen on Wayback")
    assert h.from_status == DetectionStatus.new and d.status == DetectionStatus.confirmed
    db.refresh(d)
    assert len(d.history) == 1

    # parcel delete is blocked while referenced; cascade removes scan + detections
    with pytest.raises(ParcelInUseError):
        parcels.delete(parcel)
    parcels.delete(parcel, cascade=True)
    assert scans.get(scan.id) is None and dets.get(d.id) is None

    scans.finish(scan, ScanStatus.failed, "no scenes", "no_scenes") if scans.get(scan.id) else None


def test_previous_match_uses_50_percent_overlap(db: Session) -> None:
    parcels, scans, dets = ParcelRepository(db), ScanRepository(db), DetectionRepository(db)
    parcel = parcels.create("P", "wetland", SQUARE)
    periods = ((date(2020, 1, 1), date(2020, 3, 1)), (date(2023, 1, 1), date(2023, 3, 1)))
    s1 = scans.create([parcel], *periods, {}, "v")
    old = dets.create(s1, parcel, SMALL, 12000.0, ConfidenceClass.medium, 0.3, True, False)
    db.execute(
        text("UPDATE detections SET created_at = now() - interval '1 day' WHERE id = :i"),
        {"i": old.id},
    )
    s2 = scans.create([parcel], *periods, {}, "v")
    new = dets.create(s2, parcel, SMALL, 12000.0, ConfidenceClass.high, 0.5, True, True)
    db.expire_all()
    assert dets.find_previous_match(dets.get(new.id)).id == old.id  # type: ignore[union-attr]


def test_schedules(db: Session) -> None:
    parcels, sched = ParcelRepository(db), ScheduleRepository(db)
    p = parcels.create("P", "wetland", SQUARE)
    s = sched.create("weekly", "0 2 * * 1", [p], {"t_bui": 0.15})
    assert s.is_active and s.baseline_rule["mode"] == "same_season_previous_year"
    assert len(s.parcels) == 1
    sched.set_active(s, False)
    assert sched.list_all(active_only=True) == []
    with pytest.raises(ValueError):
        sched.create("empty", "* * * * *", [], {})
    assert isinstance(s.id, uuid.UUID)
