"""users + parcels (schema 05 §4.1–4.2)

Revision ID: 0002
Revises: 0001
"""

import geoalchemy2 as ga
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def _enum(name: str) -> pg.ENUM:
    return pg.ENUM(name=name, create_type=False)


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column(
            "id",
            pg.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("email", sa.Text, nullable=False, unique=True),
        sa.Column("full_name", sa.Text, nullable=False),
        sa.Column("password_hash", sa.Text, nullable=False),
        sa.Column("role", _enum("user_role"), nullable=False, server_default="officer"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("telegram_chat_id", sa.Text),
        sa.Column(
            "must_change_password", sa.Boolean, nullable=False, server_default=sa.text("false")
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_table(
        "parcels",
        sa.Column(
            "id",
            pg.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("category", sa.Text, nullable=False),
        sa.Column("notes", sa.Text),
        sa.Column(
            "geom", ga.Geometry("MULTIPOLYGON", srid=4326, spatial_index=False), nullable=False
        ),
        sa.Column("area_m2", sa.Float, nullable=False),
        sa.Column("source", sa.Text, nullable=False, server_default="upload"),
        sa.Column("source_ref", sa.Text),
        sa.Column(
            "created_by", pg.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("source IN ('upload','drawn')", name="parcels_source_check"),
        sa.CheckConstraint("ST_IsValid(geom)", name="parcels_valid_geom"),
    )
    op.create_index("idx_parcels_geom", "parcels", ["geom"], postgresql_using="gist")


def downgrade() -> None:
    op.drop_table("parcels")
    op.drop_table("users")
