"""seasonal-model scan mode: month a change began — Phase 9.6

Revision ID: 0010
Revises: 0009
"""

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("detections", sa.Column("onset_month", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("detections", "onset_month")
