"""init extensions + enums (schema 05 §2–3)

Revision ID: 0001
Revises:
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

ENUMS = {
    "user_role": ("admin", "officer"),
    "scan_status": ("queued", "running", "succeeded", "failed", "cancelled"),
    "detection_status": ("new", "confirmed", "dismissed", "field_visit"),
    "confidence_class": ("high", "medium", "low"),
    "sensor_type": ("sentinel1", "sentinel2"),
    "period_type": ("baseline", "current"),
    "evidence_kind": ("before_rgb", "after_rgb", "change_map", "overview"),
    "alert_status": ("pending", "sent", "failed"),
}


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis WITH SCHEMA public")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public")
    for name, values in ENUMS.items():
        vals = ", ".join(f"'{v}'" for v in values)
        op.execute(f"CREATE TYPE {name} AS ENUM ({vals})")


def downgrade() -> None:
    for name in reversed(list(ENUMS)):
        op.execute(f"DROP TYPE IF EXISTS {name}")
    # extensions are left in place on purpose (shared, cheap, and PostGIS drop is destructive)
