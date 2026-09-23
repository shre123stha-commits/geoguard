"""parcel_timeseries — monthly built-up fraction per parcel (Phase 9.3)

Revision ID: 0008
Revises: 0007
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "parcel_timeseries",
        sa.Column(
            "parcel_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("parcels.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("month", sa.Date, primary_key=True),  # first day of the month
        sa.Column("built_frac", sa.REAL),  # share of parcel pixels with BUI >= t_bui (0..1)
        sa.Column("ndvi_mean", sa.REAL),
        sa.Column("valid_frac", sa.REAL),  # share of parcel pixels with a clear observation
        sa.Column("n_scenes", sa.Integer, nullable=False, server_default="0"),
        sa.Column("t_bui", sa.REAL, nullable=False),
        sa.Column(
            "computed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_table(
        "timeline_jobs",
        sa.Column(
            "parcel_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("parcels.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("status", sa.Text, nullable=False),  # running | done | failed
        sa.Column("progress", sa.Integer, nullable=False, server_default="0"),
        sa.Column("message", sa.Text),
        sa.Column("months_total", sa.Integer, nullable=False, server_default="0"),
        sa.Column("months_done", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("status IN ('running','done','failed')", name="timeline_jobs_status"),
    )


def downgrade() -> None:
    op.drop_table("timeline_jobs")
    op.drop_table("parcel_timeseries")
