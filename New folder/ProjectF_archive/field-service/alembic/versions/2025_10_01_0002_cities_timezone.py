"""Add timezone column to cities and populate canonical IANA zones."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

from field_service.data.cities import CITY_TIMEZONES

# revision identifiers, used by Alembic.
revision = "2025_10_01_0002_cities_timezone"
down_revision = "2025_10_01_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cities", sa.Column("timezone", sa.String(length=64), nullable=True))

    conn = op.get_bind()
    update_sql = sa.text(
        """
        UPDATE cities
           SET timezone = :tz
         WHERE name = :name
        """
    )
    for name, tz in CITY_TIMEZONES.items():
        conn.execute(update_sql, {"name": name, "tz": tz})


def downgrade() -> None:
    op.drop_column("cities", "timezone")
