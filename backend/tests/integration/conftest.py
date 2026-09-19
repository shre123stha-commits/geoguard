"""Shared fixtures for the API-level integration tests (Phases 4–5): users, one parcel and
synthetic offline scenes with a 100 m x 100 m built block in the current period."""

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.enums import UserRole
from app.pipeline.aoi import build_aoi
from app.pipeline.grid import make_grid
from app.pipeline.sources.local_folder import write_manifest, write_scene
from app.repositories import ParcelRepository, UserRepository

ADMIN = ("admin@geoguard.test", "admin-password-1")
OFFICER = ("officer@geoguard.test", "officer-password-1")
# ~500 m x 500 m parcel near Pallikaranai
PARCEL = {
    "type": "Polygon",
    "coordinates": [
        [
            [80.190, 12.935],
            [80.1946, 12.935],
            [80.1946, 12.9395],
            [80.190, 12.9395],
            [80.190, 12.935],
        ]
    ],
}
Login = Callable[[str, str], dict[str, str]]


def make_local_scenes(root: Path, parcel_geojson: dict, built_block: bool = True) -> Path:  # type: ignore[type-arg]
    """Write 2 S2 + 2 S1 scenes per period. Current period has a 100 m x 100 m built block."""
    aoi = build_aoi([{"geometry": parcel_geojson, "properties": {"name": "p"}}])
    grid = make_grid(aoi.bbox_utm, aoi.epsg_utm)
    h, w = grid.shape
    rng = np.random.default_rng(0)

    def s2(built: bool) -> dict[str, np.ndarray]:
        # vegetation: red 0.05, nir 0.40, swir 0.15 (in DN x 10000 for PB < 04.00)
        red = np.full((h, w), 500.0) + rng.normal(0, 20, (h, w))
        nir = np.full((h, w), 4000.0) + rng.normal(0, 100, (h, w))
        swir = np.full((h, w), 1500.0) + rng.normal(0, 60, (h, w))
        scl = np.full((h, w), 4.0)  # vegetation class
        if built:
            r0, c0 = h // 2 - 5, w // 2 - 5
            red[r0 : r0 + 10, c0 : c0 + 10] = 2200
            nir[r0 : r0 + 10, c0 : c0 + 10] = 2600
            swir[r0 : r0 + 10, c0 : c0 + 10] = 3600
        return {"B04": red, "B08": nir, "B11": swir, "SCL": scl}

    def s1(built: bool) -> dict[str, np.ndarray]:
        vv = 10 ** (np.full((h, w), -12.0) / 10) * rng.lognormal(0, 0.15, (h, w))
        vh = 10 ** (np.full((h, w), -18.0) / 10) * rng.lognormal(0, 0.15, (h, w))
        if built:
            r0, c0 = h // 2 - 5, w // 2 - 5
            vv[r0 : r0 + 10, c0 : c0 + 10] *= 10 ** (6.0 / 10)  # +6 dB
        return {"vv": vv, "vh": vh}

    recs = []
    for period, (y, built) in {"baseline": (2020, False), "current": (2023, built_block)}.items():
        for k in range(2):
            t = datetime(y, 2, 1 + 10 * k, 5, 0, tzinfo=UTC)
            recs.append(
                write_scene(
                    root,
                    f"S2_{period}_{k}",
                    "sentinel2",
                    t,
                    s2(built),
                    grid,
                    cloud_cover=5.0,
                    meta={"processing_baseline": "02.14"},
                )  # fmt: skip
            )
            recs.append(write_scene(root, f"S1_{period}_{k}", "sentinel1", t, s1(built), grid))
    write_manifest(root, recs)
    return root


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        jwt_secret=SecretStr("test-secret-not-for-prod"),
        data_dir=tmp_path / "data",
        imagery_provider="local_folder",
        worker_enabled=False,
    )


@pytest.fixture
def seeded(api: tuple[TestClient, Session], settings: Settings) -> tuple[TestClient, Session, str]:
    client, db = api
    client.app.state.settings = settings  # type: ignore[attr-defined]
    urepo = UserRepository(db)
    urepo.create(ADMIN[0], "Admin", ADMIN[1], UserRole.admin)
    urepo.create(OFFICER[0], "Officer", OFFICER[1], UserRole.officer)
    parcel = ParcelRepository(db).create("Test parcel", "wetland", PARCEL)
    db.flush()
    make_local_scenes(settings.data_dir / "local_scenes", PARCEL)
    return client, db, str(parcel.id)


@pytest.fixture
def login(seeded: tuple[TestClient, Session, str]) -> Login:
    client = seeded[0]

    def _login(email: str, password: str) -> dict[str, str]:
        r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
        assert r.status_code == 200, r.text
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    return _login
