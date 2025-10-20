"""commission_rework: WAIT_PAY/REPORTED/APPROVED/OVERDUE + snapshot"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "2025_09_19_0009"
down_revision = "2025_09_19_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1)  ENUM commission_status
    op.execute("ALTER TYPE commission_status ADD VALUE IF NOT EXISTS 'WAIT_PAY'")
    op.execute("ALTER TYPE commission_status ADD VALUE IF NOT EXISTS 'REPORTED'")
    op.execute("ALTER TYPE commission_status ADD VALUE IF NOT EXISTS 'APPROVED'")
    # 2)    commissions
    op.add_column("commissions", sa.Column("rate", sa.Numeric(5, 2)))
    op.add_column(
        "commissions", sa.Column("paid_reported_at", sa.DateTime(timezone=True))
    )
    op.add_column(
        "commissions", sa.Column("paid_approved_at", sa.DateTime(timezone=True))
    )
    op.add_column("commissions", sa.Column("paid_amount", sa.Numeric(10, 2)))
    op.add_column(
        "commissions",
        sa.Column(
            "is_paid", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
    )
    op.add_column(
        "commissions",
        sa.Column(
            "has_checks", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
    )
    op.add_column(
        "commissions",
        sa.Column(
            "pay_to_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
    )
    # :        
    #   
    op.create_index("ix_commissions__ispaid_due", "commissions", ["is_paid", "due_at"])


def downgrade() -> None:
    op.drop_index("ix_commissions__ispaid_due", table_name="commissions")
    op.drop_column("commissions", "pay_to_snapshot")
    op.drop_column("commissions", "has_checks")
    op.drop_column("commissions", "is_paid")
    op.drop_column("commissions", "paid_amount")
    op.drop_column("commissions", "paid_approved_at")
    op.drop_column("commissions", "paid_reported_at")
    op.drop_column("commissions", "rate")
    #  ENUM   (),  ;   
