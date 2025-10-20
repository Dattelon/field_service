"""Add v1.2 order fields"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from alembic import op
import sqlalchemy as sa

from field_service.config import settings


revision = "2025_09_27_0002"
down_revision = "2025_09_23_0003"
branch_labels = None
depends_on = None

ORDER_STATUS_VALUES = ("SEARCHING", "EN_ROUTE", "WORKING", "PAYMENT")
ORDER_TYPE_ENUM = sa.Enum("NORMAL", "GUARANTEE", name="order_type", create_type=False)

LEGACY_COLUMNS = (
    sa.Column("type", ORDER_TYPE_ENUM, nullable=False, server_default="NORMAL"),
    sa.Column("timeslot_start_utc", sa.DateTime(timezone=True), nullable=True),
    sa.Column("timeslot_end_utc", sa.DateTime(timezone=True), nullable=True),
    sa.Column(
        "total_sum",
        sa.Numeric(10, 2),
        nullable=False,
        server_default="0",
    ),
    sa.Column("lat", sa.Float(precision=53), nullable=True),
    sa.Column("lon", sa.Float(precision=53), nullable=True),
    sa.Column(
        "no_district",
        sa.Boolean,
        nullable=False,
        server_default=sa.text("false"),
    ),
)


def _resolve_timezone() -> ZoneInfo:
    tz_name = getattr(settings, "timezone", None) or "UTC"
    try:
        return ZoneInfo(tz_name)
    except Exception:  # pragma: no cover - fallback
        return ZoneInfo("UTC")


def _add_enum_values() -> None:
    for value in ORDER_STATUS_VALUES:
        quoted = value.replace("'", "''")
        op.execute(f"ALTER TYPE order_status ADD VALUE IF NOT EXISTS '{quoted}'")


def _add_columns(bind) -> set[str]:
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("orders")}

    ORDER_TYPE_ENUM.create(bind, checkfirst=True)

    if "type" not in columns:
        op.add_column("orders", sa.Column("type", ORDER_TYPE_ENUM, nullable=False, server_default="NORMAL"))
    if "timeslot_start_utc" not in columns:
        op.add_column("orders", sa.Column("timeslot_start_utc", sa.DateTime(timezone=True), nullable=True))
    if "timeslot_end_utc" not in columns:
        op.add_column("orders", sa.Column("timeslot_end_utc", sa.DateTime(timezone=True), nullable=True))
    if "total_sum" not in columns:
        op.add_column("orders", sa.Column("total_sum", sa.Numeric(10, 2), nullable=False, server_default="0"))
    if "lat" not in columns:
        op.add_column("orders", sa.Column("lat", sa.Float(asdecimal=False), nullable=True))
    if "lon" not in columns:
        op.add_column("orders", sa.Column("lon", sa.Float(asdecimal=False), nullable=True))
    if "no_district" not in columns:
        op.add_column("orders", sa.Column("no_district", sa.Boolean(), nullable=False, server_default=sa.text("false")))

    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("orders")}
    indexes = {idx["name"] for idx in inspector.get_indexes("orders")}
    checks = {chk["name"] for chk in inspector.get_check_constraints("orders")}

    if "ix_orders__status_city_timeslot_start" not in indexes:
        op.create_index("ix_orders__status_city_timeslot_start", "orders", ["status", "city_id", "timeslot_start_utc"])
    if "ck_orders__timeslot_range" not in checks:
        op.create_check_constraint("ck_orders__timeslot_range", "orders", "(timeslot_start_utc IS NULL AND timeslot_end_utc IS NULL) OR (timeslot_start_utc < timeslot_end_utc)")

    return columns


def _backfill_orders(bind, columns: set[str]) -> None:
    metadata = sa.MetaData()
    orders = sa.Table("orders", metadata, autoload_with=bind)

    tz = _resolve_timezone()
    rows = list(
        bind.execute(
            sa.select(
                orders.c.id,
                orders.c.scheduled_date,
                orders.c.time_slot_start,
                orders.c.time_slot_end,
                orders.c.total_price,
                orders.c.latitude,
                orders.c.longitude,
                orders.c.district_id,
                orders.c.order_type,
            )
        )
    )

    for row in rows:
        values: dict[str, object] = {}

        scheduled_date = row.scheduled_date
        start_local = row.time_slot_start
        end_local = row.time_slot_end

        if "timeslot_start_utc" in columns and scheduled_date and start_local:
            start_dt = datetime.combine(scheduled_date, start_local, tzinfo=tz)
            values["timeslot_start_utc"] = start_dt.astimezone(timezone.utc)
        if "timeslot_end_utc" in columns and scheduled_date and end_local:
            end_dt = datetime.combine(scheduled_date, end_local, tzinfo=tz)
            values["timeslot_end_utc"] = end_dt.astimezone(timezone.utc)

        if "total_sum" in columns:
            total_price = row.total_price
            if total_price is None:
                total_sum = Decimal("0")
            else:
                total_sum = Decimal(str(total_price))
            values["total_sum"] = total_sum

        if "lat" in columns and row.latitude is not None:
            values["lat"] = float(row.latitude)
        if "lon" in columns and row.longitude is not None:
            values["lon"] = float(row.longitude)

        if "no_district" in columns and row.district_id is None:
            values["no_district"] = True

        if "type" in columns:
            order_type_value = row.order_type
            if order_type_value is None:
                db_value = "NORMAL"
            elif hasattr(order_type_value, "value"):
                db_value = str(order_type_value.value)
            else:
                db_value = str(order_type_value)
            values["type"] = db_value

        if values:
            bind.execute(
                orders.update().where(orders.c.id == row.id).values(**values)
            )




def upgrade() -> None:
    _add_enum_values()
    bind = op.get_bind()
    columns = _add_columns(bind)

    _backfill_orders(bind, columns)

    op.alter_column("orders", "type", server_default=None)


def downgrade() -> None:
    raise NotImplementedError("orders v1.2 fields cannot be rolled back")

