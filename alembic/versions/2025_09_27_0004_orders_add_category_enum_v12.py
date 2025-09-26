"""orders add category enum v1.2

Revision ID: 2025_09_27_0004
Revises: 2025_09_27_0003
Create Date: 2025-09-27 00:04:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "2025_09_27_0004"
down_revision = "2025_09_27_0003"
branch_labels = None
depends_on = None

order_category = sa.Enum(
    "ELECTRICS",
    "PLUMBING",
    "APPLIANCES",
    "WINDOWS",
    "HANDYMAN",
    "ROADSIDE",
    name="order_category",
)


def upgrade() -> None:
    bind = op.get_bind()
    order_category.create(bind, checkfirst=True)

    op.add_column(
        "orders",
        sa.Column(
            "category",
            sa.Enum(name="order_category", create_type=False),
            nullable=False,
            server_default="ELECTRICS",
        ),
    )
    op.create_index("ix_orders__category", "orders", ["category"])



def downgrade() -> None:
    op.drop_index("ix_orders__category", table_name="orders")
    op.drop_column("orders", "category")

    bind = op.get_bind()
    order_category.drop(bind, checkfirst=True)
