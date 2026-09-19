"""scans, scan_parcels, scan_scenes (schema 05 §4.3–4.5)

Revision ID: 0003
Revises: 0002
"""

import geoalchemy2 as ga
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def _enum(name: str) -> pg.ENUM:
    return pg.ENUM(name=name, create_type=False)


def _uuid_pk() -> sa.Column:  # type: ignore[type-arg]
    return sa.Column(
        "id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )


def upgrade() -> None:
    op.create_table(
        "scans",
        _uuid_pk(),
        sa.Column("status", _enum("scan_status"), nullable=False, server_default="queued"),
        sa.Column("step", sa.Text),
        sa.Column("progress", sa.SmallInteger, nullable=False, server_default="0"),
        sa.Column("message", sa.Text),
        sa.Column("error_code", sa.Text),
        sa.Column("baseline_start", sa.Date, nullable=False),
        sa.Column("baseline_end", sa.Date, nullable=False),
        sa.Column("current_start", sa.Date, nullable=False),
        sa.Column("current_end", sa.Date, nullable=False),
        sa.Column("params", pg.JSONB, nullable=False),
        sa.Column("algorithm_version", sa.Text, nullable=False),
        sa.Column("aoi_geom", ga.Geometry("POLYGON", srid=4326, spatial_index=False)),
        sa.Column(
            "rerun_of", pg.UUID(as_uuid=True), sa.ForeignKey("scans.id", ondelete="SET NULL")
        ),
        sa.Column("schedule_id", pg.UUID(as_uuid=True)),
        sa.Column(
            "created_by", pg.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("progress BETWEEN 0 AND 100", name="scans_progress_check"),
        sa.CheckConstraint(
            "baseline_start <= baseline_end AND current_start <= current_end "
            "AND baseline_end < current_start",
            name="scans_periods_ok",
        ),
    )
    op.create_index("idx_scans_status_created", "scans", ["status", sa.text("created_at DESC")])
    op.create_table(
        "scan_parcels",
        sa.Column(
            "scan_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("scans.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "parcel_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("parcels.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
    )
    op.create_table(
        "scan_scenes",
        _uuid_pk(),
        sa.Column(
            "scan_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("scans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sensor", _enum("sensor_type"), nullable=False),
        sa.Column("period", _enum("period_type"), nullable=False),
        sa.Column("scene_id", sa.Text, nullable=False),
        sa.Column("acquired_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cloud_cover", pg.REAL),
        sa.Column("orbit", sa.Text),
        sa.Column("footprint", ga.Geometry("POLYGON", srid=4326, spatial_index=False)),
        sa.Column("meta", pg.JSONB),
        sa.UniqueConstraint("scan_id", "sensor", "period", "scene_id", name="scan_scenes_unique"),
    )
    op.create_index("idx_scan_scenes_scan", "scan_scenes", ["scan_id"])


def downgrade() -> None:
    op.drop_table("scan_scenes")
    op.drop_table("scan_parcels")
    op.drop_table("scans")
