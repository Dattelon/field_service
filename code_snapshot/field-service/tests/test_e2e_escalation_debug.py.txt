# -*- coding: utf-8 -*-
"""
DEBUG тест для диагностики проблемы с эскалацией к админу
"""
from datetime import datetime, timedelta
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from field_service.db import models as m
from field_service.services.distribution_scheduler import tick_once, DistConfig
async def _get_db_now(session: AsyncSession) -> datetime:
    """Получает текущее время из БД"""
    row = await session.execute(text("SELECT NOW()"))
    return row.scalar()
@pytest.mark.asyncio
async def test_debug_admin_escalation(
    async_session: AsyncSession,
):
    """
    DEBUG: минимальный сценарий, использует транзакционную изоляцию из conftest.py
    """
    db_now = await _get_db_now(async_session)
    escalation_time = db_now - timedelta(minutes=15)
    notification_time = db_now - timedelta(minutes=14)
    # создаём минимально необходимые сущности
    city = m.cities(name="Test City", timezone="Europe/Moscow", is_active=True)
    async_session.add(city)
    await async_session.flush()
    district = m.districts(city_id=city.id, name="Test District")
    async_session.add(district)
    await async_session.flush()
    skill = m.skills(code="ELEC", name="Электрика", is_active=True)
    async_session.add(skill)
    await async_session.flush()
    order = m.orders(
        status=m.OrderStatus.SEARCHING,
        city_id=city.id,
        district_id=district.id,
        category=m.OrderCategory.ELECTRICS,
        house="1",
        timeslot_start_utc=db_now + timedelta(hours=2),
        timeslot_end_utc=db_now + timedelta(hours=4),
        dist_escalated_logist_at=escalation_time,
        escalation_logist_notified_at=notification_time,
    )
    async_session.add(order)
    await async_session.commit()
    await async_session.refresh(order)
    # sanity чек
    res = await async_session.execute(text("""
        SELECT id, status
        FROM orders
        WHERE id = :oid
    """), {"oid": order.id})
    row = res.first()
    assert row is not None
    # Single tick
    cfg = DistConfig()
    await tick_once(cfg, session=async_session)
    # здесь могут быть дополнительные проверки статуса/уведомлений
    # но сам факт выполнения без зависаний уже критичен
