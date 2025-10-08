from __future__ import annotations

import csv
import io
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, AsyncIterator, Iterable, Literal, Optional, Sequence

from openpyxl import Workbook
from openpyxl.utils import get_column_letter
from sqlalchemy import func, select
from sqlalchemy.orm import aliased
from sqlalchemy.ext.asyncio import AsyncSession

from field_service.db import models as m
from field_service.db.session import SessionLocal

UTC = timezone.utc


def get_timezone():
    """Return the local timezone used for exports.

    Provided for tests to monkeypatch. Falls back to UTC on errors.
    """
    try:
        from field_service.services.settings_service import get_timezone as _get_tz

        return _get_tz()
    except Exception:
        # Avoid hard failures if settings are not available in test env
        from zoneinfo import ZoneInfo

        return ZoneInfo("UTC")

ColumnKind = Literal["str", "datetime", "decimal", "int", "float", "bool"]


@dataclass(frozen=True)
class ColumnSpec:
    name: str
    kind: ColumnKind
    precision: int | None = None


@dataclass(slots=True)
class ExportBundle:
    csv_filename: str
    csv_bytes: bytes
    xlsx_filename: str
    xlsx_bytes: bytes


ORDERS_COLUMNS: Sequence[ColumnSpec] = (
    ColumnSpec("order_id", "int"),
    ColumnSpec("created_at_utc", "datetime"),
    ColumnSpec("closed_at_utc", "datetime"),
    ColumnSpec("city", "str"),
    ColumnSpec("district", "str"),
    ColumnSpec("street", "str"),
    ColumnSpec("house", "str"),
    ColumnSpec("lat", "float", precision=6),
    ColumnSpec("lon", "float", precision=6),
    ColumnSpec("category", "str"),
    ColumnSpec("status", "str"),
    ColumnSpec("type", "str"),
    ColumnSpec("timeslot_start_utc", "datetime"),
    ColumnSpec("timeslot_end_utc", "datetime"),
    ColumnSpec("late_visit", "bool"),
    ColumnSpec("company_payment", "int"),
    ColumnSpec("total_sum", "decimal", precision=2),
    ColumnSpec("user_name", "str"),
    ColumnSpec("user_phone", "str"),
    ColumnSpec("master_name", "str"),
    ColumnSpec("master_phone", "str"),
    ColumnSpec("cancel_reason", "str"),
)

COMMISSIONS_COLUMNS: Sequence[ColumnSpec] = (
    ColumnSpec("commission_id", "int"),
    ColumnSpec("order_id", "int"),
    ColumnSpec("master_id", "int"),
    ColumnSpec("master_name", "str"),
    ColumnSpec("master_phone", "str"),
    ColumnSpec("amount", "decimal", precision=2),
    ColumnSpec("rate", "decimal", precision=2),
    ColumnSpec("created_at_utc", "datetime"),
    ColumnSpec("deadline_at_utc", "datetime"),
    ColumnSpec("paid_reported_at_utc", "datetime"),
    ColumnSpec("paid_approved_at_utc", "datetime"),
    ColumnSpec("paid_amount", "decimal", precision=2),
    ColumnSpec("is_paid", "bool"),
    ColumnSpec("has_checks", "bool"),
    ColumnSpec("snapshot_methods", "str"),
    ColumnSpec("snapshot_card_number_last4", "str"),
    ColumnSpec("snapshot_sbp_phone_masked", "str"),
)

REF_REWARDS_COLUMNS: Sequence[ColumnSpec] = (
    ColumnSpec("reward_id", "int"),
    ColumnSpec("master_id", "int"),
    ColumnSpec("order_id", "int"),
    ColumnSpec("commission_id", "int"),
    ColumnSpec("level", "int"),
    ColumnSpec("amount", "decimal", precision=2),
    ColumnSpec("created_at_utc", "datetime"),
)


def _ensure_utc(value: datetime | date, *, end_of_day: bool = False) -> datetime:
    """Convert date or datetime to UTC-aware datetime.
    
    Args:
        value: Date or datetime to convert
        end_of_day: If True and value is date, set time to 23:59:59
    """
    if isinstance(value, date) and not isinstance(value, datetime):
        # Convert date to datetime
        if end_of_day:
            value = datetime.combine(value, datetime.max.time().replace(microsecond=0), tzinfo=UTC)
        else:
            value = datetime.combine(value, datetime.min.time(), tzinfo=UTC)
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _quantize(value: Any, precision: int) -> Decimal:
    quant = Decimal("1").scaleb(-precision)
    return Decimal(value).quantize(quant, rounding=ROUND_HALF_UP)


def _format_csv_value(spec: ColumnSpec, value: Any) -> str:
    if value is None:
        return ""
    if spec.kind == "datetime":
        if isinstance(value, str):
            return value
        return _ensure_utc(value).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    if spec.kind == "decimal":
        precision = spec.precision or 2
        quantized = _quantize(value, precision)
        return f"{quantized:.{precision}f}"
    if spec.kind == "float":
        precision = spec.precision or 6
        quantized = _quantize(value, precision)
        return f"{quantized:.{precision}f}"
    if spec.kind == "int":
        return str(int(value))
    if spec.kind == "bool":
        return "true" if bool(value) else "false"
    return str(value)


def _xlsx_value(spec: ColumnSpec, value: Any) -> Any:
    if value is None:
        return None
    if spec.kind == "datetime":
        if isinstance(value, str):
            return value
        return _ensure_utc(value).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    if spec.kind == "decimal":
        precision = spec.precision or 2
        return _quantize(value, precision)
    if spec.kind == "float":
        precision = spec.precision or 6
        return float(_quantize(value, precision))
    if spec.kind == "int":
        return int(value)
    if spec.kind == "bool":
        return bool(value)
    return value


def _apply_number_formats(ws, columns: Sequence[ColumnSpec]) -> None:
    for idx, spec in enumerate(columns, start=1):
        column_letter = get_column_letter(idx)
        ws.column_dimensions[column_letter].width = max(len(spec.name) + 2, 12)
        if spec.kind not in {"decimal", "float", "int"}:
            continue
        if spec.kind == "int":
            fmt = "0"
        else:
            precision = spec.precision or (6 if spec.kind == "float" else 2)
            fmt = "0" if precision == 0 else "0." + ("0" * precision)
        for cell in ws.iter_rows(min_row=2, min_col=idx, max_col=idx):
            cell[0].number_format = fmt


def _render_csv(columns: Sequence[ColumnSpec], rows: Sequence[dict[str, Any]]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow([spec.name for spec in columns])
    for row in rows:
        writer.writerow([
            _format_csv_value(spec, row.get(spec.name)) for spec in columns
        ])
    return buffer.getvalue().encode("utf-8-sig")


def _render_xlsx(sheet_name: str, columns: Sequence[ColumnSpec], rows: Sequence[dict[str, Any]]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name
    ws.append([spec.name for spec in columns])
    for row in rows:
        ws.append([
            _xlsx_value(spec, row.get(spec.name)) for spec in columns
        ])
    _apply_number_formats(ws, columns)
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def _make_bundle(prefix: str, columns: Sequence[ColumnSpec], rows: Sequence[dict[str, Any]], *, sheet_name: Optional[str] = None) -> ExportBundle:
    sheet = sheet_name or prefix
    csv_bytes = _render_csv(columns, rows)
    xlsx_bytes = _render_xlsx(sheet, columns, rows)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return ExportBundle(
        csv_filename=f"{prefix}_{timestamp}.csv",
        csv_bytes=csv_bytes,
        xlsx_filename=f"{prefix}_{timestamp}.xlsx",
        xlsx_bytes=xlsx_bytes,
    )


@asynccontextmanager
async def _session_scope(session: AsyncSession | None) -> AsyncIterator[AsyncSession]:
    if session is not None:
        yield session
        return
    async with SessionLocal() as new_session:
        yield new_session


async def export_orders(*, date_from: datetime | date, date_to: datetime | date, city_ids: Optional[Iterable[int]] = None, session: AsyncSession | None = None) -> ExportBundle:
    start_utc = _ensure_utc(date_from)
    end_utc = _ensure_utc(date_to, end_of_day=True)
    assigned_master = aliased(m.masters, name="assigned_master")
    city_filter = list(city_ids) if city_ids else None
    async with _session_scope(session) as db:
        stmt = (
            select(
                m.orders.id.label("order_id"),
                m.orders.created_at.label("created_at"),
                m.cities.name.label("city"),
                m.districts.name.label("district"),
                m.streets.name.label("street"),
                m.orders.house.label("house"),
                m.orders.lat.label("lat"),
                m.orders.lon.label("lon"),
                m.orders.category.label("category"),
                m.orders.status.label("status"),
                m.orders.type.label("order_type"),
                m.orders.late_visit.label("late_visit"),
                m.orders.company_payment.label("company_payment"),
                m.orders.total_sum.label("total_sum"),
                m.orders.client_name.label("client_name"),
                m.orders.client_phone.label("client_phone"),
                m.orders.timeslot_start_utc.label("timeslot_start_utc"),
                m.orders.timeslot_end_utc.label("timeslot_end_utc"),
                assigned_master.full_name.label("master_name"),
                assigned_master.phone.label("master_phone"),
                (
                    select(func.max(m.order_status_history.created_at))
                    .where(
                        (m.order_status_history.order_id == m.orders.id)
                        & (m.order_status_history.to_status == m.OrderStatus.CLOSED)
                    )
                ).scalar_subquery().label("closed_at"),
                (
                    select(m.order_status_history.reason)
                    .where(
                        (m.order_status_history.order_id == m.orders.id)
                        & (m.order_status_history.to_status == m.OrderStatus.CANCELED)
                    )
                    .order_by(m.order_status_history.created_at.desc())
                    .limit(1)
                ).scalar_subquery().label("cancel_reason"),
            )
            .join(m.cities, m.orders.city_id == m.cities.id)
            .join(m.districts, m.orders.district_id == m.districts.id, isouter=True)
            .join(m.streets, m.orders.street_id == m.streets.id, isouter=True)
            .join(assigned_master, m.orders.assigned_master_id == assigned_master.id, isouter=True)
            .where(m.orders.created_at >= start_utc, m.orders.created_at <= end_utc)
            .order_by(m.orders.created_at)
        )
        if city_filter:
            stmt = stmt.where(m.orders.city_id.in_(city_filter))
        result = await db.execute(stmt)

        rows: list[dict[str, Any]] = []
        for row in result:
            # Fallback timeslot window if not set
            slot_start = row.timeslot_start_utc
            slot_end = row.timeslot_end_utc
            if slot_start is None or slot_end is None:
                try:
                    tz = get_timezone()
                except Exception:
                    tz = UTC
                base_dt = row.closed_at or getattr(row, "updated_at", None) or row.created_at
                if base_dt is not None:
                    base_local = _ensure_utc(base_dt).astimezone(tz)
                    start_local = base_local.replace(hour=10, minute=0, second=0, microsecond=0)
                    end_local = base_local.replace(hour=13, minute=0, second=0, microsecond=0)
                    slot_start = start_local.astimezone(UTC)
                    slot_end = end_local.astimezone(UTC)
            company_payment = None
            if row.company_payment is not None:
                quantized_payment = _quantize(row.company_payment, 0)
                if quantized_payment != 0:
                    company_payment = int(quantized_payment)
            rows.append(
                {
                    "order_id": int(row.order_id),
                    "created_at_utc": row.created_at,
                    "closed_at_utc": row.closed_at,
                    "city": row.city or "",
                    "district": row.district or "",
                    "street": row.street or "",
                    "house": row.house or "",
                    "lat": row.lat,
                    "lon": row.lon,
                    "category": row.category or "",
                    "status": row.status.value if hasattr(row.status, "value") else str(row.status),
                    "type": row.order_type.value if hasattr(row.order_type, "value") else str(row.order_type),
                    "timeslot_start_utc": slot_start,
                    "timeslot_end_utc": slot_end,
                    "late_visit": bool(row.late_visit),
                    "company_payment": company_payment,
                    "total_sum": row.total_sum,
                    "user_name": row.client_name or "",
                    "user_phone": row.client_phone or "",
                    "master_name": row.master_name or "",
                    "master_phone": row.master_phone or "",
                    "cancel_reason": row.cancel_reason or "",
                }
            )
    return _make_bundle("orders", ORDERS_COLUMNS, rows, sheet_name="orders")


async def export_commissions(*, date_from: datetime | date, date_to: datetime | date, city_ids: Optional[Iterable[int]] = None, session: AsyncSession | None = None) -> ExportBundle:
    start_utc = _ensure_utc(date_from)
    end_utc = _ensure_utc(date_to, end_of_day=True)
    city_filter = list(city_ids) if city_ids else None
    master_alias = aliased(m.masters, name="commission_master")
    checks_subquery = (
        select(func.count(m.attachments.id))
        .where(
            (m.attachments.entity_type == m.AttachmentEntity.COMMISSION),
            (m.attachments.entity_id == m.commissions.id),
        )
        .correlate(m.commissions)
        .scalar_subquery()
    )

    async with _session_scope(session) as db:
        stmt = (
            select(
                m.commissions.id,
                m.commissions.order_id,
                m.commissions.master_id,
                master_alias.full_name,
                master_alias.phone,
                m.commissions.amount,
                m.commissions.rate,
                m.commissions.created_at,
                m.commissions.deadline_at,
                m.commissions.paid_reported_at,
                m.commissions.paid_approved_at,
                m.commissions.paid_amount,
                m.commissions.is_paid,
                checks_subquery.label("checks_count"),
                m.commissions.pay_to_snapshot,
                m.orders.city_id,
            )
            .join(master_alias, master_alias.id == m.commissions.master_id)
            .join(m.orders, m.orders.id == m.commissions.order_id)
            .where(m.commissions.created_at >= start_utc, m.commissions.created_at <= end_utc)
            .order_by(m.commissions.created_at)
        )
        if city_filter:
            stmt = stmt.where(m.orders.city_id.in_(city_filter))
        result = await db.execute(stmt)

        rows: list[dict[str, Any]] = []
        for row in result:
            snapshot = row.pay_to_snapshot or {}
            methods = snapshot.get("methods")
            if isinstance(methods, list):
                methods_value = ",".join(str(item) for item in methods)
            elif methods:
                methods_value = str(methods)
            else:
                methods_value = ""
            rows.append(
                {
                    "commission_id": int(row.id),
                    "order_id": int(row.order_id),
                    "master_id": int(row.master_id),
                    "master_name": row.full_name or "",
                    "master_phone": row.phone or "",
                    "amount": row.amount,
                    "rate": row.rate,
                    "created_at_utc": row.created_at,
                    "deadline_at_utc": row.deadline_at,
                    "paid_reported_at_utc": row.paid_reported_at,
                    "paid_approved_at_utc": row.paid_approved_at,
                    "paid_amount": row.paid_amount,
                    "is_paid": bool(row.is_paid),
                    "has_checks": (row.checks_count or 0) > 0,
                    "snapshot_methods": methods_value,
                    "snapshot_card_number_last4": snapshot.get("card_number_last4") or "",
                    "snapshot_sbp_phone_masked": snapshot.get("sbp_phone_masked") or "",
                }
            )
    return _make_bundle("commissions", COMMISSIONS_COLUMNS, rows, sheet_name="commissions")


async def export_referral_rewards(*, date_from: datetime | date, date_to: datetime | date, city_ids: Optional[Iterable[int]] = None, session: AsyncSession | None = None) -> ExportBundle:
    start_utc = _ensure_utc(date_from)
    end_utc = _ensure_utc(date_to, end_of_day=True)
    city_filter = list(city_ids) if city_ids else None

    async with _session_scope(session) as db:
        stmt = (
            select(
                m.referral_rewards.id,
                m.referral_rewards.referrer_id,
                m.referral_rewards.commission_id,
                m.referral_rewards.level,
                m.referral_rewards.amount,
                m.referral_rewards.created_at,
                m.orders.id.label("order_id"),
                m.orders.city_id,
            )
            .join(m.commissions, m.commissions.id == m.referral_rewards.commission_id)
            .join(m.orders, m.orders.id == m.commissions.order_id)
            .where(m.referral_rewards.created_at >= start_utc, m.referral_rewards.created_at <= end_utc)
            .order_by(m.referral_rewards.created_at)
        )
        if city_filter:
            stmt = stmt.where(m.orders.city_id.in_(city_filter))
        result = await db.execute(stmt)

        rows = [
            {
                "reward_id": int(row.id),
                "master_id": int(row.referrer_id),
                "order_id": int(row.order_id),
                "commission_id": int(row.commission_id),
                "level": int(row.level),
                "amount": row.amount,
                "created_at_utc": row.created_at,
            }
            for row in result
        ]
    return _make_bundle("ref_rewards", REF_REWARDS_COLUMNS, rows, sheet_name="ref_rewards")











