"""field photo evidence — Phase 9.4

Revision ID: 0009
Revises: 0008
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE cannot run inside a transaction block on PG < 12; on Supabase
    # (PG 15+) it can, but committing first is harmless and portable.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE evidence_kind ADD VALUE IF NOT EXISTS 'field_photo'")
    op.add_column(
        "evidence_files",
        sa.Column(
            "meta",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("evidence_files", "meta")
    # enum values cannot be dropped in PostgreSQL; rows of kind field_photo are removed instead
    op.execute("DELETE FROM evidence_files WHERE kind = 'field_photo'")
