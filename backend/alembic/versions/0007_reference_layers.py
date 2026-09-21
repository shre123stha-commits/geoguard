"""reference_layers + reference_features (Phase 9: zone context for detections)

Revision ID: 0007
Revises: 0006
"""

import geoalchemy2 as ga
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

KINDS = "'wetland','water_body','forest','coastal','land_use','custom'"


def upgrade() -> None:
    op.create_table(
        "reference_layers",
        sa.Column(
            "id",
            pg.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("source", sa.Text),
        sa.Column("source_date", sa.Date),
        sa.Column("notes", sa.Text),
        sa.Column("buffer_m", sa.Integer, nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("feature_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "created_by", pg.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(f"kind IN ({KINDS})", name="reference_layers_kind_check"),
        sa.CheckConstraint("buffer_m BETWEEN 0 AND 5000", name="reference_layers_buffer_check"),
    )
    op.create_table(
        "reference_features",
        sa.Column(
            "id",
            pg.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "layer_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("reference_layers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.Text),
        sa.Column("props", pg.JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "geom", ga.Geometry("MULTIPOLYGON", srid=4326, spatial_index=False), nullable=False
        ),
        sa.CheckConstraint("ST_IsValid(geom)", name="reference_features_valid_geom"),
    )
    op.create_index(
        "idx_reference_features_geom", "reference_features", ["geom"], postgresql_using="gist"
    )
    op.create_index("idx_reference_features_layer", "reference_features", ["layer_id"])


def downgrade() -> None:
    op.drop_index("idx_reference_features_layer", table_name="reference_features")
    op.drop_index("idx_reference_features_geom", table_name="reference_features")
    op.drop_table("reference_features")
    op.drop_table("reference_layers")
