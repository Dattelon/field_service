"""staff visibility indexes

Revision ID: 2025_09_22_0001
Revises: 2025_09_20_0016
Create Date: 2025-09-22 10:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "2025_09_22_0001"
down_revision = "2025_09_20_0016"
branch_labels = None
depends_on = None


INDEXES = (
    ("ix_staff_cities__staff_user_id", "staff_user_id"),
    ("ix_staff_cities__city_id", "city_id"),
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {index["name"] for index in inspector.get_indexes("staff_cities")}
    for name, column in INDEXES:
        if name not in existing:
            op.create_index(name, "staff_cities", [column])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {index["name"] for index in inspector.get_indexes("staff_cities")}
    for name, _ in INDEXES:
        if name in existing:
            op.drop_index(name, table_name="staff_cities")
