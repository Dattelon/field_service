from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from field_service.bots.admin_bot.services_db import (
    DBFinanceService,
    DBOrdersService,
    DBSettingsService,
)
from field_service.db import models as m

UTC = timezone.utc


def _tables(*items):
    return list(items)


async def _ensure_tables(session, tables):
    def _create(sync_session):
        for table in tables:
            table.create(sync_session.bind, checkfirst=True)

    await session.run_sync(_create)


@asynccontextmanager
async def existing_session(session):
    yield session


@pytest.mark.asyncio
async def test_list_cities_and_districts(async_session) -> None:
    await _ensure_tables(async_session, _tables(m.districts.__table__))
    city = m.cities(name="Sample City")
    async_session.add(city)
    await async_session.flush()

    district = m.districts(city_id=city.id, name="Central")
    async_session.add(district)
    await async_session.commit()

    orders_service = DBOrdersService(session_factory=lambda: existing_session(async_session))
    cities = await orders_service.list_cities(limit=10)
    assert any(c.name == "Sample City" for c in cities)

    districts, has_next = await orders_service.list_districts(city.id, page=1, page_size=5)
    assert has_next is False
    assert any(d.name == "Central" for d in districts)


@pytest.mark.asyncio
async def test_search_streets(async_session) -> None:
    await _ensure_tables(async_session, _tables(m.districts.__table__, m.streets.__table__))
    city = m.cities(name="Street City")
    async_session.add(city)
    await async_session.flush()

    district = m.districts(city_id=city.id, name="District")
    async_session.add(district)
    await async_session.flush()

    street = m.streets(city_id=city.id, district_id=district.id, name="Baker Street")
    async_session.add(street)
    await async_session.commit()

    orders_service = DBOrdersService(session_factory=lambda: existing_session(async_session))
    results = await orders_service.search_streets(city.id, "Baker")
    assert any(r.name == "Baker Street" for r in results)


@pytest.mark.asyncio
async def test_commission_detail(async_session) -> None:
    await _ensure_tables(async_session, _tables(m.attachments.__table__))
    city = m.cities(name="Finance City")
    async_session.add(city)
    await async_session.flush()

    master = m.masters(
        tg_user_id=555,
        full_name="Finance Master",
        phone="+79990000001",
        city_id=city.id,
        is_active=True,
        is_on_shift=True,
        verified=True,
        shift_status=m.ShiftStatus.SHIFT_ON,
        moderation_status=m.ModerationStatus.APPROVED,
    )
    async_session.add(master)
    await async_session.flush()

    order = m.orders(
        city_id=city.id,
        district_id=None,
        status=m.OrderStatus.PAYMENT,
        total_price=Decimal("2000"),
        assigned_master_id=master.id,
        client_name="Client",
        client_phone="+79990000002",
    )
    async_session.add(order)
    await async_session.flush()

    commission = m.commissions(
        order_id=order.id,
        master_id=master.id,
        amount=Decimal("1000"),
        rate=Decimal("0.5"),
        status=m.CommissionStatus.WAIT_PAY,
        deadline_at=datetime.now(UTC) + timedelta(hours=1),
        has_checks=True,
        pay_to_snapshot={"methods": ["card"], "card_number": "1234123412341234"},
    )
    async_session.add(commission)
    await async_session.flush()

    attachment = m.attachments(
        entity_type=m.AttachmentEntity.COMMISSION,
        entity_id=commission.id,
        file_type=m.AttachmentFileType.DOCUMENT,
        file_id="file-id",
        file_name="check.pdf",
    )
    async_session.add(attachment)
    await async_session.commit()

    finance_service = DBFinanceService(session_factory=lambda: existing_session(async_session))
    detail = await finance_service.get_commission_detail(commission.id)
    assert detail is not None
    assert detail.amount == Decimal("1000")
    assert detail.attachments and detail.attachments[0].file_name == "check.pdf"
    assert "card" in detail.snapshot_methods


@pytest.mark.asyncio
async def test_db_settings_set_and_channels(async_session) -> None:
    service = DBSettingsService(session_factory=lambda: existing_session(async_session))
    await service.set_value("alerts_channel_id", "321", value_type="STR")
    await service.set_value("logs_channel_id", "", value_type="STR")

    values = await service.get_values(["alerts_channel_id", "logs_channel_id"])
    assert values["alerts_channel_id"][0] == "321"
    assert values["logs_channel_id"][0] == ""

    channels = await service.get_channel_settings()
    assert channels["alerts_channel_id"] == 321
    assert channels["logs_channel_id"] is None


def test_live_log_buffer() -> None:
    from field_service.services import live_log

    live_log.clear()
    live_log.push("dist", "message", level="INFO")
    entries = live_log.snapshot(10)
    assert entries
    assert entries[-1].message == "message"
    assert live_log.size() == 1
    live_log.clear()
    assert live_log.size() == 0
