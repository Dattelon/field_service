"""guarantee_cycle: link to source order + company_payment"""

from alembic import op
import sqlalchemy as sa

revision = "2025_09_19_0011"
down_revision = "2025_09_19_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) company_payment
    op.add_column(
        "orders",
        sa.Column(
            "company_payment", sa.Numeric(10, 2), nullable=False, server_default="0"
        ),
    )
    # 2) связь с исходным заказом
    op.add_column(
        "orders",
        sa.Column(
            "guarantee_source_order_id",
            sa.Integer,
            sa.ForeignKey("orders.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_orders__guarantee_source", "orders", ["guarantee_source_order_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_orders__guarantee_source", table_name="orders")
    op.drop_column("orders", "guarantee_source_order_id")
    op.drop_column("orders", "company_payment")
