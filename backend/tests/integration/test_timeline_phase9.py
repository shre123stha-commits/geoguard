"""Phase 9.3: per-parcel timeline over the synthetic local scenes (Feb 2020 vegetated,
Feb 2023 with a 100 m x 100 m built block inside a ~500 m parcel)."""

from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import ParcelTimeseries
from app.services import timeline
from app.services.scan_runner import default_source_factory
from tests.integration.conftest import OFFICER, Login

Seeded = tuple[TestClient, Session, str]


def test_timeline_end_to_end(seeded: Seeded, login: Login, settings: Settings) -> None:
    client, db, pid = seeded
    off = login(*OFFICER)
    import uuid

    parcel_id = uuid.UUID(pid)

    # Empty before anything runs
    r = client.get(f"/api/v1/parcels/{pid}/timeline", headers=off)
    assert r.status_code == 200 and r.json()["months"] == [] and r.json()["job"] is None

    # Compute months directly (no thread) so the test does not depend on timing.
    src = default_source_factory(settings)
    months = timeline.month_range(date(2023, 2, 1), 37)  # Feb 2020 .. Feb 2023
    for m in months:
        st = timeline.compute_month(src, _geojson(db, parcel_id), m, 0.0)
        db.merge(
            ParcelTimeseries(
                parcel_id=parcel_id,
                month=m,
                built_frac=st.built_frac,
                ndvi_mean=st.ndvi_mean,
                valid_frac=st.valid_frac,
                n_scenes=st.n_scenes,
                t_bui=0.0,
            )
        )
    db.flush()
    n = db.query(ParcelTimeseries).filter_by(parcel_id=parcel_id).count()
    assert n == 37, n

    body = client.get(f"/api/v1/parcels/{pid}/timeline", headers=off).json()
    by = {m["month"]: m for m in body["months"]}
    assert len(by) == 37
    feb20, feb23 = by["2020-02-01"], by["2023-02-01"]
    assert feb20["n_scenes"] == 2 and feb23["n_scenes"] == 2
    assert feb20["built_frac"] < 0.02  # vegetated
    # 100 m block in ~500 m parcel ≈ 4 % of pixels; allow generous bounds
    assert 0.02 < feb23["built_frac"] < 0.12, feb23
    assert feb23["ndvi_mean"] < feb20["ndvi_mean"]
    # months without scenes are gaps, not zeros
    assert by["2021-06-01"]["n_scenes"] == 0 and by["2021-06-01"]["built_frac"] is None
    assert body["onset_month"] is None  # only 2 clear months in total — too few for a step

    # POST starts a background job (officer allowed); second POST while running → 409 or fine
    r = client.post(f"/api/v1/parcels/{pid}/timeline", json={"months": 2}, headers=off)
    assert r.status_code == 202, r.text
    assert client.get(f"/api/v1/parcels/{pid}/timeline").status_code == 401


def _geojson(db: Session, parcel_id):  # type: ignore[no-untyped-def]
    from app.db.models import Parcel
    from app.repositories.base import from_db

    return from_db(db.get(Parcel, parcel_id).geom)  # type: ignore[union-attr]
