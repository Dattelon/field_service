"""seed_cities: 78   Field Service v1.2

Revision ID: 2025_09_17_0002a
Revises: 2025_09_17_0002
Create Date: 2025-09-17 18:00:00.000000
"""

from __future__ import annotations
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "2025_09_17_0002a"
down_revision = "2025_09_17_0002"
branch_labels = None
depends_on = None

CITIES = [
    # 115
    "",
    " ",
    "",
    "",
    "",
    " ",
    "",
    "",
    "",
    "",
    "  ",
    "",
    "",
    "",
    "",
    # 1645
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    " ",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    " ()",
    "",
    # 4678
    "",
    "",
    "",
    " ",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    " ()",
    "",
    "",
    "",
    "",
    " ",
    " ",
    " ",
    "",
    "",
    " ",
    "",
    "",
    "",
    "",
    " ()",
    "",
    "",
    "",
]


def upgrade() -> None:
    conn = op.get_bind()
    #  
    for name in CITIES:
        conn.execute(
            sa.text(
                """
            INSERT INTO cities(name, is_active)
            VALUES (:name, TRUE)
            ON CONFLICT (name) DO NOTHING
        """
            ),
            {"name": name},
        )


def downgrade() -> None:
    #      ().
    #      .
    pass
