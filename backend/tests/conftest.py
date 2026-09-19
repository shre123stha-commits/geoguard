"""Shared fixtures. Integration tests need a reachable `geoguard_test` PostGIS database
(Settings.test_database_url / TEST_DATABASE_URL); otherwise they are skipped, so the
offline unit suite always runs (docs/08-rules.md: unit tests never touch the network)."""

import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.config import Settings

BACKEND = Path(__file__).resolve().parents[1]


def _test_url() -> str:
    return Settings().test_database_url


@pytest.fixture(scope="session")
def pg_engine():  # type: ignore[no-untyped-def]
    url = _test_url()
    try:
        engine = create_engine(url, pool_pre_ping=True)
        with engine.connect() as c:
            c.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        pytest.skip(
            f"geoguard_test not reachable ({exc.__class__.__name__}); integration tests skipped"
        )
    # migrate to head via the real Alembic scripts (DATABASE_URL points Alembic at the test DB)
    import os

    env = {**os.environ, "DATABASE_URL": url}
    for cmd in (["downgrade", "base"], ["upgrade", "head"]):
        r = subprocess.run(
            [sys.executable, "-m", "alembic", *cmd],
            cwd=BACKEND,
            env=env,
            capture_output=True,
            text=True,
        )
        assert r.returncode == 0, r.stderr
    yield engine
    engine.dispose()


@pytest.fixture
def db(pg_engine) -> Iterator[Session]:  # type: ignore[no-untyped-def]
    """One transaction per test, rolled back at the end (fast, isolated)."""
    conn = pg_engine.connect()
    tx = conn.begin()
    session = Session(bind=conn, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        tx.rollback()
        conn.close()
