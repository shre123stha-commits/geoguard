"""Create the first admin (and optionally the sample parcels) on a fresh, migrated database.

Usage (from backend/, venv active, .env filled):
    python scripts/seed.py                 # admin from FIRST_ADMIN_EMAIL / FIRST_ADMIN_PASSWORD
    python scripts/seed.py --sample-parcels ../data/samples/parcels.geojson
    python scripts/seed.py --sample-parcels ../data/samples/parcels.geojson --sample-scan

`--sample-scan` runs one complete scan of the sample parcels right away using the offline
scenes in DATA_DIR/local_scenes (created by scripts/composites_to_local_scenes.py), so the
first screen already shows real detections (appflow Flow G). It needs no network.

Idempotent: an existing admin email is left untouched; sample parcels are skipped if a
parcel with the same name exists; the sample scan is skipped if any scan exists.
"""

import argparse
import json
import logging
import sys
import uuid
from datetime import date
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import Settings, get_settings  # noqa: E402
from app.core.logging import setup_logging  # noqa: E402
from app.db.enums import UserRole  # noqa: E402
from app.db.session import get_session_factory  # noqa: E402
from app.repositories import ParcelRepository, UserRepository  # noqa: E402

log = logging.getLogger("seed")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample-parcels", metavar="GEOJSON", help="optional parcels file to load")
    ap.add_argument(
        "--sample-scan",
        action="store_true",
        help="run one offline scan of the sample parcels (needs DATA_DIR/local_scenes)",
    )
    args = ap.parse_args()
    settings = get_settings()
    setup_logging(settings.log_level)

    email = settings.first_admin_email.strip()
    password = settings.first_admin_password.get_secret_value()
    if not email or password in {"", "CHANGE_ME"}:
        log.error("set FIRST_ADMIN_EMAIL and a real FIRST_ADMIN_PASSWORD in .env first")
        return 2

    with get_session_factory()() as db:
        users = UserRepository(db)
        if users.get_by_email(email):
            log.info("admin %s already exists — nothing to do", email)
        else:
            users.create(
                email, "Administrator", password, UserRole.admin, must_change_password=True
            )
            log.info("created admin %s (must change password at first login)", email)
        if args.sample_parcels:
            parcels = ParcelRepository(db)
            existing = {p.name for p in parcels.list_all()}
            feats = json.loads(Path(args.sample_parcels).read_text(encoding="utf-8"))["features"]
            n = 0
            for f in feats:
                name = f["properties"].get("name", "parcel")
                if name in existing:
                    continue
                parcels.create(
                    name,
                    f["properties"].get("category", "unknown"),
                    f["geometry"],
                    source="upload",
                    source_ref=Path(args.sample_parcels).name,
                    created_by=users.get_by_email(email).id,  # type: ignore[union-attr]
                )
                n += 1
            log.info("loaded %d sample parcels (%d skipped as existing)", n, len(feats) - n)
        db.commit()
        if args.sample_scan:
            return _sample_scan(db, settings, users.get_by_email(email).id)  # type: ignore[union-attr]
    return 0


def _sample_scan(db: Session, settings: Settings, admin_id: uuid.UUID) -> int:
    from app.db.models import Detection, Scan
    from app.pipeline.fusion import ALGORITHM_VERSION
    from app.pipeline.sources.local_folder import MANIFEST
    from app.repositories import ScanRepository
    from app.schemas.scans import ScanParamsIn
    from app.services.scan_runner import ScanRunner

    if db.scalar(select(func.count()).select_from(Scan)):
        log.info("a scan already exists — sample scan skipped")
        return 0
    scenes = settings.data_dir / "local_scenes"
    if not (scenes / MANIFEST).is_file():
        log.error(
            "no offline scenes at %s — run scripts/composites_to_local_scenes.py first", scenes
        )
        return 2
    windows_path = settings.data_dir / "samples" / "windows.json"
    windows = json.loads(windows_path.read_text(encoding="utf-8"))
    parcels = ParcelRepository(db).list_all()
    if not parcels:
        log.error("no parcels to scan — pass --sample-parcels as well")
        return 2
    scan = ScanRepository(db).create(
        parcels,
        (date.fromisoformat(windows["baseline"][0]), date.fromisoformat(windows["baseline"][1])),
        (date.fromisoformat(windows["current"][0]), date.fromisoformat(windows["current"][1])),
        ScanParamsIn().model_dump(),
        ALGORITHM_VERSION,
        created_by=admin_id,
    )
    db.commit()
    offline = settings.model_copy(update={"imagery_provider": "local_folder"})
    ScanRunner(db, offline).run(scan)
    db.commit()
    n = db.scalar(select(func.count()).select_from(Detection).where(Detection.scan_id == scan.id))
    log.info("sample scan %s: %s, %s detections", scan.id, scan.status.value, n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
