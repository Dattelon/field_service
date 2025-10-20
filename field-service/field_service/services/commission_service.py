from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from field_service.config import settings
from field_service.db import models as m
from field_service.services import owner_requisites_service as owner_service
from field_service.services.settings_service import get_int

UTC = timezone.utc
LOGGER = logging.getLogger(__name__)
TWO_PLACES = Decimal("0.01")
RATE_THRESHOLD = Decimal("7000")
DEFAULT_RATE_LOW = Decimal("0.50")
DEFAULT_RATE_HIGH = Decimal("0.40")



@dataclass(slots=True, frozen=True)
class CommissionOverdueEvent:
    commission_id: int
    order_id: int
    master_id: int
    master_full_name: str | None


class CommissionService:
    """Business logic around commissions (rate & creation)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def compute_rate(avg_week_check: Decimal | float | int | str | None) -> Decimal:
        """Return commission rate based on master's weekly average."""
        value = _to_decimal(avg_week_check)
        return DEFAULT_RATE_HIGH if value >= RATE_THRESHOLD else DEFAULT_RATE_LOW

    async def create_for_order(self, order_id: int) -> m.commissions | None:
        """Create a commission for *order_id* unless it already exists or is a guarantee order."""
        # Idempotency: if commission already exists, just return it
        existing = await self._session.execute(
            select(m.commissions).where(m.commissions.order_id == order_id)
        )
        commission = existing.scalar_one_or_none()
        if commission is not None:
            return commission

        row = await self._session.execute(
            select(m.orders, m.masters)
            .join(m.masters, m.orders.assigned_master_id == m.masters.id)
            .where(m.orders.id == order_id)
        )
        result = row.one_or_none()
        if result is None:
            raise ValueError(f"order #{order_id} not found or has no assigned master")

        order, master = result
        if _is_guarantee(order):
            LOGGER.info("commission_skip: guarantee order_id=%s", order_id)
            return None

        avg_week_check = await self._get_avg_week_check(master.id)
        rate = self.compute_rate(avg_week_check)

        total = _to_decimal(order.total_sum)
        amount = (total * rate).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

        now = datetime.now(UTC)
        deadline_hours = int(settings.commission_deadline_hours)
        deadline_at = now + timedelta(hours=deadline_hours)

        snapshot = await self._build_owner_snapshot(order=order, master=master)

        commission = m.commissions(
            order_id=order.id,
            master_id=master.id,
            amount=amount,
            rate=rate,
            status=m.CommissionStatus.WAIT_PAY,
            deadline_at=deadline_at,
            is_paid=False,
            has_checks=False,
            pay_to_snapshot=snapshot,
        )
        self._session.add(commission)
        await self._session.flush()

        # Начисляем реферальные бонусы
        from field_service.services import referral_service
        await referral_service.apply_rewards_for_commission(
            self._session,
            commission_id=commission.id,
            master_id=master.id,
            base_amount=commission.amount,
        )

        return commission

    async def _get_avg_week_check(self, master_id: int) -> Decimal:
        week_ago = datetime.now(UTC) - timedelta(days=7)
        stmt = (
            select(func.avg(m.orders.total_sum))
            .where(m.orders.assigned_master_id == master_id)
            .where(m.orders.status == m.OrderStatus.CLOSED)
            .where(m.orders.created_at >= week_ago)
        )
        result = await self._session.execute(stmt)
        value = result.scalar_one_or_none()
        return _to_decimal(value)

    async def _build_owner_snapshot(self, *, order: m.orders, master: m.masters) -> dict[str, Any]:
        requisites = await owner_service.fetch_effective(self._session)
        methods = [item for item in requisites.get("methods", []) if item in owner_service.ALLOWED_METHODS]

        card_number_raw = ''.join(ch for ch in requisites.get("card_number", "") if ch.isdigit())
        card_last4 = card_number_raw[-4:] if card_number_raw else None

        comment_template = requisites.get("comment_template") or ""
        comment = (_render_comment(comment_template, order=order, master=master)).strip()

        snapshot: dict[str, Any] = {
            "methods": methods,
            "card_number_last4": card_last4,
            "card_holder": _empty_to_none(requisites.get("card_holder")),
            "card_bank": _empty_to_none(requisites.get("card_bank")),
            "sbp_phone_masked": _mask_phone(requisites.get("sbp_phone")),
            "sbp_bank": _empty_to_none(requisites.get("sbp_bank")),
            "sbp_qr_file_id": _empty_to_none(requisites.get("sbp_qr_file_id")),
            "other_text": _empty_to_none(requisites.get("other_text")),
            "comment": comment or None,
        }
        return snapshot



def _empty_to_none(value: Any | None) -> str | None:
    if value is None:
        return None
    value_str = str(value).strip()
    return value_str or None


def _mask_phone(phone: str | None) -> str | None:
    if not phone:
        return None
    digits = [ch for ch in phone if ch.isdigit()]
    if len(digits) < 2:
        return phone
    if len(digits) == 11 and digits[0] in {"7", "8"}:
        last_two = ''.join(digits[-2:])
        return f"+7*** *** ** {last_two}"
    masked_part = '*' * max(len(digits) - 2, 0)
    visible = ''.join(digits[-2:])
    return masked_part + visible


def _render_comment(template: str, *, order: m.orders, master: m.masters) -> str:
    if not template:
        return f"Commission #{order.id}"
    return (
        template.replace("<order_id>", str(order.id))
        .replace("<master_fio>", master.full_name or "Unknown")
    )


def _is_guarantee(order: m.orders) -> bool:
    order_type = getattr(order, "type", None)
    if order_type is None:
        order_type = getattr(order, "order_type", None)
    if isinstance(order_type, m.OrderType):
        if order_type is m.OrderType.GUARANTEE:
            return True
    elif isinstance(order_type, str):
        if order_type.upper() == m.OrderType.GUARANTEE.value:
            return True
    if getattr(order, "guarantee_source_order_id", None) is not None:
        return True
    return False


def _to_decimal(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    if isinstance(value, str) and value.strip():
        try:
            return Decimal(value)
        except InvalidOperation:
            return Decimal("0")
    return Decimal("0")


async def apply_overdue_commissions(
    session: AsyncSession, *, now: datetime | None = None
) -> list[CommissionOverdueEvent]:
    """Mark expired WAIT_PAY commissions as OVERDUE and block masters."""

    current_time = now or datetime.now(UTC)

    result = await session.execute(
        select(
            m.commissions.id.label('commission_id'),
            m.commissions.order_id.label('order_id'),
            m.commissions.master_id.label('master_id'),
            m.masters.full_name.label('master_full_name'),
        )
        .join(m.masters, m.masters.id == m.commissions.master_id)
        .where(
            (m.commissions.status == m.CommissionStatus.WAIT_PAY)
            & (m.commissions.deadline_at < current_time)
            & (m.commissions.blocked_applied.is_(False))
        )
        .order_by(m.commissions.id.asc())
        .with_for_update()  # P1: Блокировка для предотвращения race condition
    )
    rows = result.all()
    if not rows:
        return []

    events = [
        CommissionOverdueEvent(
            commission_id=row.commission_id,
            order_id=row.order_id,
            master_id=row.master_id,
            master_full_name=row.master_full_name,
        )
        for row in rows
    ]

    commission_ids = [event.commission_id for event in events]
    master_ids = sorted({event.master_id for event in events})

    await session.execute(
        update(m.commissions)
        .where(m.commissions.id.in_(commission_ids))
        .values(
            status=m.CommissionStatus.OVERDUE,
            blocked_applied=True,
            blocked_at=current_time,
            updated_at=func.now(),
        )
    )

    if master_ids:
        await session.execute(
            update(m.masters)
            .where(m.masters.id.in_(master_ids))
            .values(
                is_blocked=True,
                is_active=False,
                blocked_at=current_time,
                blocked_reason='commission_overdue',
                updated_at=func.now(),
            )
        )

    return events
