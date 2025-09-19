from __future__ import annotations

from datetime import timedelta, datetime, timezone
from decimal import Decimal

from sqlalchemy import func

from field_service.db import models as m
from field_service.services.settings_service import get_int
from field_service.config import settings


async def create_commission_for_order(session, order: m.orders, master: m.masters) -> m.commissions:
    """Create commission entry for an order according to new rules.

    - For warranty orders (order.status == GUARANTEE before PAYMENT): approve immediately with zero amount.
    - Otherwise create WAIT_PAY with due_at = now + commission_deadline_hours.
    - Persist derived amount from order.total_price (fallback 0).
    """
    amount = Decimal(order.total_price or 0)
    is_warranty = (str(order.status) == "GUARANTEE")

    if is_warranty:
        comm = m.commissions(
            order_id=order.id,
            master_id=master.id,
            amount=Decimal("0.00"),
            status=m.CommissionStatus.APPROVED,
            is_paid=True,
            paid_approved_at=func.now(),
            blocked_applied=False,
        )
        session.add(comm)
        await session.flush()
        return comm

    hours = await get_int("commission_deadline_hours", settings.commission_deadline_hours)
    comm = m.commissions(
        order_id=order.id,
        master_id=master.id,
        amount=amount,
        status=m.CommissionStatus.WAIT_PAY,
        due_at=datetime.now(timezone.utc) + timedelta(hours=int(hours)),
        blocked_applied=False,
    )
    session.add(comm)
    await session.flush()
    return comm
