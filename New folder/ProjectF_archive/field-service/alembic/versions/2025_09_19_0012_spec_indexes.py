"""apply_spec_indexes: align indexes with TZ requirements"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "2025_09_19_0012"
down_revision = "2025_09_19_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # masters: add is_on_shift + verified flags with defaults
    op.add_column(
        "masters",
        sa.Column(
            "is_on_shift",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "masters",
        sa.Column(
            "verified",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.execute(
        "UPDATE masters SET is_on_shift = (shift_status='SHIFT_ON'), verified = (moderation_status='APPROVED')"
    )
    op.create_index(
        "ix_masters__onshift_verified",
        "masters",
        ["is_on_shift", "verified"],
    )
    op.alter_column(
        "masters",
        "is_on_shift",
        server_default=sa.text("false"),
    )
    op.alter_column(
        "masters",
        "verified",
        server_default=sa.text("false"),
    )

    # orders: status + city index for distribution worker
    op.create_index(
        "ix_orders__status_city",
        "orders",
        ["status", "city_id"],
    )

    # commissions: rename due_at -> deadline_at and add index
    op.drop_index("ix_commissions__status_due", table_name="commissions")
    op.drop_index("ix_commissions__master_status", table_name="commissions")
    op.drop_index(
        "ix_commissions__ispaid_due",
        table_name="commissions",
        if_exists=True,
    )
    op.execute("ALTER TABLE commissions RENAME COLUMN due_at TO deadline_at")
    op.create_index(
        "ix_commissions__ispaid_deadline",
        "commissions",
        ["is_paid", "deadline_at"],
    )

    op.create_index(
        "ix_commissions__status_deadline",
        "commissions",
        ["status", "deadline_at"],
    )
    op.create_index(
        "ix_commissions__master_status",
        "commissions",
        ["master_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_commissions__ispaid_deadline", table_name="commissions")
    op.drop_index("ix_commissions__master_status", table_name="commissions")
    op.drop_index("ix_commissions__status_deadline", table_name="commissions")
    op.execute("ALTER TABLE commissions RENAME COLUMN deadline_at TO due_at")
    op.create_index(
        "ix_commissions__ispaid_due",
        "commissions",
        ["is_paid", "due_at"],
    )
    op.create_index(
        "ix_commissions__master_status",
        "commissions",
        ["master_id", "status"],
    )
    op.create_index(
        "ix_commissions__status_due",
        "commissions",
        ["status", "due_at"],
    )

    op.drop_index("ix_orders__status_city", table_name="orders")

    op.drop_index("ix_masters__onshift_verified", table_name="masters")
    op.drop_column("masters", "verified")
    op.drop_column("masters", "is_on_shift")
