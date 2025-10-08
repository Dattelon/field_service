"""Add geo centroids and geocache cache table"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "2025_10_02_0003_geo_enhancements"
down_revision = "2025_10_01_0002_cities_timezone"
branch_labels = None
depends_on = None


def _has_column(inspector, table_name: str, column_name: str) -> bool:
    return column_name in {col["name"] for col in inspector.get_columns(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_column(inspector, "cities", "timezone"):
        op.add_column("cities", sa.Column("timezone", sa.String(length=64), nullable=True))
    if not _has_column(inspector, "cities", "centroid_lat"):
        op.add_column("cities", sa.Column("centroid_lat", sa.Float(), nullable=True))
    if not _has_column(inspector, "cities", "centroid_lon"):
        op.add_column("cities", sa.Column("centroid_lon", sa.Float(), nullable=True))

    if not _has_column(inspector, "districts", "centroid_lat"):
        op.add_column("districts", sa.Column("centroid_lat", sa.Float(), nullable=True))
    if not _has_column(inspector, "districts", "centroid_lon"):
        op.add_column("districts", sa.Column("centroid_lon", sa.Float(), nullable=True))

    if not _has_column(inspector, "streets", "centroid_lat"):
        op.add_column("streets", sa.Column("centroid_lat", sa.Float(), nullable=True))
    if not _has_column(inspector, "streets", "centroid_lon"):
        op.add_column("streets", sa.Column("centroid_lon", sa.Float(), nullable=True))

    if not _has_column(inspector, "orders", "geocode_provider"):
        op.add_column("orders", sa.Column("geocode_provider", sa.String(length=32), nullable=True))
    if not _has_column(inspector, "orders", "geocode_confidence"):
        op.add_column("orders", sa.Column("geocode_confidence", sa.Integer(), nullable=True))

    if "geocache" not in inspector.get_table_names():
        op.create_table(
            "geocache",
            sa.Column("query", sa.String(length=255), primary_key=True),
            sa.Column("lat", sa.Float(), nullable=True),
            sa.Column("lon", sa.Float(), nullable=True),
            sa.Column("provider", sa.String(length=32), nullable=True),
            sa.Column("confidence", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        )
        op.create_index("ix_geocache_created_at", "geocache", ["created_at"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "geocache" in inspector.get_table_names():
        op.drop_index("ix_geocache_created_at", table_name="geocache")
        op.drop_table("geocache")

    for table, column in (
        ("orders", "geocode_confidence"),
        ("orders", "geocode_provider"),
        ("streets", "centroid_lon"),
        ("streets", "centroid_lat"),
        ("districts", "centroid_lon"),
        ("districts", "centroid_lat"),
        ("cities", "centroid_lon"),
        ("cities", "centroid_lat"),
        ("cities", "timezone"),
    ):
        if _has_column(inspector, table, column):
            op.drop_column(table, column)

