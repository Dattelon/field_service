"""orders_v12_compat: add v1.2 order columns and backfill"""

from __future__ import annotations

import os
from datetime import datetime
from zoneinfo import ZoneInfo

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision = "2025_09_22_0002"
down_revision = "2025_09_22_0001"
branch_labels = None
depends_on = None

ORDER_CATEGORY_ENUM = (
    "ELECTRICS",
    "PLUMBING",
    "APPLIANCES",
    "WINDOWS",
    "HANDYMAN",
    "ROADSIDE",
)


def _has_column(inspector: sa.engine.reflection.Inspector, table: str, column: str) -> bool:
    return any(col["name"] == column for col in inspector.get_columns(table))


def _create_order_category_enum(bind) -> postgresql.ENUM:
    enum = postgresql.ENUM(*ORDER_CATEGORY_ENUM, name="order_category")
    enum.create(bind, checkfirst=True)
    return enum


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    orders_columns = {col["name"]: col for col in inspector.get_columns("orders")}

    # --- add new columns if missing ---
    if "lat" not in orders_columns:
        op.add_column("orders", sa.Column("lat", sa.Numeric(9, 6), nullable=True))
    if "lon" not in orders_columns:
        op.add_column("orders", sa.Column("lon", sa.Numeric(9, 6), nullable=True))
    if "timeslot_start_utc" not in orders_columns:
        op.add_column(
            "orders",
            sa.Column("timeslot_start_utc", sa.DateTime(timezone=True), nullable=True),
        )
    if "timeslot_end_utc" not in orders_columns:
        op.add_column(
            "orders",
            sa.Column("timeslot_end_utc", sa.DateTime(timezone=True), nullable=True),
        )
    if "total_sum" not in orders_columns:
        op.add_column(
            "orders",
            sa.Column("total_sum", sa.Numeric(10, 2), nullable=False, server_default="0"),
        )
    if "cancel_reason" not in orders_columns:
        op.add_column("orders", sa.Column("cancel_reason", sa.Text(), nullable=True))
    if "no_district" not in orders_columns:
        op.add_column(
            "orders",
            sa.Column("no_district", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        )

    # Ensure index ix_orders__status_city exists
    existing_indexes = {idx["name"] for idx in inspector.get_indexes("orders")}
    if "ix_orders__status_city" not in existing_indexes:
        op.create_index("ix_orders__status_city", "orders", ["status", "city_id"])

    # --- ensure category uses ENUM ---
    category_col = orders_columns.get("category")
    enum_created = False
    if category_col is not None and not isinstance(category_col["type"], sa.Enum):
        _create_order_category_enum(bind)
        enum_created = True
        op.execute(
            sa.text(
                "UPDATE orders SET category = UPPER(category) "
                "WHERE category IS NOT NULL"
            )
        )
        op.execute(
            sa.text(
                "ALTER TABLE orders ALTER COLUMN category TYPE order_category "
                "USING CASE WHEN category IS NULL THEN NULL ELSE category::order_category END"
            )
        )

    # --- backfill data ---
    session = Session(bind=bind)
    try:
        if "total_sum" not in orders_columns:
            session.execute(sa.text("UPDATE orders SET total_sum = COALESCE(total_price, 0)"))
        else:
            session.execute(
                sa.text(
                    "UPDATE orders SET total_sum = COALESCE(total_price, 0) "
                    "WHERE total_sum = 0"
                )
            )

        if "lat" not in orders_columns and _has_column(inspector, "orders", "latitude"):
            session.execute(sa.text("UPDATE orders SET lat = latitude WHERE latitude IS NOT NULL"))
        if "lon" not in orders_columns and _has_column(inspector, "orders", "longitude"):
            session.execute(sa.text("UPDATE orders SET lon = longitude WHERE longitude IS NOT NULL"))

        if "no_district" not in orders_columns:
            session.execute(
                sa.text("UPDATE orders SET no_district = TRUE WHERE district_id IS NULL")
            )

        orders = sa.Table("orders", sa.MetaData(), autoload_with=bind)
        if _has_column(inspector, "orders", "timeslot_start_utc"):
            cities_columns = {col["name"] for col in inspector.get_columns("cities")}
            city_tz_map: dict[int, str] = {}
            if "timezone" in cities_columns:
                cities = sa.Table("cities", sa.MetaData(), autoload_with=bind)
                for cid, tz_name in session.execute(sa.select(cities.c.id, cities.c.timezone)):
                    if tz_name:
                        city_tz_map[int(cid)] = tz_name

            utc_zone = ZoneInfo("UTC")
            default_tz = ZoneInfo(os.getenv("TIMEZONE", "Europe/Moscow"))

            select_stmt = sa.select(
                orders.c.id,
                orders.c.city_id,
                orders.c.scheduled_date,
                orders.c.time_slot_start,
                orders.c.time_slot_end,
                orders.c.timeslot_start_utc,
                orders.c.timeslot_end_utc,
            ).where(
                sa.or_(
                    orders.c.time_slot_start.isnot(None),
                    orders.c.time_slot_end.isnot(None),
                )
            )
            result = session.execute(select_stmt)
            for row in result:
                if row.scheduled_date is None:
                    continue
                if row.timeslot_start_utc is not None or row.timeslot_end_utc is not None:
                    continue
                tzinfo = default_tz
                tz_name = city_tz_map.get(row.city_id)
                if tz_name:
                    try:
                        tzinfo = ZoneInfo(tz_name)
                    except Exception:
                        tzinfo = default_tz
                start_utc = None
                end_utc = None
                if row.time_slot_start is not None:
                    local_start = datetime.combine(row.scheduled_date, row.time_slot_start, tzinfo)
                    start_utc = local_start.astimezone(utc_zone)
                if row.time_slot_end is not None:
                    local_end = datetime.combine(row.scheduled_date, row.time_slot_end, tzinfo)
                    end_utc = local_end.astimezone(utc_zone)
                session.execute(
                    orders.update()
                    .where(orders.c.id == row.id)
                    .values(timeslot_start_utc=start_utc, timeslot_end_utc=end_utc)
                )

        session.commit()
    finally:
        session.close()

    op.alter_column("orders", "total_sum", server_default=None)
    op.alter_column("orders", "no_district", server_default=None)

    # cleanup inspector cache by reflecting again (for future migrations)
    if enum_created:
        inspect(bind, raiseerr=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if any(col["name"] == "category" and isinstance(col["type"], sa.Enum) for col in inspector.get_columns("orders")):
        op.execute(
            sa.text(
                "ALTER TABLE orders ALTER COLUMN category TYPE VARCHAR(32) "
                "USING category::TEXT"
            )
        )
        postgresql.ENUM(name="order_category").drop(bind, checkfirst=True)

    if "ix_orders__status_city" in {idx["name"] for idx in inspector.get_indexes("orders")}:
        op.drop_index("ix_orders__status_city", table_name="orders")

    for col_name in (
        "timeslot_start_utc",
        "timeslot_end_utc",
        "cancel_reason",
        "no_district",
        "total_sum",
        "lat",
        "lon",
    ):
        if _has_column(inspector, "orders", col_name):
            op.drop_column("orders", col_name)
