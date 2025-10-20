"""merge heads: unify branches

Revision ID: 2cad62ab4b40
Revises: 2025_09_19_0011b, 2025_09_admin_role_rename
Create Date: 2025-09-28 12:58:53.400120
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '2cad62ab4b40'
down_revision = ('2025_09_19_0011b', '2025_09_admin_role_rename')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
