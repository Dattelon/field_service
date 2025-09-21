"""masters: per-master active orders limit override (merged)
Revision ID: 2025_09_18_0007
Revises: 2025_09_18_0006
Create Date: 2025-09-18 10:05:00
"""

from alembic import op
import sqlalchemy as sa

revision = "2025_09_18_0007"
down_revision = "2025_09_18_0006"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c.get("name") for c in insp.get_columns("masters")}
    if "max_active_orders_override" not in cols:
        op.add_column(
            "masters",
            sa.Column("max_active_orders_override", sa.SmallInteger(), nullable=True),
        )
    checks = {c.get("name") for c in insp.get_check_constraints("masters")}
    if "ck_masters__limit_nonneg" not in checks:
        op.create_check_constraint(
            "ck_masters__limit_nonneg",
            "masters",
            "max_active_orders_override IS NULL OR max_active_orders_override >= 0",
        )


def downgrade():
    op.drop_constraint("ck_masters__limit_nonneg", "masters", type_="check")
    op.drop_column("masters", "max_active_orders_override")
