# field_service/services/guarantee_service.py
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import insert, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from field_service.db import models as m
from field_service.config import settings

UTC = timezone.utc

DEFAULT_GUARANTEE_LABEL = ''.join(chr(code) for code in (1047, 1040, 1071, 1042, 1050, 1040, 32, 1055, 1054, 32, 1043, 1040, 1056, 1040, 1053, 1058, 1048, 1048))


class GuaranteeError(Exception):
    pass


async def create_from_closed_order(
    session: AsyncSession,
    source_order_id: int,
    company_payment: Optional[float] = None,
    *,
    source: Optional[m.orders] = None,
    created_by_staff_id: Optional[int] = None,
    description_prefix: str = DEFAULT_GUARANTEE_LABEL,
) -> m.orders:
    """Create a GUARANTEE order from a CLOSED source order.

    Rules (per §10):
      - company_payment is fixed (env SETTINGS.GUARANTEE_COMPANY_PAYMENT, default 2500).
      - total_sum = 0.
      - commission for this order must be 0 later.
      - first offer goes to previous master (preferred_master_id).
      - If prev master refuses or times out -> auto-block.

    Persist:
      orders.status = 'GUARANTEE'
      orders.company_payment = company_payment
      orders.preferred_master_id = source.assigned_master_id
      orders.guarantee_source_order_id = source.id
    """
    cp_value: Decimal
    if company_payment is None:
        try:
            cp_value = Decimal(str(getattr(settings, "guarantee_company_payment")))
        except Exception:
            cp_value = Decimal("2500")
    else:
        cp_value = Decimal(str(company_payment))

    if source is None:
        src = await session.execute(select(m.orders).where(m.orders.id == source_order_id))
        source = src.scalar_one_or_none()
    if source is None:
        raise GuaranteeError(f"source order #{source_order_id} not found")
    status_val = getattr(source, "status", None)
    if isinstance(status_val, m.OrderStatus):
        status_is_closed = status_val == m.OrderStatus.CLOSED
    else:
        status_is_closed = str(status_val).upper() == "CLOSED"
    if not status_is_closed:
        raise GuaranteeError("source order must be CLOSED")
    if getattr(source, "type", None) == m.OrderType.GUARANTEE:
        raise GuaranteeError("source order is already guarantee")
    if not source.assigned_master_id:
        raise GuaranteeError("source order has no assigned master")

    description_prefix = description_prefix.strip()
    source_description = (source.description or "").strip()
    if description_prefix and source_description:
        if not source_description.startswith(description_prefix):
            description = f"{description_prefix}\n{source_description}"
        else:
            description = source_description
    elif description_prefix:
        description = description_prefix
    else:
        description = source_description

    new_order = m.orders(
        city_id=source.city_id,
        district_id=source.district_id,
        street_id=source.street_id,
        house=source.house,
        apartment=source.apartment,
        address_comment=source.address_comment,
        client_name=source.client_name,
        client_phone=source.client_phone,
        category=source.category,
        description=description,
        status=m.OrderStatus.GUARANTEE if hasattr(m, "OrderStatus") else "GUARANTEE",
        type=m.OrderType.GUARANTEE if hasattr(m, "OrderType") else "GUARANTEE",
        timeslot_start_utc=None,
        timeslot_end_utc=None,
        preferred_master_id=source.assigned_master_id,
        assigned_master_id=None,
        total_sum=Decimal("0"),
        company_payment=cp_value,
        guarantee_source_order_id=source.id,
        created_by_staff_id=created_by_staff_id,
        lat=getattr(source, "lat", None),
        lon=getattr(source, "lon", None),
        no_district=getattr(source, "no_district", False),
    )
    session.add(new_order)
    await session.flush()

    await session.execute(
        insert(m.order_status_history).values(
            order_id=new_order.id,
            from_status=None,
            to_status=m.OrderStatus.GUARANTEE,
            reason="guarantee_created",
            changed_by_staff_id=created_by_staff_id,
            actor_type=m.ActorType.ADMIN if created_by_staff_id else m.ActorType.SYSTEM,
            context={
                "action": "guarantee_order_creation",
                "source_order_id": source_order_id,
                "created_by_staff_id": created_by_staff_id,
                "order_type": "GUARANTEE"
            },
            created_at=datetime.now(UTC),
        )
    )

    return new_order

