"""add distribution escalation timestamps"""

from alembic import op
import sqlalchemy as sa


revision = "2025_09_20_0015"
down_revision = "2025_09_19_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "orders",
        sa.Column("dist_escalated_logist_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "orders",
        sa.Column("dist_escalated_admin_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("orders", "dist_escalated_admin_at")
    op.drop_column("orders", "dist_escalated_logist_at")
