"""Add centroid coordinates to geo tables"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "2025_10_05_0004_add_centroids"
down_revision = "2025_10_02_0003_geo_enhancements"
branch_labels = None
depends_on = None


def _has_column(inspector, table: str, column: str) -> bool:
    return column in {col["name"] for col in inspector.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    for table in ("streets", "districts", "cities"):
        if not _has_column(inspector, table, "centroid_lat"):
            op.add_column(table, sa.Column("centroid_lat", sa.Float(), nullable=True))
        if not _has_column(inspector, table, "centroid_lon"):
            op.add_column(table, sa.Column("centroid_lon", sa.Float(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    for table in ("streets", "districts", "cities"):
        if _has_column(inspector, table, "centroid_lat"):
            op.drop_column(table, "centroid_lat")
        if _has_column(inspector, table, "centroid_lon"):
            op.drop_column(table, "centroid_lon")
