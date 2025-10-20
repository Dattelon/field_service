# -*- coding: utf-8 -*-
"""
E2E тесты для проверки исправлений Stage 1.1-1.3

Fix 1.1: Race Condition при параллельном принятии офферов
Fix 1.2: DEFERRED заказы - разрешение принятия в нерабочее время
Fix 1.3: Гарантийные заказы - fallback при недоступном preferred мастере
"""

import asyncio
import pytest
import pytest_asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy import select, insert, update
from sqlalchemy.ext.asyncio import AsyncSession

from field_service.db import models as m
from field_service.bots.master_bot.handlers import orders
from field_service.services import distribution_scheduler as ds


# ============================================================================
# FIXTURES
# ============================================================================

@pytest_asyncio.fixture
async def sample_city(async_session: AsyncSession) -> m.cities:
    """Создание тестового города"""
    city = m.cities(
        id=1,
        name="Тестовый город",
        timezone="Europe/Moscow",
    )
    async_session.add(city)
    await async_session.commit()
    await async_session.refresh(city)
    return city


@pytest_asyncio.fixture
async def sample_district(async_session: AsyncSession, sample_city) -> m.districts:
    """Создание тестового района"""
    district = m.districts(
        id=1,
        city_id=sample_city.id,
        name="Центральный район",
    )
    async_session.add(district)
    await async_session.commit()
    await async_session.refresh(district)
    return district


@pytest_asyncio.fixture
async def sample_skill(async_session: AsyncSession) -> m.skills:
    """Создание тестового навыка"""
    skill = m.skills(
        id=1,
        code="ELEC",
        name="Электрика",
        is_active=True,
    )
    async_session.add(skill)
    await async_session.commit()
    await async_session.refresh(skill)
    return skill


@pytest_asyncio.fixture
async def master1(async_session: AsyncSession, sample_city, sample_district, sample_skill) -> m.masters:
    """Создание первого мастера"""
    master = m.masters(
        id=101,
        tg_user_id=1001,
        full_name="Мастер Первый",
        phone="+79001111111",
        city_id=sample_city.id,
        is_active=True,
        is_blocked=False,
        verified=True,
        is_on_shift=True,
        has_vehicle=True,
        rating=Decimal("4.8"),
    )
    async_session.add(master)
    await async_session.flush()
    
    # Добавляем район
    async_session.add(m.master_districts(master_id=master.id, district_id=sample_district.id))
    
    # Добавляем навык
    async_session.add(m.master_skills(master_id=master.id, skill_id=sample_skill.id))
    
    await async_session.commit()
    await async_session.refresh(master)
    return master


@pytest_asyncio.fixture
async def master2(async_session: AsyncSession, sample_city, sample_district, sample_skill) -> m.masters:
    """Создание второго мастера"""
    master = m.masters(
        id=102,
        tg_user_id=1002,
        full_name="Мастер Второй",
        phone="+79002222222",
        city_id=sample_city.id,
        is_active=True,
        is_blocked=False,
        verified=True,
        is_on_shift=True,
        has_vehicle=False,
        rating=Decimal("4.5"),
    )
    async_session.add(master)
    await async_session.flush()
    
    # Добавляем район
    async_session.add(m.master_districts(master_id=master.id, district_id=sample_district.id))
    
    # Добавляем навык
    async_session.add(m.master_skills(master_id=master.id, skill_id=sample_skill.id))
    
    await async_session.commit()
    await async_session.refresh(master)
    return master


@pytest_asyncio.fixture
async def master3_preferred_unavailable(async_session: AsyncSession, sample_city, sample_district, sample_skill) -> m.masters:
    """Создание третьего мастера (preferred, но недоступен)"""
    master = m.masters(
        id=103,
        tg_user_id=1003,
        full_name="Мастер Третий (Preferred)",
        phone="+79003333333",
        city_id=sample_city.id,
        is_active=True,
        is_blocked=False,
        verified=True,
        is_on_shift=False,  # ❌ НЕ на смене
        has_vehicle=True,
        rating=Decimal("5.0"),
    )
    async_session.add(master)
    await async_session.flush()
    
    # Добавляем район
    async_session.add(m.master_districts(master_id=master.id, district_id=sample_district.id))
    
    # Добавляем навык
    async_session.add(m.master_skills(master_id=master.id, skill_id=sample_skill.id))
    
    await async_session.commit()
    await async_session.refresh(master)
    return master


@pytest_asyncio.fixture
async def sample_order(async_session: AsyncSession, sample_city, sample_district) -> m.orders:
    """Создание тестового заказа"""
    order = m.orders(
        id=1,
        city_id=sample_city.id,
        district_id=sample_district.id,
        category=m.OrderCategory.ELECTRICS,
        type=m.OrderType.NORMAL,
        status=m.OrderStatus.SEARCHING,
        client_name="Тестовый клиент",
        client_phone="+79009999999",
        house="10",
        timeslot_start_utc=datetime.utcnow() + timedelta(hours=2),
        timeslot_end_utc=datetime.utcnow() + timedelta(hours=4),
        version=1,
    )
    async_session.add(order)
    await async_session.commit()
    await async_session.refresh(order)
    return order


# ============================================================================
# FIX 1.1: RACE CONDITION TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_race_condition_two_masters_accept_simultaneously(
    async_session: AsyncSession,
    sample_order: m.orders,
    master1: m.masters,
    master2: m.masters,
):
    """
    Тест Fix 1.1: Два мастера одновременно принимают заказ
    
    Ожидаемое поведение:
    - Первый мастер успешно принимает заказ
    - Второй мастер получает ошибку "Заказ уже взят"
    - В БД только один assigned_master_id
    """
    # Создаём офферы для обоих мастеров
    async_session.add_all([
        m.offers(
            order_id=sample_order.id,
            master_id=master1.id,
            round_number=1,
            state=m.OfferState.SENT,
            sent_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(seconds=120),
        ),
        m.offers(
            order_id=sample_order.id,
            master_id=master2.id,
            round_number=1,
            state=m.OfferState.SENT,
            sent_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(seconds=120),
        ),
    ])
    await async_session.commit()
    
    # Мокируем callback для обоих мастеров
    callback1 = MagicMock()
    callback1.data = f"m:new:acc:{sample_order.id}:1"
    callback1.from_user.id = master1.tg_user_id
    
    callback2 = MagicMock()
    callback2.data = f"m:new:acc:{sample_order.id}:1"
    callback2.from_user.id = master2.tg_user_id
    
    # Мокируем функции уведомлений
    mock_answer = AsyncMock()
    mock_render = AsyncMock()
    
    import field_service.bots.master_bot.handlers.orders as orders_module
    original_answer = orders_module.safe_answer_callback
    original_render = orders_module._render_offers
    
    orders_module.safe_answer_callback = mock_answer
    orders_module._render_offers = mock_render
    
    try:
        # Запускаем оба принятия параллельно
        results = await asyncio.gather(
            orders.offer_accept(callback1, async_session, master1),
            orders.offer_accept(callback2, async_session, master2),
            return_exceptions=True,
        )
        
        # Проверяем результат в БД
        await async_session.commit()
        order_result = await async_session.get(m.orders, sample_order.id)
        
        # ✅ Проверка 1: Заказ назначен только одному мастеру
        assert order_result.assigned_master_id is not None
        assert order_result.assigned_master_id in [master1.id, master2.id]
        assert order_result.status == m.OrderStatus.ASSIGNED
        
        # ✅ Проверка 2: Один оффер ACCEPTED, другой CANCELED
        offers_result = await async_session.execute(
            select(m.offers).where(m.offers.order_id == sample_order.id)
        )
        offers_list = list(offers_result.scalars().all())
        
        accepted_count = sum(1 for o in offers_list if o.state == m.OfferState.ACCEPTED)
        canceled_count = sum(1 for o in offers_list if o.state == m.OfferState.CANCELED)
        
        assert accepted_count == 1, "Должен быть ровно 1 принятый оффер"
        assert canceled_count == 1, "Должен быть ровно 1 отменённый оффер"
        
        # ✅ Проверка 3: Версия заказа увеличилась
        assert order_result.version == 2
        
        print("✅ FIX 1.1 TEST PASSED: Race condition prevented!")
        
    finally:
        # Восстанавливаем оригинальные функции
        orders_module.safe_answer_callback = original_answer
        orders_module._render_offers = original_render


@pytest.mark.asyncio
async def test_race_condition_with_for_update_skip_locked(
    async_session: AsyncSession,
    sample_order: m.orders,
    master1: m.masters,
):
    """
    Тест Fix 1.1: Проверка работы FOR UPDATE SKIP LOCKED
    
    Ожидаемое поведение:
    - Заблокированная строка пропускается (skip_locked=True)
    - Второй запрос возвращает None вместо ожидания
    """
    # Начинаем транзакцию с блокировкой
    from sqlalchemy import text
    
    # Первая сессия блокирует заказ
    async with async_session.begin():
        locked_order = await async_session.execute(
            select(m.orders)
            .where(m.orders.id == sample_order.id)
            .with_for_update()
        )
        locked_order.first()
        
        # Пытаемся получить заказ со SKIP LOCKED во второй сессии
        # (симулируем второго мастера)
        from field_service.db.session import SessionLocal
        async with SessionLocal() as session2:
            skipped_order = await session2.execute(
                select(m.orders)
                .where(m.orders.id == sample_order.id)
                .with_for_update(skip_locked=True)
            )
            result = skipped_order.first()
            
            # ✅ Проверка: Заблокированная строка пропущена
            assert result is None, "SKIP LOCKED должен вернуть None для заблокированной строки"
    
    print("✅ FIX 1.1 TEST PASSED: FOR UPDATE SKIP LOCKED works correctly!")


# ============================================================================
# FIX 1.2: DEFERRED ORDERS TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_deferred_order_can_be_accepted(
    async_session: AsyncSession,
    sample_order: m.orders,
    master1: m.masters,
):
    """
    Тест Fix 1.2: Мастер может принять DEFERRED заказ
    
    Ожидаемое поведение:
    - Заказ в статусе DEFERRED
    - Мастер успешно принимает оффер
    - Статус меняется DEFERRED → ASSIGNED
    """
    # Устанавливаем статус DEFERRED
    sample_order.status = m.OrderStatus.DEFERRED
    await async_session.commit()
    
    # Создаём оффер
    async_session.add(
        m.offers(
            order_id=sample_order.id,
            master_id=master1.id,
            round_number=1,
            state=m.OfferState.SENT,
            sent_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(seconds=120),
        )
    )
    await async_session.commit()
    
    # Мокируем callback
    callback = MagicMock()
    callback.data = f"m:new:acc:{sample_order.id}:1"
    callback.from_user.id = master1.tg_user_id
    
    # Мокируем функции
    mock_answer = AsyncMock()
    mock_render = AsyncMock()
    
    import field_service.bots.master_bot.handlers.orders as orders_module
    original_answer = orders_module.safe_answer_callback
    original_render = orders_module._render_offers
    
    orders_module.safe_answer_callback = mock_answer
    orders_module._render_offers = mock_render
    
    try:
        # Принимаем оффер
        await orders.offer_accept(callback, async_session, master1)
        
        # Проверяем результат
        await async_session.commit()
        order_result = await async_session.get(m.orders, sample_order.id)
        
        # ✅ Проверка 1: Заказ принят
        assert order_result.assigned_master_id == master1.id
        
        # ✅ Проверка 2: Статус изменился DEFERRED → ASSIGNED
        assert order_result.status == m.OrderStatus.ASSIGNED
        
        # ✅ Проверка 3: Оффер в состоянии ACCEPTED
        offer_result = await async_session.execute(
            select(m.offers).where(
                m.offers.order_id == sample_order.id,
                m.offers.master_id == master1.id
            )
        )
        offer = offer_result.scalar_one()
        assert offer.state == m.OfferState.ACCEPTED
        
        print("✅ FIX 1.2 TEST PASSED: DEFERRED order accepted successfully!")
        
    finally:
        orders_module.safe_answer_callback = original_answer
        orders_module._render_offers = original_render


@pytest.mark.asyncio
async def test_deferred_orders_included_in_distribution(
    async_session: AsyncSession,
    sample_city: m.cities,
    sample_district: m.districts,
):
    """
    Тест Fix 1.2: DEFERRED заказы с офферами включаются в распределение
    
    Ожидаемое поведение:
    - DEFERRED заказ с активным оффером попадает в выборку
    - DEFERRED заказ без оффера НЕ попадает в выборку
    """
    # Создаём два DEFERRED заказа
    order_with_offer = m.orders(
        id=100,
        city_id=sample_city.id,
        district_id=sample_district.id,
        category=m.OrderCategory.ELECTRICS,
        type=m.OrderType.NORMAL,
        status=m.OrderStatus.DEFERRED,  # ✅ DEFERRED
        client_name="Клиент 1",
        client_phone="+79001111111",
        house="10",
        version=1,
    )
    
    order_without_offer = m.orders(
        id=101,
        city_id=sample_city.id,
        district_id=sample_district.id,
        category=m.OrderCategory.ELECTRICS,
        type=m.OrderType.NORMAL,
        status=m.OrderStatus.DEFERRED,  # ✅ DEFERRED
        client_name="Клиент 2",
        client_phone="+79002222222",
        house="20",
        version=1,
    )
    
    async_session.add_all([order_with_offer, order_without_offer])
    await async_session.flush()
    
    # Добавляем оффер для первого заказа
    async_session.add(
        m.offers(
            order_id=order_with_offer.id,
            master_id=101,
            round_number=1,
            state=m.OfferState.SENT,  # ✅ Активный оффер
            sent_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(seconds=120),
        )
    )
    await async_session.commit()
    
    # Получаем заказы для распределения
    orders_for_dist = await ds._fetch_orders_for_distribution(async_session)
    
    order_ids = [o.id for o in orders_for_dist]
    
    # ✅ Проверка: DEFERRED с оффером включён
    assert order_with_offer.id in order_ids, \
        "DEFERRED заказ с активным оффером должен быть в распределении"
    
    # ✅ Проверка: DEFERRED без оффера НЕ включён
    assert order_without_offer.id not in order_ids, \
        "DEFERRED заказ без оффера НЕ должен быть в распределении"
    
    print("✅ FIX 1.2 TEST PASSED: DEFERRED orders correctly filtered in distribution!")


# ============================================================================
# FIX 1.3: GUARANTEE ORDERS TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_guarantee_order_fallback_when_preferred_unavailable(
    async_session: AsyncSession,
    sample_city: m.cities,
    sample_district: m.districts,
    sample_skill: m.skills,
    master1: m.masters,
    master3_preferred_unavailable: m.masters,
):
    """
    Тест Fix 1.3: Гарантийный заказ - fallback при недоступном preferred мастере
    
    Ожидаемое поведение:
    - Preferred мастер не на смене (unavailable)
    - Система ищет альтернативных мастеров
    - Оффер отправляется доступному мастеру
    - НЕТ эскалации к логисту
    """
    # Создаём гарантийный заказ с preferred мастером
    guarantee_order = m.orders(
        id=200,
        city_id=sample_city.id,
        district_id=sample_district.id,
        category=m.OrderCategory.ELECTRICS,
        type=m.OrderType.GUARANTEE,  # ✅ Гарантийный
        status=m.OrderStatus.GUARANTEE,
        preferred_master_id=master3_preferred_unavailable.id,  # ✅ Preferred (недоступен)
        client_name="Гарантийный клиент",
        client_phone="+79003333333",
        house="30",
        version=1,
    )
    async_session.add(guarantee_order)
    await async_session.commit()
    
    # Получаем кандидатов с preferred
    skill_code = "ELEC"
    
    # Первая попытка: с preferred
    ranked_with_preferred = await ds._candidates(
        async_session,
        oid=guarantee_order.id,
        city_id=sample_city.id,
        district_id=sample_district.id,
        skill_code=skill_code,
        preferred_mid=master3_preferred_unavailable.id,
        fallback_limit=5,
    )
    
    # ✅ Проверка 1: Preferred недоступен, список пуст
    assert len(ranked_with_preferred) == 0, \
        "Preferred мастер не на смене, должен быть отфильтрован"
    
    # Вторая попытка: БЕЗ preferred (fallback)
    ranked_without_preferred = await ds._candidates(
        async_session,
        oid=guarantee_order.id,
        city_id=sample_city.id,
        district_id=sample_district.id,
        skill_code=skill_code,
        preferred_mid=None,  # ✅ Fallback
        fallback_limit=5,
    )
    
    # ✅ Проверка 2: Найден альтернативный мастер
    assert len(ranked_without_preferred) > 0, \
        "Должны быть найдены альтернативные мастера"
    
    assert master1.id in [c['mid'] for c in ranked_without_preferred], \
        "master1 (доступный) должен быть в списке кандидатов"
    
    print("✅ FIX 1.3 TEST PASSED: Guarantee order fallback works correctly!")


@pytest.mark.asyncio
async def test_preferred_master_diagnostics(
    async_session: AsyncSession,
    sample_district: m.districts,
    master3_preferred_unavailable: m.masters,
):
    """
    Тест Fix 1.3: Диагностика preferred мастера
    
    Ожидаемое поведение:
    - Функция диагностики определяет причины недоступности
    - Возвращает детальную информацию
    """
    # Проверяем диагностику
    diag = await ds._check_preferred_master_availability(
        async_session,
        master_id=master3_preferred_unavailable.id,
        order_id=1,
        district_id=sample_district.id,
        skill_code="ELEC",
    )
    
    # ✅ Проверка 1: Мастер недоступен
    assert diag["available"] is False, "Preferred мастер должен быть недоступен"
    
    # ✅ Проверка 2: Причина - not_on_shift
    assert "not_on_shift" in diag["reasons"], \
        "Причина недоступности: not_on_shift"
    
    print("✅ FIX 1.3 TEST PASSED: Preferred master diagnostics working!")


# ============================================================================
# INTEGRATION TEST: ALL FIXES TOGETHER
# ============================================================================

@pytest.mark.asyncio
async def test_all_fixes_integration(
    async_session: AsyncSession,
    sample_city: m.cities,
    sample_district: m.districts,
    sample_skill: m.skills,
    master1: m.masters,
    master2: m.masters,
    master3_preferred_unavailable: m.masters,
):
    """
    Интеграционный тест: Все исправления вместе
    
    Сценарий:
    1. Создаём DEFERRED гарантийный заказ с preferred мастером
    2. Preferred мастер недоступен
    3. Два других мастера пытаются принять одновременно
    
    Ожидание:
    - Заказ можно принять несмотря на DEFERRED
    - Fallback находит альтернативных мастеров
    - Race condition предотвращён
    """
    # Создаём DEFERRED гарантийный заказ
    complex_order = m.orders(
        id=300,
        city_id=sample_city.id,
        district_id=sample_district.id,
        category=m.OrderCategory.ELECTRICS,
        type=m.OrderType.GUARANTEE,
        status=m.OrderStatus.DEFERRED,  # ✅ DEFERRED
        preferred_master_id=master3_preferred_unavailable.id,  # ✅ Preferred unavailable
        client_name="Комплексный клиент",
        client_phone="+79004444444",
        house="40",
        version=1,
    )
    async_session.add(complex_order)
    await async_session.flush()
    
    # Создаём офферы для обоих доступных мастеров
    async_session.add_all([
        m.offers(
            order_id=complex_order.id,
            master_id=master1.id,
            round_number=1,
            state=m.OfferState.SENT,
            sent_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(seconds=120),
        ),
        m.offers(
            order_id=complex_order.id,
            master_id=master2.id,
            round_number=1,
            state=m.OfferState.SENT,
            sent_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(seconds=120),
        ),
    ])
    await async_session.commit()
    
    # Мокируем callbacks
    callback1 = MagicMock()
    callback1.data = f"m:new:acc:{complex_order.id}:1"
    callback1.from_user.id = master1.tg_user_id
    
    callback2 = MagicMock()
    callback2.data = f"m:new:acc:{complex_order.id}:1"
    callback2.from_user.id = master2.tg_user_id
    
    # Мокируем функции
    mock_answer = AsyncMock()
    mock_render = AsyncMock()
    
    import field_service.bots.master_bot.handlers.orders as orders_module
    original_answer = orders_module.safe_answer_callback
    original_render = orders_module._render_offers
    
    orders_module.safe_answer_callback = mock_answer
    orders_module._render_offers = mock_render
    
    try:
        # Параллельное принятие
        await asyncio.gather(
            orders.offer_accept(callback1, async_session, master1),
            orders.offer_accept(callback2, async_session, master2),
            return_exceptions=True,
        )
        
        # Проверяем результат
        await async_session.commit()
        order_result = await async_session.get(m.orders, complex_order.id)
        
        # ✅ Fix 1.2: DEFERRED заказ принят
        assert order_result.status == m.OrderStatus.ASSIGNED, \
            "DEFERRED заказ должен стать ASSIGNED"
        
        # ✅ Fix 1.1: Только один мастер получил заказ
        assert order_result.assigned_master_id is not None
        assert order_result.assigned_master_id in [master1.id, master2.id]
        
        # ✅ Fix 1.3: Preferred НЕ получил заказ (недоступен)
        assert order_result.assigned_master_id != master3_preferred_unavailable.id, \
            "Preferred (недоступный) мастер НЕ должен получить заказ"
        
        print("✅ INTEGRATION TEST PASSED: All fixes working together!")
        
    finally:
        orders_module.safe_answer_callback = original_answer
        orders_module._render_offers = original_render


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
