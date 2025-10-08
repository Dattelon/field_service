"""Drop legacy order fields and finalize v1.2 schema"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "2025_09_27_0003"
down_revision = "2025_09_27_0002"
branch_labels = None
depends_on = None

LEGACY_COLUMNS = (
    "scheduled_date",
    "time_slot_start",
    "time_slot_end",
    "slot_label",
    "total_price",
    "latitude",
    "longitude",
)
NEW_STATUSES = (
    "CREATED",
    "SEARCHING",
    "ASSIGNED",
    "EN_ROUTE",
    "WORKING",
    "PAYMENT",
    "CLOSED",
    "DEFERRED",
    "GUARANTEE",
    "CANCELED",
)
INDEXES_TO_DROP = (
    "ix_orders__status_city_date",
)


def _drop_column_if_exists(column: str) -> None:
    op.execute(
        sa.text(
            "ALTER TABLE orders DROP COLUMN IF EXISTS {}".format(column)
        )
    )


def _drop_index_if_exists(name: str) -> None:
    op.execute(sa.text(f"DROP INDEX IF EXISTS {name}"))


def _drop_check_if_exists(name: str) -> None:
    op.execute(sa.text(f"ALTER TABLE orders DROP CONSTRAINT IF EXISTS {name}"))


def _recreate_order_status_enum(bind) -> None:
    inspector = sa.inspect(bind)
    current_labels = None
    for enum in inspector.get_enums():
        if enum.get("name") == "order_status":
            current_labels = set(enum.get("labels", ()))
            break

    desired = set(NEW_STATUSES)
    if current_labels == desired:
        return

    op.execute("DROP TYPE IF EXISTS order_status_new CASCADE")
    temp_enum = sa.Enum(*NEW_STATUSES, name="order_status_new")
    temp_enum.create(bind, checkfirst=False)

    op.execute("ALTER TABLE orders ALTER COLUMN status DROP DEFAULT")
    op.execute("ALTER TABLE order_status_history ALTER COLUMN to_status DROP DEFAULT")
    op.execute("ALTER TABLE order_status_history ALTER COLUMN from_status DROP DEFAULT")

    op.execute(
        "ALTER TABLE orders ALTER COLUMN status TYPE order_status_new USING status::text::order_status_new"
    )
    op.execute(
        "ALTER TABLE order_status_history ALTER COLUMN to_status TYPE order_status_new USING to_status::text::order_status_new"
    )
    op.execute(
        "ALTER TABLE order_status_history ALTER COLUMN from_status TYPE order_status_new USING from_status::text::order_status_new"
    )

    op.execute("DROP TYPE order_status")
    op.execute("ALTER TYPE order_status_new RENAME TO order_status")
    op.execute("ALTER TABLE orders ALTER COLUMN status SET DEFAULT 'CREATED'")


def upgrade() -> None:
    bind = op.get_bind()

    for index in INDEXES_TO_DROP:
        _drop_index_if_exists(index)

    _drop_check_if_exists("ck_orders__slot_interval_valid")
    _drop_check_if_exists("ck_orders__slot_in_working_window")
    _drop_check_if_exists("ck_orders__timeslot_range")
    _drop_check_if_exists("ck_orders__ck_orders__timeslot_range")

    for column in LEGACY_COLUMNS:
        _drop_column_if_exists(column)

    _recreate_order_status_enum(bind)

    inspector = sa.inspect(bind)
    indexes = {idx["name"] for idx in inspector.get_indexes("orders")}
    checks = {chk["name"] for chk in inspector.get_check_constraints("orders")}

    if "ix_orders__status_city_timeslot_start" not in indexes:
        op.create_index(
            "ix_orders__status_city_timeslot_start",
            "orders",
            ["status", "city_id", "timeslot_start_utc"],
        )
    if "ck_orders__timeslot_range" not in checks and "ck_orders__ck_orders__timeslot_range" not in checks:
        op.create_check_constraint(
            "timeslot_range",
            "orders",
            "(timeslot_start_utc IS NULL AND timeslot_end_utc IS NULL) OR (timeslot_start_utc < timeslot_end_utc)",
        )


def downgrade() -> None:
    raise NotImplementedError("legacy schema cleanup is irreversible")
