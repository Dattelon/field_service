from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Tuple, Optional
from zoneinfo import ZoneInfo

from sqlalchemy import select, update, insert
from sqlalchemy.ext.asyncio import AsyncSession

from field_service.db import models as m
from field_service.services import settings_service, time_service

UTC = timezone.utc
_DEFERRED_LOGGED: set[int] = set()


@dataclass(slots=True)
class AwakenedOrder:
    order_id: int
    city_name: Optional[str]
    target_local: datetime


@dataclass(slots=True)
class DeferredNotice:
    order_id: int
    city_name: Optional[str]
    target_local: datetime


async def _resolve_city_timezone(session: AsyncSession, city_id: Optional[int]) -> ZoneInfo:
    if not city_id:
        return time_service.resolve_timezone()
    if hasattr(m.cities, "timezone"):
        row = await session.execute(
            select(m.cities.timezone).where(m.cities.id == int(city_id))
        )
        tz_value = row.scalar_one_or_none()
        if tz_value:
            return time_service.resolve_timezone(str(tz_value))
    return time_service.resolve_timezone()


async def run(
    session: AsyncSession,
    *,
    now_utc: datetime,
) -> Tuple[List[AwakenedOrder], List[DeferredNotice]]:
    now_utc = now_utc.astimezone(UTC)
    stmt = (
        select(
            m.orders.id,
            m.orders.city_id,
            m.orders.timeslot_start_utc,
            m.cities.name,
        )
        .join(m.cities, m.cities.id == m.orders.city_id, isouter=True)
        .where(m.orders.status == m.OrderStatus.DEFERRED)
    )
    rows = await session.execute(stmt)
    items = rows.all()
    if not items:
        return [], []

    workday_start, _ = await settings_service.get_working_window()
    awakened: List[AwakenedOrder] = []
    notices: List[DeferredNotice] = []
    tz_cache: dict[int, ZoneInfo] = {}

    for order_id, city_id, start_utc, city_name in items:
        tz = tz_cache.get(city_id)
        if tz is None:
            tz = await _resolve_city_timezone(session, city_id)
            if city_id is not None:
                tz_cache[city_id] = tz
        local_now = now_utc.astimezone(tz)
        if start_utc is not None:
            su = start_utc if getattr(start_utc, "tzinfo", None) is not None else start_utc.replace(tzinfo=UTC)
            target_local = su.astimezone(tz)
        else:
            target_local = datetime.combine(local_now.date(), workday_start, tzinfo=tz)
        if target_local > local_now:
            if order_id not in _DEFERRED_LOGGED:
                _DEFERRED_LOGGED.add(order_id)
                notices.append(
                    DeferredNotice(
                        order_id=int(order_id),
                        city_name=city_name,
                        target_local=target_local,
                    )
                )
            continue

        await session.execute(
            update(m.orders)
            .where(m.orders.id == order_id)
            .values(
                status=m.OrderStatus.SEARCHING,
                updated_at=now_utc,
                dist_escalated_logist_at=None,
                dist_escalated_admin_at=None,
            )
        )
        await session.execute(
            insert(m.order_status_history).values(
                order_id=order_id,
                from_status=m.OrderStatus.DEFERRED,
                to_status=m.OrderStatus.SEARCHING,
                reason="deferred_wakeup",
                changed_by_staff_id=None,
                changed_by_master_id=None,
            )
        )
        _DEFERRED_LOGGED.discard(order_id)
        awakened.append(
            AwakenedOrder(
                order_id=int(order_id),
                city_name=city_name,
                target_local=target_local,
            )
        )

    await session.flush()
    return awakened, notices
