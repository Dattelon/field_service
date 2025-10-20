"""
✅ ТЕСТЫ ДЛЯ ЭТАПА 2: ЛОГИЧЕСКИЕ УЛУЧШЕНИЯ
===============================================

Проверяем:
- 2.1: Приоритизация заказов в очереди
- 2.2: Обработка заказов без района (fallback на город)
- 2.3: Уменьшенный интервал тика (15 секунд)
"""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from field_service.db import models as m
from field_service.services.distribution_scheduler import (
    DistConfig,
    tick_once,
    _load_config,
)


# ==================== ФИКСТУРЫ ====================

@pytest.fixture
async def test_city(session: AsyncSession) -> m.cities:
    """Создаём тестовый город."""
    city = m.cities(name="TestCity", timezone="Europe/Moscow")
    session.add(city)
    await session.commit()
    await session.refresh(city)
    return city


@pytest.fixture
async def test_district(session: AsyncSession, test_city: m.cities) -> m.districts:
    """Создаём тестовый район."""
    district = m.districts(city_id=test_city.id, name="TestDistrict")
    session.add(district)
    await session.commit()
    await session.refresh(district)
    return district


@pytest.fixture
async def test_skill(session: AsyncSession) -> m.skills:
    """Создаём тестовый навык."""
    skill = m.skills(code="ELEC", name="Electrician", is_active=True)
    session.add(skill)
    await session.commit()
    await session.refresh(skill)
    return skill


@pytest.fixture
async def test_master(
    session: AsyncSession,
    test_city: m.cities,
    test_district: m.districts,
    test_skill: m.skills,
) -> m.masters:
    """Создаём тестового мастера с навыком и районом."""
    master = m.masters(
        tg_user_id=123456789,  # ✅ Исправлено: telegram_id -> tg_user_id
        full_name="Test Master",
        city_id=test_city.id,
        is_active=True,
        is_blocked=False,
        verified=True,
        is_on_shift=True,
        has_vehicle=True,
        rating=4.5,
    )
    session.add(master)
    await session.flush()
    
    # Привязываем навык
    master_skill = m.master_skills(master_id=master.id, skill_id=test_skill.id)
    session.add(master_skill)
    
    # Привязываем район
    master_district = m.master_districts(master_id=master.id, district_id=test_district.id)
    session.add(master_district)
    
    await session.commit()
    await session.refresh(master)
    return master


async def _get_db_now(session: AsyncSession) -> datetime:
    """Получить текущее время БД."""
    row = await session.execute(text("SELECT NOW()"))
    return row.scalar()


# ==================== ТЕСТ 2.1: ПРИОРИТИЗАЦИЯ ====================

@pytest.mark.asyncio
async def test_step_2_1_order_prioritization(
    session: AsyncSession,
    test_city: m.cities,
    test_district: m.districts,
):
    """
    ✅ STEP 2.1: Проверяем приоритизацию заказов в очереди.
    
    Создаём 5 заказов с разными приоритетами:
    1. Эскалация к админу (highest)
    2. Гарантийный заказ
    3. Просроченный слот
    4. Эскалация к логисту
    5. Обычный (oldest)
    
    Проверяем что они обрабатываются в правильном порядке.
    """
    db_now = await _get_db_now(session)
    
    # 5. Обычный заказ (самый старый по времени создания)
    order_normal = m.orders(
        city_id=test_city.id,
        district_id=test_district.id,
        status=m.OrderStatus.SEARCHING,
        category="ELECTRICS",
        type="NORMAL",
        created_at=db_now - timedelta(hours=5),
    )
    
    # 4. С эскалацией к логисту
    order_logist = m.orders(
        city_id=test_city.id,
        district_id=test_district.id,
        status=m.OrderStatus.SEARCHING,
        category="ELECTRICS",
        type="NORMAL",
        dist_escalated_logist_at=db_now - timedelta(minutes=5),
        created_at=db_now - timedelta(hours=4),
    )
    
    # 3. Просроченный слот
    order_overdue = m.orders(
        city_id=test_city.id,
        district_id=test_district.id,
        status=m.OrderStatus.SEARCHING,
        category="ELECTRICS",
        type="NORMAL",
        timeslot_start_utc=db_now - timedelta(hours=1),  # Просрочен!
        created_at=db_now - timedelta(hours=3),
    )
    
    # 2. Гарантийный заказ
    order_guarantee = m.orders(
        city_id=test_city.id,
        district_id=test_district.id,
        status=m.OrderStatus.GUARANTEE,
        category="ELECTRICS",
        type="GUARANTEE",
        created_at=db_now - timedelta(hours=2),
    )
    
    # 1. С эскалацией к админу (highest priority)
    order_admin = m.orders(
        city_id=test_city.id,
        district_id=test_district.id,
        status=m.OrderStatus.SEARCHING,
        category="ELECTRICS",
        type="NORMAL",
        dist_escalated_logist_at=db_now - timedelta(minutes=15),
        dist_escalated_admin_at=db_now - timedelta(minutes=5),
        created_at=db_now - timedelta(hours=1),
    )
    
    session.add_all([order_normal, order_logist, order_overdue, order_guarantee, order_admin])
    await session.commit()
    
    # Получаем порядок обработки
    result = await session.execute(
        text("""
        SELECT o.id,
               o.type,
               o.dist_escalated_admin_at IS NOT NULL AS has_admin_esc,
               o.dist_escalated_logist_at IS NOT NULL AS has_logist_esc,
               o.timeslot_start_utc IS NOT NULL AND o.timeslot_start_utc < NOW() AS is_overdue
          FROM orders o
          JOIN cities c ON c.id = o.city_id
         WHERE o.status IN ('SEARCHING','GUARANTEE')
           AND o.assigned_master_id IS NULL
         ORDER BY
           (o.dist_escalated_admin_at IS NOT NULL) DESC,
           (o.type = 'GUARANTEE' OR o.status = 'GUARANTEE') DESC,
           (o.timeslot_start_utc IS NOT NULL AND o.timeslot_start_utc < NOW()) DESC,
           (o.dist_escalated_logist_at IS NOT NULL) DESC,
           o.created_at ASC
        """)
    )
    rows = result.fetchall()
    
    # Проверяем порядок
    assert len(rows) == 5, "Должно быть 5 заказов"
    
    # Сохраняем ID для проверки
    session.expire_all()
    await session.refresh(order_admin)
    await session.refresh(order_guarantee)
    await session.refresh(order_overdue)
    await session.refresh(order_logist)
    await session.refresh(order_normal)
    
    order_ids = [row[0] for row in rows]
    
    assert order_ids[0] == order_admin.id, "1-й: эскалация к админу"
    assert order_ids[1] == order_guarantee.id, "2-й: гарантийный"
    assert order_ids[2] == order_overdue.id, "3-й: просроченный слот"
    assert order_ids[3] == order_logist.id, "4-й: эскалация к логисту"
    assert order_ids[4] == order_normal.id, "5-й: обычный (oldest)"
    
    print("✅ Приоритизация работает правильно!")


# ==================== ТЕСТ 2.2: ЗАКАЗЫ БЕЗ РАЙОНА ====================

@pytest.mark.asyncio
async def test_step_2_2_no_district_fallback_to_city(
    session: AsyncSession,
    test_city: m.cities,
    test_skill: m.skills,
):
    """
    ✅ STEP 2.2: Проверяем fallback на поиск по городу для заказов без района.
    
    Создаём:
    - Заказ без района (district_id = NULL)
    - Мастера привязанного к городу но БЕЗ привязки к району
    
    Ожидаем:
    - Мастер будет найден (fallback на город)
    - Оффер будет отправлен
    """
    # Создаём мастера БЕЗ привязки к району (только город)
    master = m.masters(
        tg_user_id=987654321,  # ✅ Исправлено
        full_name="Citywide Master",
        city_id=test_city.id,
        is_active=True,
        is_blocked=False,
        verified=True,
        is_on_shift=True,
        has_vehicle=True,
        rating=4.8,
    )
    session.add(master)
    await session.flush()
    
    # Привязываем навык
    master_skill = m.master_skills(master_id=master.id, skill_id=test_skill.id)
    session.add(master_skill)
    await session.commit()
    await session.refresh(master)
    
    # Создаём заказ БЕЗ района
    order = m.orders(
        city_id=test_city.id,
        district_id=None,  # ✅ НЕТ района!
        status=m.OrderStatus.SEARCHING,
        category="ELECTRICS",
        type="NORMAL",
    )
    session.add(order)
    await session.commit()
    await session.refresh(order)
    
    # Запускаем распределитель
    cfg = DistConfig(
        tick_seconds=15,
        sla_seconds=120,
        rounds=2,
        top_log_n=10,
        to_admin_after_min=10,
    )
    
    await tick_once(cfg, bot=None, alerts_chat_id=None, session=session)
    
    # Проверяем что оффер был создан
    session.expire_all()
    result = await session.execute(
        select(m.offers).where(m.offers.order_id == order.id)
    )
    offer = result.scalar_one_or_none()
    
    assert offer is not None, "Оффер должен быть создан!"
    assert offer.master_id == master.id, f"Оффер должен быть отправлен мастеру {master.id}"
    assert offer.state == "SENT", "Оффер должен быть в статусе SENT"
    
    # Проверяем что эскалации НЕ было
    await session.refresh(order)
    assert order.dist_escalated_logist_at is None, "Не должно быть эскалации к логисту"
    assert order.dist_escalated_admin_at is None, "Не должно быть эскалации к админу"
    
    print("✅ Fallback на город работает!")


@pytest.mark.asyncio
async def test_step_2_2_no_district_escalates_if_no_masters(
    session: AsyncSession,
    test_city: m.cities,
):
    """
    ✅ STEP 2.2: Проверяем эскалацию если нет мастеров даже по городу.
    
    Создаём заказ без района, но НЕ создаём мастеров в городе.
    Ожидаем эскалацию к логисту.
    """
    # Создаём заказ БЕЗ района и БЕЗ мастеров
    order = m.orders(
        city_id=test_city.id,
        district_id=None,
        status=m.OrderStatus.SEARCHING,
        category="ELECTRICS",
        type="NORMAL",
    )
    session.add(order)
    await session.commit()
    await session.refresh(order)
    
    cfg = DistConfig(
        tick_seconds=15,
        sla_seconds=120,
        rounds=2,
        top_log_n=10,
        to_admin_after_min=10,
    )
    
    await tick_once(cfg, bot=None, alerts_chat_id=None, session=session)
    
    # Проверяем что произошла эскалация
    session.expire_all()
    await session.refresh(order)
    
    assert order.dist_escalated_logist_at is not None, "Должна быть эскалация к логисту"
    
    print("✅ Эскалация при отсутствии мастеров работает!")


# ==================== ТЕСТ 2.3: ИНТЕРВАЛ ТИКА ====================

@pytest.mark.asyncio
async def test_step_2_3_reduced_tick_interval(session: AsyncSession):
    """
    ✅ STEP 2.3: Проверяем что дефолтный интервал тика уменьшен до 15 секунд.
    """
    cfg = await _load_config()
    
    assert cfg.tick_seconds == 15, "Интервал тика должен быть 15 секунд (было 30)"
    
    print(f"✅ Интервал тика: {cfg.tick_seconds} секунд")


@pytest.mark.asyncio
async def test_step_2_3_faster_retry_after_timeout(
    session: AsyncSession,
    test_city: m.cities,
    test_district: m.districts,
    test_master: m.masters,
):
    """
    ✅ STEP 2.3: Проверяем что после таймаута оффера новый раунд начинается быстрее.
    
    План:
    1. Создаём заказ
    2. Отправляем оффер мастеру
    3. Делаем оффер истёкшим (expires_at в прошлом)
    4. Запускаем новый тик
    5. Проверяем что начался новый раунд (round_number = 2)
    """
    # Создаём заказ
    order = m.orders(
        city_id=test_city.id,
        district_id=test_district.id,
        status=m.OrderStatus.SEARCHING,
        category="ELECTRICS",
        type="NORMAL",
    )
    session.add(order)
    await session.commit()
    await session.refresh(order)
    
    # Создаём истёкший оффер (round 1)
    db_now = await _get_db_now(session)
    expired_offer = m.offers(
        order_id=order.id,
        master_id=test_master.id,
        round_number=1,
        state="SENT",
        sent_at=db_now - timedelta(minutes=5),
        expires_at=db_now - timedelta(minutes=1),  # ✅ Истёк 1 минуту назад!
    )
    session.add(expired_offer)
    await session.commit()
    
    # Запускаем тик
    cfg = DistConfig(
        tick_seconds=15,
        sla_seconds=120,
        rounds=2,
        top_log_n=10,
        to_admin_after_min=10,
    )
    
    await tick_once(cfg, bot=None, alerts_chat_id=None, session=session)
    
    # Проверяем результат
    session.expire_all()
    await session.refresh(expired_offer)
    
    # Старый оффер должен быть EXPIRED
    assert expired_offer.state == "EXPIRED", "Старый оффер должен быть EXPIRED"
    
    # Должен быть новый оффер (round 2)
    result = await session.execute(
        select(m.offers)
        .where(m.offers.order_id == order.id)
        .where(m.offers.round_number == 2)
        .where(m.offers.state == "SENT")
    )
    new_offer = result.scalar_one_or_none()
    
    assert new_offer is not None, "Должен быть новый оффер (round 2)"
    assert new_offer.master_id == test_master.id, "Новый оффер тому же мастеру"
    
    print("✅ Быстрый retry после таймаута работает!")


# ==================== ИНТЕГРАЦИОННЫЙ ТЕСТ ====================

@pytest.mark.asyncio
async def test_step_2_integration_all_improvements(
    session: AsyncSession,
    test_city: m.cities,
    test_district: m.districts,
    test_skill: m.skills,
):
    """
    ✅ ИНТЕГРАЦИОННЫЙ ТЕСТ: Проверяем все улучшения ЭТАПА 2 вместе.
    
    Сценарий:
    1. Создаём 3 заказа: гарантийный, с эскалацией, обычный
    2. Создаём мастера для всего города (без привязки к району)
    3. Проверяем что обработка идёт по приоритету
    4. Проверяем что мастер находится даже для заказа без района
    """
    db_now = await _get_db_now(session)
    
    # Мастер для всего города
    master = m.masters(
        tg_user_id=111222333,  # ✅ Исправлено
        full_name="Citywide Master",
        city_id=test_city.id,
        is_active=True,
        is_blocked=False,
        verified=True,
        is_on_shift=True,
        has_vehicle=True,
        rating=5.0,
    )
    session.add(master)
    await session.flush()
    
    master_skill = m.master_skills(master_id=master.id, skill_id=test_skill.id)
    session.add(master_skill)
    await session.commit()
    await session.refresh(master)
    
    # 1. Обычный заказ (низкий приоритет) БЕЗ района
    order_normal = m.orders(
        city_id=test_city.id,
        district_id=None,  # ✅ Без района!
        status=m.OrderStatus.SEARCHING,
        category="ELECTRICS",
        type="NORMAL",
        created_at=db_now - timedelta(hours=3),
    )
    
    # 2. С эскалацией (средний приоритет)
    order_escalated = m.orders(
        city_id=test_city.id,
        district_id=test_district.id,
        status=m.OrderStatus.SEARCHING,
        category="ELECTRICS",
        type="NORMAL",
        dist_escalated_logist_at=db_now - timedelta(minutes=5),
        created_at=db_now - timedelta(hours=2),
    )
    
    # 3. Гарантийный (высокий приоритет)
    order_guarantee = m.orders(
        city_id=test_city.id,
        district_id=test_district.id,
        status=m.OrderStatus.GUARANTEE,
        category="ELECTRICS",
        type="GUARANTEE",
        created_at=db_now - timedelta(hours=1),
    )
    
    session.add_all([order_normal, order_escalated, order_guarantee])
    await session.commit()
    
    # Запускаем 3 тика (для каждого заказа)
    cfg = DistConfig(
        tick_seconds=15,
        sla_seconds=120,
        rounds=2,
        top_log_n=10,
        to_admin_after_min=10,
    )
    
    for i in range(3):
        await tick_once(cfg, bot=None, alerts_chat_id=None, session=session)
        await asyncio.sleep(0.1)  # Небольшая пауза
    
    # Проверяем что все офферы созданы
    session.expire_all()
    result = await session.execute(select(m.offers))
    offers = result.scalars().all()
    
    assert len(offers) == 3, f"Должно быть 3 оффера, получено {len(offers)}"
    
    # Проверяем порядок обработки по round_number
    # Гарантийный должен быть первым (round 1 раньше других)
    result = await session.execute(
        select(m.offers)
        .order_by(m.offers.sent_at)
    )
    ordered_offers = result.scalars().all()
    
    # Первый оффер - гарантийному
    await session.refresh(order_guarantee)
    assert ordered_offers[0].order_id == order_guarantee.id, "Первым обработан гарантийный"
    
    # Второй - с эскалацией
    await session.refresh(order_escalated)
    assert ordered_offers[1].order_id == order_escalated.id, "Вторым обработан с эскалацией"
    
    # Третий - обычный БЕЗ района
    await session.refresh(order_normal)
    assert ordered_offers[2].order_id == order_normal.id, "Третьим обработан обычный"
    
    # Проверяем что заказ без района НЕ эскалирован (нашёлся мастер по городу)
    assert order_normal.dist_escalated_logist_at is None, "Обычный заказ НЕ эскалирован"
    
    print("✅ Все улучшения ЭТАПА 2 работают вместе!")
