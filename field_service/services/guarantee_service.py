# field_service/services/guarantee_service.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from field_service.db import models as m
from field_service.config import settings

UTC = timezone.utc


class GuaranteeError(Exception):
    pass


async def create_from_closed_order(
    session: AsyncSession, source_order_id: int, company_payment: Optional[float] = None
) -> m.orders:
    """Create a GUARANTEE order from a CLOSED source order.

    Rules (per §10):
      - company_payment is fixed (env SETTINGS.GUARANTEE_COMPANY_PAYMENT, default 2500).
      - total_sum (total_price) = 0.
      - commission for this order must be 0 later.
      - first offer goes to previous master (preferred_master_id).
      - If prev master refuses or times out -> auto-block.

    Persist:
      orders.status = 'GUARANTEE'
      orders.company_payment = company_payment
      orders.preferred_master_id = source.assigned_master_id
      orders.guarantee_source_order_id = source.id
    """
    if company_payment is None:
        try:
            cp = float(getattr(settings, "guarantee_company_payment"))
        except Exception:
            cp = 2500.0
    else:
        cp = float(company_payment)

    src = await session.execute(select(m.orders).where(m.orders.id == source_order_id))
    source = src.scalar_one_or_none()
    if source is None:
        raise GuaranteeError(f"source order #{source_order_id} not found")
    if str(source.status) != "CLOSED":
        raise GuaranteeError("source order must be CLOSED")

    # insert new order
    new_order = m.orders(
        city_id=source.city_id,
        district_id=source.district_id,
        street_id=source.street_id,
        house=source.house,
        apartment=source.apartment,
        address_comment=source.address_comment,
        client_name=source.client_name,
        client_phone=source.client_phone,
        status=m.OrderStatus.GUARANTEE if hasattr(m, "OrderStatus") else "GUARANTEE",
        scheduled_date=None,
        time_slot_start=None,
        time_slot_end=None,
        slot_label=None,
        preferred_master_id=source.assigned_master_id,
        assigned_master_id=None,
        total_price=0,
        company_payment=cp,
        guarantee_source_order_id=source.id,
    )
    session.add(new_order)
    await session.flush()

    # status history
    await session.execute(
        text(
            """
        INSERT INTO order_status_history(order_id, from_status, to_status, created_at)
        VALUES (:oid, NULL, 'GUARANTEE', NOW())
        """
        ).bindparams(oid=new_order.id)
    )

    return new_order
