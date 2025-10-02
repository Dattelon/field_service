"""Seed canonical city list for Field Service v1.2."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

from field_service.data.cities import ALLOWED_CITIES

# revision identifiers, used by Alembic.
revision = "2025_09_17_0002a"
down_revision = "2025_09_17_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    insert_stmt = sa.text(
        """
        INSERT INTO cities(name, is_active)
        VALUES (:name, TRUE)
        ON CONFLICT (name) DO NOTHING
        """
    )
    for name in ALLOWED_CITIES:
        conn.execute(insert_stmt, {"name": name})


def downgrade() -> None:
    # No-op: we keep seeded cities.
    pass
