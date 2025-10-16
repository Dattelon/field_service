"""merge_heads_test_and_main

Revision ID: 4c2465ccb4e5
Revises: 2025_10_02_0001, 2025_10_15_0001
Create Date: 2025-10-15 17:36:54.375080
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '4c2465ccb4e5'
down_revision = ('2025_10_02_0001', '2025_10_15_0001')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
