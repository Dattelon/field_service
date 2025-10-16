# tests/test_distribution_scheduler.py
# CR-2025-10-03-010: Migrated from distribution_worker to distribution_scheduler

from datetime import datetime, time, timezone, timedelta
from zoneinfo import ZoneInfo
from unittest.mock import AsyncMock

import pytest
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert

from field_service.db import models as m
from field_service.services.distribution import wakeup
from field_service.services import distribution_scheduler


@pytest.mark.asyncio
async def test_wakeup_promotes_at_start(async_session, monkeypatch):
    """Test that DEFERRED orders are promoted to SEARCHING at timeslot start."""
    await async_session.execute(
        m.cities.__table__.insert().values(id=1, name="Test City", is_active=True)
    )
    await async_session.execute(
        m.orders.__table__.insert().values(
            id=100,
            city_id=1,
            status=m.OrderStatus.DEFERRED,
            timeslot_start_utc=datetime(2025, 9, 15, 10, 0, tzinfo=timezone.utc),
            timeslot_end_utc=datetime(2025, 9, 15, 12, 0, tzinfo=timezone.utc),
        )
    )
    await async_session.commit()

    monkeypatch.setattr(
        wakeup.settings_service,
        "get_working_window",
        AsyncMock(return_value=(time(10, 0), time(20, 0))),
    )
    monkeypatch.setattr(
        wakeup, "_resolve_city_timezone",
        AsyncMock(return_value=ZoneInfo("UTC")),
    )

    now_utc = datetime(2025, 9, 15, 10, 0, tzinfo=timezone.utc)
    awakened, notices = await wakeup.run(async_session, now_utc=now_utc)

    assert notices == []
    assert len(awakened) == 1
    assert awakened[0].order_id == 100
    assert awakened[0].city_name == "Test City"
    assert awakened[0].target_local.tzinfo == ZoneInfo("UTC")

    order = await async_session.get(m.orders, 100)
    assert order.status == m.OrderStatus.SEARCHING

    history_rows = await async_session.execute(
        m.order_status_history.__table__.select().where(
            m.order_status_history.order_id == 100
        )
    )
    history = history_rows.mappings().all()
    assert history and history[-1]["to_status"] == m.OrderStatus.SEARCHING


@pytest.mark.asyncio
async def test_wakeup_notices_only_once(async_session, monkeypatch):
    """Test that wakeup notices for DEFERRED orders are logged only once."""
    await async_session.execute(
        m.cities.__table__.insert().values(id=2, name="Another City", is_active=True)
    )
    await async_session.execute(
        m.orders.__table__.insert().values(
            id=200,
            city_id=2,
            status=m.OrderStatus.DEFERRED,
            timeslot_start_utc=datetime(2025, 9, 15, 10, 0, tzinfo=timezone.utc),
            timeslot_end_utc=datetime(2025, 9, 15, 12, 0, tzinfo=timezone.utc),
        )
    )
    await async_session.commit()

    monkeypatch.setattr(
        wakeup.settings_service,
        "get_working_window",
        AsyncMock(return_value=(time(10, 0), time(20, 0))),
    )
    monkeypatch.setattr(
        wakeup, "_resolve_city_timezone",
        AsyncMock(return_value=ZoneInfo("UTC")),
    )

    before_start = datetime(2025, 9, 15, 8, 0, tzinfo=timezone.utc)
    awakened, notices = await wakeup.run(async_session, now_utc=before_start)
    assert awakened == []
    assert len(notices) == 1
    assert notices[0].order_id == 200

    # Second invocation before start should not duplicate notice
    awakened2, notices2 = await wakeup.run(async_session, now_utc=before_start)
    assert awakened2 == []
    assert notices2 == []

    at_start = datetime(2025, 9, 15, 10, 0, tzinfo=timezone.utc)
    awakened3, notices3 = await wakeup.run(async_session, now_utc=at_start)
    assert notices3 == []
    assert any(order.order_id == 200 for order in awakened3)
    assert wakeup._DEFERRED_LOGGED == set()


@pytest.mark.asyncio
async def test_wakeup_uses_city_timezone(async_session, monkeypatch) -> None:
    """Test that wakeup respects city-specific timezone settings."""
    await async_session.execute(
        m.cities.__table__.insert().values(
            id=3,
            name="Zone City",
            is_active=True,
            timezone="Asia/Yekaterinburg",
        )
    )
    await async_session.execute(
        m.orders.__table__.insert().values(
            id=300,
            city_id=3,
            status=m.OrderStatus.DEFERRED,
            timeslot_start_utc=None,
            timeslot_end_utc=None,
        )
    )
    await async_session.commit()

    monkeypatch.setattr(
        wakeup.settings_service,
        "get_working_window",
        AsyncMock(return_value=(time(10, 0), time(20, 0))),
    )
    wakeup._DEFERRED_LOGGED.clear()

    now_utc = datetime(2025, 9, 15, 5, 0, tzinfo=timezone.utc)
    awake, notices = await wakeup.run(async_session, now_utc=now_utc)

    assert not notices
    assert len(awake) == 1
    assert awake[0].order_id == 300
    assert awake[0].target_local.tzinfo == ZoneInfo("Asia/Yekaterinburg")


@pytest.mark.asyncio
async def test_distribution_escalates_when_no_candidates(async_session):
    """Test that orders escalate to logist when no candidates available."""
    # Setup: Create city, district, but NO masters with required skills
    city = m.cities(name="Escalate City", is_active=True)
    district = m.districts(city=city, name="North")
    async_session.add_all([city, district])
    await async_session.flush()

    order = m.orders(
        city_id=city.id,
        district_id=district.id,
        status=m.OrderStatus.SEARCHING,
        category="ELECTRICS",
        type=m.OrderType.NORMAL,
        no_district=False,
    )
    async_session.add(order)
    await async_session.commit()

    # Create config with test settings
    cfg = distribution_scheduler.DistConfig(
        tick_seconds=30,
        sla_seconds=120,
        rounds=2,
        top_log_n=10,
        to_admin_after_min=10,
    )

    # Run distribution tick
    await distribution_scheduler.tick_once(cfg, bot=None, alerts_chat_id=None)

    # Verify order was escalated to logist (no candidates scenario)
    refreshed = await async_session.get(m.orders, order.id)
    assert refreshed.dist_escalated_logist_at is not None


@pytest.mark.asyncio  
async def test_distribution_sends_offer_when_candidates_exist(async_session):
    """Test that distribution sends offers when valid candidates exist."""
    # Setup: Create city, district, skill, and qualified master
    city = m.cities(name="Offer City", is_active=True)
    district = m.districts(city=city, name="Central")
    skill = m.skills(code="ELEC", name="Electrics", is_active=True)
    async_session.add_all([city, district, skill])
    await async_session.flush()

    master = m.masters(
        full_name="Test Master",
        phone="+70000000001",
        city_id=city.id,
        has_vehicle=True,
        rating=4.5,
        is_active=True,
        is_blocked=False,
        is_on_shift=True,
        verified=True,
    )
    async_session.add(master)
    await async_session.flush()

    # Link master to district and skill
    async_session.add_all([
        m.master_districts(master_id=master.id, district_id=district.id),
        m.master_skills(master_id=master.id, skill_id=skill.id),
    ])

    order = m.orders(
        city_id=city.id,
        district_id=district.id,
        status=m.OrderStatus.SEARCHING,
        category="ELECTRICS",
        type=m.OrderType.NORMAL,
        no_district=False,
    )
    async_session.add(order)
    await async_session.commit()

    cfg = distribution_scheduler.DistConfig(
        tick_seconds=30,
        sla_seconds=120,
        rounds=2,
        top_log_n=10,
        to_admin_after_min=10,
    )

    # Run distribution tick
    await distribution_scheduler.tick_once(cfg, bot=None, alerts_chat_id=None)

    # Verify offer was sent
    offer_rows = await async_session.execute(
        sa.select(m.offers).where(m.offers.order_id == order.id)
    )
    offers = offer_rows.scalars().all()
    
    assert len(offers) == 1
    assert offers[0].master_id == master.id
    assert offers[0].state == m.OfferState.SENT
    assert offers[0].round_number == 1


@pytest.mark.asyncio
async def test_distribution_config_loads_from_settings(async_session):
    """Test that DistConfig properly loads values from settings."""
    # Сбрасываем кэш перед тестом
    distribution_scheduler._CONFIG_CACHE = None
    distribution_scheduler._CONFIG_CACHE_TIMESTAMP = None
    
    # Используем ON CONFLICT DO UPDATE вместо простого INSERT
    settings_data = [
        {"key": "distribution_sla_seconds", "value": "180"},
        {"key": "distribution_rounds", "value": "3"},
        {"key": "escalate_to_admin_after_min", "value": "15"},
    ]
    
    for setting in settings_data:
        stmt = pg_insert(m.settings).values(**setting)
        stmt = stmt.on_conflict_do_update(
            index_elements=["key"],
            set_={"value": stmt.excluded.value}
        )
        await async_session.execute(stmt)
    
    await async_session.commit()

    cfg = await distribution_scheduler._load_config(session=async_session)

    assert cfg.sla_seconds == 180
    assert cfg.rounds == 3
    assert cfg.to_admin_after_min == 15
