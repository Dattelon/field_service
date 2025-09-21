from __future__ import annotations

from datetime import timedelta, datetime, timezone
from decimal import Decimal
from typing import Sequence

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from field_service.db import models as m
from field_service.services.settings_service import get_int
from field_service.config import settings

UTC = timezone.utc


def _is_guarantee(order: m.orders) -> bool:
    # Prefer structural flag if present
    if (
        hasattr(order, "guarantee_source_order_id")
        and getattr(order, "guarantee_source_order_id") is not None
    ):
        return True
    # Fallback: status == 'GUARANTEE' for newly created warranty orders
    return str(getattr(order, "status", "")) == "GUARANTEE"


async def create_commission_for_order(
    session: AsyncSession, order: m.orders, master: m.masters
) -> m.commissions | None:
    """Create commission entry for an order according to v1.2 rules.

    - For warranty orders: no deduction for the master. We record a zero commission approved immediately,
      so it appears in reports but never blocks the master.
    - For normal orders: compute amount = total_price * rate (0.5 or 0.4), WAIT_PAY with deadline.
    """
    now = datetime.now(UTC)
    if _is_guarantee(order):
        # zero, approved
        comm = m.commissions(
            order_id=order.id,
            master_id=master.id,
            amount=Decimal("0.00"),
            rate=Decimal("0.00"),
            status=m.CommissionStatus.APPROVED,
            deadline_at=now,
            paid_reported_at=now,
            paid_approved_at=now,
            paid_amount=Decimal("0.00"),
            is_paid=True,
            has_checks=False,
            pay_to_snapshot={"methods": [], "comment": f"Гарантия #{order.id}"},
            blocked_applied=False,
        )
        session.add(comm)
        await session.flush()
        return comm

    # NORMAL: compute rate by avg_week_check (last 7d over closed orders)
    rate = Decimal("0.50")
    # avg_week_check placeholder — use 7d average from orders table if available
    # (we keep it simple here to avoid heavy queries in this snippet)
    q = await session.execute(
        func.coalesce(
            func.avg(m.orders.total_price).filter(
                (m.orders.assigned_master_id == master.id)
                & (
                    m.orders.status.in_(
                        [m.OrderStatus.PAYMENT.value, m.OrderStatus.CLOSED.value]
                    )
                )
            ),
            0,
        )
    )
    avg7 = Decimal(q.scalar() or 0)
    if avg7 >= Decimal("7000"):
        rate = Decimal("0.40")

    amount = (Decimal(order.total_price or 0) * rate).quantize(Decimal("0.01"))

    hours = await get_int(
        "commission_deadline_hours", settings.commission_deadline_hours
    )
    comm = m.commissions(
        order_id=order.id,
        master_id=master.id,
        amount=amount,
        rate=rate,
        status=m.CommissionStatus.WAIT_PAY,
        deadline_at=now + timedelta(hours=int(hours)),
        blocked_applied=False,
        has_checks=False,
        is_paid=False,
        pay_to_snapshot={},  # snapshot is filled by caller from owner settings
    )
    session.add(comm)
    await session.flush()
    return comm


async def apply_overdue_commissions(
    session: AsyncSession, *, now: datetime | None = None
) -> Sequence[int]:
    """Mark expired WAIT_PAY commissions as OVERDUE and block masters."""

    current_time = now or datetime.now(UTC)

    result = await session.execute(
        select(m.commissions.id, m.commissions.master_id).where(
            (m.commissions.status == m.CommissionStatus.WAIT_PAY)
            & (m.commissions.deadline_at < current_time)
            & (m.commissions.blocked_applied.is_(False))
        )
    )
    rows = result.all()
    if not rows:
        return []

    commission_ids = [row.id for row in rows]
    master_ids = sorted({row.master_id for row in rows if row.master_id is not None})

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
                blocked_at=current_time,
                blocked_reason="commission_overdue",
            )
        )

    return master_ids
