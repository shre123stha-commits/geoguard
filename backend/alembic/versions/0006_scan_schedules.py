"""scan_schedules, schedule_parcels, scans.schedule_id FK (schema 05 §4.12)

Revision ID: 0006
Revises: 0005
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scan_schedules",
        sa.Column(
            "id",
            pg.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("cron", sa.Text, nullable=False),
        sa.Column("current_window_days", sa.Integer, nullable=False, server_default="30"),
        sa.Column("baseline_rule", pg.JSONB, nullable=False),
        sa.Column("params", pg.JSONB, nullable=False),
        sa.Column("last_run_at", sa.DateTime(timezone=True)),
        sa.Column("next_run_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_by", pg.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "current_window_days BETWEEN 5 AND 120", name="scan_schedules_window_check"
        ),
    )
    op.create_table(
        "schedule_parcels",
        sa.Column(
            "schedule_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("scan_schedules.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "parcel_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("parcels.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )
    op.create_foreign_key(
        "scans_schedule_fk", "scans", "scan_schedules", ["schedule_id"], ["id"], ondelete="SET NULL"
    )


def downgrade() -> None:
    op.drop_constraint("scans_schedule_fk", "scans", type_="foreignkey")
    op.drop_table("schedule_parcels")
    op.drop_table("scan_schedules")
