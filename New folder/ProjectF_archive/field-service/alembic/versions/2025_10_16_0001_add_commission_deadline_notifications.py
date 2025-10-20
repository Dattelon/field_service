"""add commission_deadline_notifications table

Revision ID: 2025_10_16_0001
Revises: 4c2465ccb4e5
Create Date: 2025-10-16 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "2025_10_16_0001"
down_revision = "4c2465ccb4e5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create commission_deadline_notifications table if it doesn't exist."""
    
    # Проверяем существование таблицы через raw SQL
    conn = op.get_bind()
    result = conn.execute(
        sa.text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'commission_deadline_notifications'
            );
        """)
    )
    table_exists = result.scalar()
    
    if not table_exists:
        # Создаём таблицу
        op.create_table(
            "commission_deadline_notifications",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "commission_id",
                sa.Integer(),
                sa.ForeignKey("commissions.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "hours_before",
                sa.SmallInteger(),
                nullable=False,
            ),
            sa.Column(
                "sent_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("NOW()"),
            ),
            sa.CheckConstraint(
                "hours_before IN (1, 6, 24)",
                name="commission_deadline_notifications_hours_before_check",
            ),
            sa.UniqueConstraint(
                "commission_id",
                "hours_before",
                name="uq_commission_deadline__commission_hours",
            ),
        )
        
        # Создаём индекс
        op.create_index(
            "ix_commission_deadline_notifications__commission",
            "commission_deadline_notifications",
            ["commission_id"],
        )


def downgrade() -> None:
    """Drop commission_deadline_notifications table."""
    op.drop_index(
        "ix_commission_deadline_notifications__commission",
        table_name="commission_deadline_notifications",
    )
    op.drop_table("commission_deadline_notifications")
