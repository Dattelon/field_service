"""Add retry tracking fields to notifications_outbox

Revision ID: 2025_10_02_0001
Revises: 2025_10_01_0001
Create Date: 2025-10-02 09:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "2025_10_02_0001"
down_revision = "2025_10_01_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "notifications_outbox",
        sa.Column(
            "attempt_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "notifications_outbox",
        sa.Column("last_error", sa.Text(), nullable=True),
    )
    op.alter_column(
        "notifications_outbox",
        "attempt_count",
        server_default=None,
    )


def downgrade() -> None:
    op.drop_column("notifications_outbox", "last_error")
    op.drop_column("notifications_outbox", "attempt_count")
