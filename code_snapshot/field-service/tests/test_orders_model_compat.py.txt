from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import exc

from field_service.db import models as m


@pytest.mark.asyncio
async def test_orders_persist_v12_fields(async_session) -> None:
    order = m.orders(
        city_id=1,
        status=m.OrderStatus.CREATED,
        type=m.OrderType.GUARANTEE,
        timeslot_start_utc=datetime(2025, 9, 15, 10, 0, tzinfo=timezone.utc),
        timeslot_end_utc=datetime(2025, 9, 15, 12, 0, tzinfo=timezone.utc),
        total_sum=Decimal('123.45'),
        lat=55.123456,
        lon=37.654321,
        no_district=True,
    )
    async_session.add(order)
    await async_session.commit()

    stored = await async_session.get(m.orders, order.id)
    assert stored is not None
    assert stored.type is m.OrderType.GUARANTEE
    assert stored.timeslot_start_utc == datetime(2025, 9, 15, 10, 0, tzinfo=timezone.utc)
    assert stored.timeslot_end_utc == datetime(2025, 9, 15, 12, 0, tzinfo=timezone.utc)
    assert Decimal(stored.total_sum) == Decimal('123.45')
    assert stored.lat == pytest.approx(55.123456)
    assert stored.lon == pytest.approx(37.654321)
    assert stored.no_district is True


@pytest.mark.asyncio
async def test_timeslot_range_constraint(async_session) -> None:
    order = m.orders(
        city_id=1,
        status=m.OrderStatus.CREATED,
        timeslot_start_utc=datetime(2025, 9, 15, 12, 0, tzinfo=timezone.utc),
        timeslot_end_utc=datetime(2025, 9, 15, 10, 0, tzinfo=timezone.utc),
        total_sum=Decimal('1'),
    )
    async_session.add(order)

    with pytest.raises(exc.IntegrityError):
        await async_session.commit()
    await async_session.rollback()


@pytest.mark.asyncio
async def test_total_sum_defaults(async_session) -> None:
    order = m.orders(city_id=1, status=m.OrderStatus.CREATED)
    async_session.add(order)
    await async_session.commit()

    stored = await async_session.get(m.orders, order.id)
    assert Decimal(stored.total_sum) == Decimal('0')
    assert stored.type is m.OrderType.NORMAL
    assert stored.timeslot_start_utc is None
    assert stored.timeslot_end_utc is None
    assert stored.no_district is False
