"""
DEBUG тест для диагностики проблемы с эскалацией к админу
"""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from field_service.db import models as m
from field_service.db.session import SessionLocal
from field_service.services.distribution_scheduler import tick_once, DistConfig


async def _get_db_now(session: AsyncSession) -> datetime:
    """Получает текущее время из БД"""
    row = await session.execute(text("SELECT NOW()"))
    return row.scalar()


@pytest.fixture(scope="function")
async def session():
    """Создаёт новую сессию БД для каждого теста"""
    async with SessionLocal() as session:
        try:
            yield session
        finally:
            await session.rollback()


@pytest.fixture(scope="function")
async def clean_db(session: AsyncSession):
    """Очищает БД перед каждым тестом"""
    try:
        await session.execute(text("TRUNCATE TABLE offers CASCADE"))
        await session.execute(text("TRUNCATE TABLE orders CASCADE"))
        await session.execute(text("TRUNCATE TABLE master_skills CASCADE"))
        await session.execute(text("TRUNCATE TABLE master_districts CASCADE"))
        await session.execute(text("TRUNCATE TABLE masters CASCADE"))
        await session.execute(text("TRUNCATE TABLE skills CASCADE"))
        await session.execute(text("TRUNCATE TABLE districts CASCADE"))
        await session.execute(text("TRUNCATE TABLE cities CASCADE"))
        await session.commit()
    except Exception:
        await session.rollback()
        await session.execute(m.offers.__table__.delete())
        await session.execute(m.orders.__table__.delete())
        await session.execute(m.master_skills.__table__.delete())
        await session.execute(m.master_districts.__table__.delete())
        await session.execute(m.masters.__table__.delete())
        await session.execute(m.skills.__table__.delete())
        await session.execute(m.districts.__table__.delete())
        await session.execute(m.cities.__table__.delete())
        await session.commit()


@pytest.fixture(scope="function")
async def sample_city(session: AsyncSession, clean_db):
    """Создаёт тестовый город"""
    city = m.cities(
        name="Test City",
        timezone="Europe/Moscow",
        is_active=True,
    )
    session.add(city)
    await session.commit()
    await session.refresh(city)
    return city


@pytest.fixture(scope="function")
async def sample_district(session: AsyncSession, sample_city):
    """Создаёт тестовый район"""
    district = m.districts(
        city_id=sample_city.id,
        name="Test District",
    )
    session.add(district)
    await session.commit()
    await session.refresh(district)
    return district


@pytest.fixture(scope="function")
async def sample_skill(session: AsyncSession):
    """Создаёт тестовый навык"""
    skill = m.skills(
        code="ELEC",
        name="Электрика",
        is_active=True,
    )
    session.add(skill)
    await session.commit()
    await session.refresh(skill)
    return skill


@pytest.mark.asyncio
async def test_debug_admin_escalation(
    session: AsyncSession,
    sample_city,
    sample_district,
    sample_skill,
):
    """
    DEBUG тест: Проверяем почему эскалация к админу не срабатывает
    """
    # Создаём заказ с эскалацией к логисту (15 минут назад)
    db_now = await _get_db_now(session)
    escalation_time = db_now - timedelta(minutes=15)
    notification_time = db_now - timedelta(minutes=14)
    
    print(f"\n[DEBUG] Текущее время БД: {db_now}")
    print(f"[DEBUG] Время эскалации к логисту: {escalation_time}")
    print(f"[DEBUG] Прошло минут: {(db_now - escalation_time).total_seconds() / 60:.2f}")
    
    order = m.orders(
        status=m.OrderStatus.SEARCHING,
        city_id=sample_city.id,
        district_id=sample_district.id,
        category=m.OrderCategory.ELECTRICS,
        house="1",
        timeslot_start_utc=db_now + timedelta(hours=2),
        timeslot_end_utc=db_now + timedelta(hours=4),
        dist_escalated_logist_at=escalation_time,
        escalation_logist_notified_at=notification_time,
    )
    session.add(order)
    await session.commit()
    await session.refresh(order)
    
    print(f"\n[DEBUG] Создан заказ ID={order.id}")
    print(f"[DEBUG] status={order.status}")
    print(f"[DEBUG] city_id={order.city_id}")
    print(f"[DEBUG] district_id={order.district_id}")
    print(f"[DEBUG] category={order.category}")
    print(f"[DEBUG] house={order.house}")
    print(f"[DEBUG] no_district={order.no_district}")
    print(f"[DEBUG] dist_escalated_logist_at={order.dist_escalated_logist_at}")
    print(f"[DEBUG] dist_escalated_admin_at={order.dist_escalated_admin_at}")

    # Проверяем что заказ будет выбран для распределения
    result = await session.execute(text("""
        SELECT id, status, district_id, no_district, category
        FROM orders
        WHERE status IN ('SEARCHING','GUARANTEE')
        AND assigned_master_id IS NULL
    """))
    rows = result.fetchall()
    print(f"\n[DEBUG] Заказы в очереди распределения: {len(rows)}")
    for row in rows:
        print(f"  - order_id={row[0]}, status={row[1]}, district_id={row[2]}, no_district={row[3]}, category={row[4]}")

    # Запускаем tick_once()
    cfg = DistConfig(
        tick_seconds=30,
        sla_seconds=120,
        rounds=2,
        top_log_n=10,
        to_admin_after_min=10,
    )
    
    print("\n[DEBUG] Запускаем tick_once()...")
    await tick_once(cfg, bot=None, alerts_chat_id=None, session=session)
    
    # Проверяем результат
    session.expire_all()
    await session.refresh(order)
    
    print(f"\n[DEBUG] После tick_once():")
    print(f"[DEBUG] dist_escalated_admin_at={order.dist_escalated_admin_at}")
    print(f"[DEBUG] escalation_admin_notified_at={order.escalation_admin_notified_at}")
    
    if order.dist_escalated_admin_at is None:
        print("\n❌ ПРОБЛЕМА: Эскалация к админу НЕ произошла!")
        print("   Проверяем условия:")
        print(f"   - escalated_logist_at is not None: {order.dist_escalated_logist_at is not None}")
        print(f"   - escalated_admin_at is None: {order.dist_escalated_admin_at is None}")
        print(f"   - Прошло >= 10 минут: {(db_now - escalation_time).total_seconds() >= 600}")
    else:
        print(f"\n✅ Эскалация к админу ПРОИЗОШЛА!")
        print(f"   Timestamp: {order.dist_escalated_admin_at}")
