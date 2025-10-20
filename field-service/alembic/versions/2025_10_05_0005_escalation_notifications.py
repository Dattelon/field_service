"""add escalation notification timestamps

Revision ID: 2025_10_05_0005
Revises: 0010_order_autoclose
Create Date: 2025-10-05 19:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "2025_10_05_0005"
down_revision = "0010_order_autoclose"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add notification tracking fields
    op.add_column(
        "orders",
        sa.Column("escalation_logist_notified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "orders",
        sa.Column("escalation_admin_notified_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("orders", "escalation_admin_notified_at")
    op.drop_column("orders", "escalation_logist_notified_at")
