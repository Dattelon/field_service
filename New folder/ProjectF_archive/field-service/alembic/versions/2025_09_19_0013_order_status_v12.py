"""Align order statuses with TZ v1.2 and enforce working window"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "2025_09_19_0013"
down_revision = "2025_09_19_0012"
branch_labels = None
depends_on = None


STATUS_MAP = {
    "DISTRIBUTION": "SEARCHING",
    "SCHEDULED": "EN_ROUTE",
    "IN_PROGRESS": "WORKING",
    "DONE": "PAYMENT",
}


def upgrade() -> None:
    for value in ("SEARCHING", "EN_ROUTE", "WORKING", "PAYMENT"):
        with op.get_context().autocommit_block():
            op.execute(
                sa.text(f"ALTER TYPE order_status ADD VALUE IF NOT EXISTS '{value}'")
            )

    bind = op.get_bind()
    for legacy, current in STATUS_MAP.items():
        bind.execute(
            sa.text(
                "UPDATE orders SET status = cast(:new AS order_status) WHERE status = :old"
            ),
            {"new": current, "old": legacy},
        )
        bind.execute(
            sa.text(
                "UPDATE order_status_history SET from_status = cast(:new AS order_status) WHERE from_status = :old"
            ),
            {"new": current, "old": legacy},
        )
        bind.execute(
            sa.text(
                "UPDATE order_status_history SET to_status = cast(:new AS order_status) WHERE to_status = :old"
            ),
            {"new": current, "old": legacy},
        )

    op.execute("ALTER TABLE orders ALTER COLUMN status SET DEFAULT 'CREATED'")

    op.execute("ALTER TABLE orders DROP CONSTRAINT IF EXISTS ck_orders__slot_in_working_window")
    op.create_check_constraint(
        "ck_orders__slot_in_working_window",
        "orders",
        "(time_slot_start IS NULL AND time_slot_end IS NULL) "
        "OR (time_slot_start >= '10:00:00' AND time_slot_end <= '20:00:00' "
        "AND time_slot_start < time_slot_end)",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_orders__slot_in_working_window", table_name="orders", type_="check"
    )

    op.execute("ALTER TABLE orders ALTER COLUMN status DROP DEFAULT")

    for legacy, current in STATUS_MAP.items():
        op.execute(
            f"UPDATE order_status_history SET to_status = '{legacy}' WHERE to_status = '{current}'"
        )
        op.execute(
            f"UPDATE order_status_history SET from_status = '{legacy}' WHERE from_status = '{current}'"
        )
        op.execute(f"UPDATE orders SET status = '{legacy}' WHERE status = '{current}'")
    # New enum values remain present; Postgres does not support removing them safely.
