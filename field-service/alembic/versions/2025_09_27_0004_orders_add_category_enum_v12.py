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
    insp = sa.inspect(bind)

    # Ensure enum type exists
    order_category.create(bind, checkfirst=True)

    # Add column only if it does not already exist
    cols = {c.get("name") for c in insp.get_columns("orders")}
    if "category" not in cols:
        op.add_column(
            "orders",
            sa.Column(
                "category",
                sa.Enum(name="order_category", create_type=False),
                nullable=False,
                server_default="ELECTRICS",
            ),
        )

    # Create index if missing
    idx_names = {i.get("name") for i in insp.get_indexes("orders")}
    if "ix_orders__category" not in idx_names:
        op.create_index("ix_orders__category", "orders", ["category"])



def downgrade() -> None:
    # Best-effort downgrade with guards
    bind = op.get_bind()
    insp = sa.inspect(bind)

    idx_names = {i.get("name") for i in insp.get_indexes("orders")}
    if "ix_orders__category" in idx_names:
        op.drop_index("ix_orders__category", table_name="orders")

    cols = {c.get("name") for c in insp.get_columns("orders")}
    if "category" in cols:
        op.drop_column("orders", "category")

    order_category.drop(bind, checkfirst=True)
