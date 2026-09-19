"""Create the first admin (and optionally the sample parcels) on a fresh, migrated database.

Usage (from backend/, venv active, .env filled):
    python scripts/seed.py                 # admin from FIRST_ADMIN_EMAIL / FIRST_ADMIN_PASSWORD
    python scripts/seed.py --sample-parcels ../data/samples/parcels.geojson

Idempotent: an existing admin email is left untouched; sample parcels are skipped if a
parcel with the same name exists. The first admin must change the password at first login.
"""

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from app.core.logging import setup_logging  # noqa: E402
from app.db.enums import UserRole  # noqa: E402
from app.db.session import get_session_factory  # noqa: E402
from app.repositories import ParcelRepository, UserRepository  # noqa: E402

log = logging.getLogger("seed")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample-parcels", metavar="GEOJSON", help="optional parcels file to load")
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
