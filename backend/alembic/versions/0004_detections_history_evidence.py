"""detections, detection_status_history, evidence_files (schema 05 §4.6–4.8)

Revision ID: 0004
Revises: 0003
"""

import geoalchemy2 as ga
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0004"
down_revision = "0003"
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
        "detections",
        _uuid_pk(),
        sa.Column(
            "scan_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("scans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "parcel_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("parcels.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "geom", ga.Geometry("MULTIPOLYGON", srid=4326, spatial_index=False), nullable=False
        ),
        sa.Column("centroid", ga.Geometry("POINT", srid=4326, spatial_index=False), nullable=False),
        sa.Column("area_m2", sa.Float, nullable=False),
        sa.Column("confidence", _enum("confidence_class"), nullable=False),
        sa.Column("score", pg.REAL, nullable=False),
        sa.Column("optical_detected", sa.Boolean, nullable=False),
        sa.Column("radar_detected", sa.Boolean, nullable=False),
        sa.Column("d_bui_mean", pg.REAL),
        sa.Column("d_ndvi_mean", pg.REAL),
        sa.Column("d_sigma_vv_mean", pg.REAL),
        sa.Column("sar_overlap", pg.REAL),
        sa.Column("status", _enum("detection_status"), nullable=False, server_default="new"),
        sa.Column("status_note", sa.Text),
        sa.Column(
            "reviewed_by", pg.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "matches_detection",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("detections.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("area_m2 > 0", name="detections_area_check"),
        sa.CheckConstraint("score BETWEEN 0 AND 1", name="detections_score_check"),
        sa.CheckConstraint(
            "sar_overlap IS NULL OR sar_overlap BETWEEN 0 AND 1", name="detections_overlap_check"
        ),
    )
    op.create_index("idx_detections_geom", "detections", ["geom"], postgresql_using="gist")
    op.create_index("idx_detections_centroid", "detections", ["centroid"], postgresql_using="gist")
    op.create_index("idx_detections_scan", "detections", ["scan_id"])
    op.create_index("idx_detections_parcel", "detections", ["parcel_id"])
    op.create_index(
        "idx_detections_filter", "detections", ["status", "confidence", sa.text("created_at DESC")]
    )

    op.create_table(
        "detection_status_history",
        _uuid_pk(),
        sa.Column(
            "detection_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("detections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("from_status", _enum("detection_status")),
        sa.Column("to_status", _enum("detection_status"), nullable=False),
        sa.Column("note", sa.Text),
        sa.Column("reason_code", sa.Text),
        sa.Column(
            "changed_by", pg.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")
        ),
        sa.Column(
            "changed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "idx_dsh_detection",
        "detection_status_history",
        ["detection_id", sa.text("changed_at DESC")],
    )

    op.create_table(
        "evidence_files",
        _uuid_pk(),
        sa.Column(
            "detection_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("detections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", _enum("evidence_kind"), nullable=False),
        sa.Column("path", sa.Text, nullable=False),
        sa.Column("width_px", sa.Integer),
        sa.Column("height_px", sa.Integer),
        sa.Column("bounds", ga.Geometry("POLYGON", srid=4326, spatial_index=False)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("detection_id", "kind", name="evidence_files_unique"),
    )


def downgrade() -> None:
    op.drop_table("evidence_files")
    op.drop_table("detection_status_history")
    op.drop_table("detections")
