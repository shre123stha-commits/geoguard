"""Shared fixtures. Integration tests need a reachable `geoguard_test` PostGIS database
(Settings.test_database_url / TEST_DATABASE_URL); otherwise they are skipped, so the
offline unit suite always runs (docs/08-rules.md: unit tests never touch the network)."""

import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session

from app.core.config import Settings

BACKEND = Path(__file__).resolve().parents[1]


def _test_target() -> tuple[str, str | None]:
    """(url, schema). Schema mode is used when the test URL is the same database as the app
    URL (Supabase free tier has one database per project)."""
    st = Settings()
    same_db = st.test_database_url.split("?")[0] == st.database_url.split("?")[0]
    schema = st.test_database_schema or None if same_db else None
    return st.test_database_url, schema


@pytest.fixture(scope="session")
def pg_engine():  # type: ignore[no-untyped-def]
    url, schema = _test_target()
    try:
        engine = create_engine(url, pool_pre_ping=True)
        if schema:
            # Explicit SET on every new DBAPI connection. The psycopg `options=-csearch_path`
            # startup parameter is silently dropped by some poolers (Supabase/Supavisor), which
            # would make the tests hit the real `public` tables.
            @event.listens_for(engine, "connect")
            def _set_search_path(dbapi_conn, _record):  # type: ignore[no-untyped-def]
                cur = dbapi_conn.cursor()
                cur.execute(f'SET search_path TO "{schema}", public')
                cur.close()
                dbapi_conn.commit()

        with engine.connect() as c:
            c.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        pytest.skip(
            f"geoguard_test not reachable ({exc.__class__.__name__}); integration tests skipped"
        )
    # migrate to head via the real Alembic scripts (DATABASE_URL points Alembic at the test DB)
    import os

    env = {**os.environ, "DATABASE_URL": url}
    x = ["-x", f"schema={schema}"] if schema else []
    for cmd in (["downgrade", "base"], ["upgrade", "head"]):
        r = subprocess.run(
            [sys.executable, "-m", "alembic", *x, *cmd],
            cwd=BACKEND,
            env=env,
            capture_output=True,
            text=True,
        )
        assert r.returncode == 0, r.stderr
    if schema:
        # Fail loudly rather than run isolation-dependent tests against `public`.
        with engine.connect() as c:
            current = c.execute(text("SELECT current_schema()")).scalar()
            assert current == schema, f"search_path not applied: {current!r}"
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
