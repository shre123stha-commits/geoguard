"""reports, alerts, app_settings (schema 05 §4.9–4.11)

Revision ID: 0005
Revises: 0004
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def _uuid_pk() -> sa.Column:  # type: ignore[type-arg]
    return sa.Column(
        "id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )


def upgrade() -> None:
    op.create_table(
        "reports",
        _uuid_pk(),
        sa.Column(
            "detection_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("detections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("path", sa.Text, nullable=False),
        sa.Column(
            "generated_by", pg.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")
        ),
        sa.Column(
            "generated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "idx_reports_detection", "reports", ["detection_id", sa.text("generated_at DESC")]
    )
    op.create_table(
        "alerts",
        _uuid_pk(),
        sa.Column(
            "detection_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("detections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("channel", sa.Text, nullable=False, server_default="console"),
        sa.Column("recipient", sa.Text, nullable=False),
        sa.Column("provider", sa.Text, nullable=False),
        sa.Column(
            "status",
            pg.ENUM(name="alert_status", create_type=False),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("attempts", sa.SmallInteger, nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
    )
    op.create_index("idx_alerts_detection", "alerts", ["detection_id"])
    op.create_table(
        "app_settings",
        sa.Column("key", sa.Text, primary_key=True),
        sa.Column("value", pg.JSONB, nullable=False),
        sa.Column(
            "updated_by", pg.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )


def downgrade() -> None:
    op.drop_table("app_settings")
    op.drop_table("alerts")
    op.drop_table("reports")
