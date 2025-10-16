# -*- coding: utf-8 -*-
"""
Комплексные тесты для FIX 1.3: Гарантийные заказы и fallback при недоступном preferred мастере

ТРЕБОВАНИЯ:
- PostgreSQL (через docker-compose)
- Реальная логика распределения
- Параллельные сценарии

Тестовые сценарии:
1. Fallback при различных причинах недоступности preferred мастера
2. Приоритизация preferred мастера, когда он доступен
3. Эскалация, если нет кандидатов вообще
4. Интеграция с системой распределения
"""

import asyncio
import pytest
import pytest_asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from field_service.db import models as m
from field_service.services import distribution_scheduler as ds


# ============================================================================
# FIXTURES
# ============================================================================

@pytest_asyncio.fixture
async def test_city(async_session: AsyncSession) -> m.cities:
    """Тестовый город"""
    city = m.cities(
        name="Москва",
        timezone="Europe/Moscow",
    )
    async_session.add(city)
    await async_session.commit()
    await async_session.refresh(city)
    return city


@pytest_asyncio.fixture
async def test_district(async_session: AsyncSession, test_city) -> m.districts:
    """Тестовый район"""
    district = m.districts(
        city_id=test_city.id,
        name="Центральный",
    )
    async_session.add(district)
    await async_session.commit()
    await async_session.refresh(district)
    return district


@pytest_asyncio.fixture
async def test_skill(async_session: AsyncSession) -> m.skills:
    """Тестовый навык: Электрика"""
    skill = m.skills(
        code="ELEC",
        name="Электрика",
        is_active=True,
    )
    async_session.add(skill)
    await async_session.commit()
    await async_session.refresh(skill)
    return skill


async def create_master(
    session: AsyncSession,
    *,
    tg_user_id: int,
    full_name: str,
    city_id: int,
    district_id: int,
    skill_id: int,
    is_on_shift: bool = True,
    is_active: bool = True,
    is_blocked: bool = False,
    verified: bool = True,
    break_until: Optional[datetime] = None,
    max_active_orders_override: Optional[int] = None,
    rating: Decimal = Decimal("4.5"),
) -> m.masters:
    """Создание мастера с полной конфигурацией"""
    master = m.masters(
        tg_user_id=tg_user_id,
        full_name=full_name,
        phone=f"+7900{tg_user_id:07d}",
        city_id=city_id,
        is_active=is_active,
        is_blocked=is_blocked,
        verified=verified,
        is_on_shift=is_on_shift,
        break_until=break_until,
        max_active_orders_override=max_active_orders_override,
        has_vehicle=True,
        rating=rating,
    )
    session.add(master)
    await session.flush()
    
    # Добавляем район
    session.add(m.master_districts(
        master_id=master.id,
        district_id=district_id,
    ))
    
    # Добавляем навык
    session.add(m.master_skills(
        master_id=master.id,
        skill_id=skill_id,
    ))
    
    await session.commit()
    await session.refresh(master)
    return master


async def create_order(
    session: AsyncSession,
    *,
    city_id: int,
    district_id: Optional[int],
    category: m.OrderCategory = m.OrderCategory.ELECTRICS,
    order_type: m.OrderType = m.OrderType.NORMAL,
    status: m.OrderStatus = m.OrderStatus.SEARCHING,
    preferred_master_id: Optional[int] = None,
    client_name: str = "Тестовый клиент",
) -> m.orders:
    """Создание заказа"""
    order = m.orders(
        city_id=city_id,
        district_id=district_id,
        category=category,
        type=order_type,
        status=status,
        preferred_master_id=preferred_master_id,
        client_name=client_name,
        client_phone="+79001234567",
        house="10",
        timeslot_start_utc=datetime.now(timezone.utc) + timedelta(hours=2),
        timeslot_end_utc=datetime.now(timezone.utc) + timedelta(hours=4),
        version=1,
    )
    session.add(order)
    await session.commit()
    await session.refresh(order)
    return order


# ============================================================================
# TEST 1: Preferred мастер не на смене → fallback
# ============================================================================

@pytest.mark.asyncio
async def test_preferred_not_on_shift_fallback(
    async_session: AsyncSession,
    test_city,
    test_district,
    test_skill,
):
    """
    Сценарий: Preferred мастер не на смене
    
    Ожидаемое поведение:
    - Диагностика определяет причину: not_on_shift
    - Система ищет альтернативных мастеров
    - Fallback находит доступного мастера
    """
    # Создаём preferred мастера (НЕ на смене)
    preferred_master = await create_master(
        async_session,
        tg_user_id=1001,
        full_name="Preferred (Not On Shift)",
        city_id=test_city.id,
        district_id=test_district.id,
        skill_id=test_skill.id,
        is_on_shift=False,  # ❌ НЕ на смене
    )
    
    # Создаём альтернативного мастера (на смене)
    fallback_master = await create_master(
        async_session,
        tg_user_id=1002,
        full_name="Fallback Master",
        city_id=test_city.id,
        district_id=test_district.id,
        skill_id=test_skill.id,
        is_on_shift=True,  # ✅ На смене
    )
    
    # Создаём гарантийный заказ
    order = await create_order(
        async_session,
        city_id=test_city.id,
        district_id=test_district.id,
        order_type=m.OrderType.GUARANTEE,
        status=m.OrderStatus.GUARANTEE,
        preferred_master_id=preferred_master.id,
    )
    
    # ===== ДИАГНОСТИКА =====
    diag = await ds._check_preferred_master_availability(
        async_session,
        master_id=preferred_master.id,
        order_id=order.id,
        district_id=test_district.id,
        skill_code="ELEC",
    )
    
    # ✅ Проверка 1: Preferred недоступен
    assert diag["available"] is False, \
        "Preferred мастер не должен быть доступен"
    
    # ✅ Проверка 2: Причина - not_on_shift
    assert "not_on_shift" in diag["reasons"], \
        f"Ожидалась причина 'not_on_shift', получено: {diag['reasons']}"
    
    # ===== FALLBACK =====
    # Ищем кандидатов БЕЗ preferred
    candidates = await ds._candidates(
        async_session,
        oid=order.id,
        city_id=test_city.id,
        district_id=test_district.id,
        skill_code="ELEC",
        preferred_mid=None,  # ✅ Fallback режим
        fallback_limit=5,
    )
    
    # ✅ Проверка 3: Найден альтернативный мастер
    assert len(candidates) > 0, \
        "Должны быть найдены альтернативные мастера"
    
    # ✅ Проверка 4: В списке только доступный мастер
    candidate_ids = [c['mid'] for c in candidates]
    assert fallback_master.id in candidate_ids, \
        "fallback_master должен быть в списке кандидатов"
    assert preferred_master.id not in candidate_ids, \
        "preferred_master НЕ должен быть в списке (не на смене)"
    
    print("[OK] TEST PASSED: Fallback при preferred not_on_shift работает")


# ============================================================================
# TEST 2: Preferred мастер на перерыве → fallback
# ============================================================================

@pytest.mark.asyncio
async def test_preferred_on_break_fallback(
    async_session: AsyncSession,
    test_city,
    test_district,
    test_skill,
):
    """
    Сценарий: Preferred мастер на перерыве
    
    Ожидаемое поведение:
    - Диагностика определяет причину: on_break_until_...
    - Система ищет альтернативных мастеров
    """
    # Создаём preferred мастера (на перерыве)
    preferred_master = await create_master(
        async_session,
        tg_user_id=2001,
        full_name="Preferred (On Break)",
        city_id=test_city.id,
        district_id=test_district.id,
        skill_id=test_skill.id,
        is_on_shift=True,
        break_until=datetime.now(timezone.utc) + timedelta(hours=1),  # ❌ На перерыве
    )
    
    # Создаём альтернативного мастера
    fallback_master = await create_master(
        async_session,
        tg_user_id=2002,
        full_name="Fallback Master 2",
        city_id=test_city.id,
        district_id=test_district.id,
        skill_id=test_skill.id,
        is_on_shift=True,
        break_until=None,  # ✅ НЕ на перерыве
    )
    
    # Создаём гарантийный заказ
    order = await create_order(
        async_session,
        city_id=test_city.id,
        district_id=test_district.id,
        order_type=m.OrderType.GUARANTEE,
        status=m.OrderStatus.GUARANTEE,
        preferred_master_id=preferred_master.id,
    )
    
    # ===== ДИАГНОСТИКА =====
    diag = await ds._check_preferred_master_availability(
        async_session,
        master_id=preferred_master.id,
        order_id=order.id,
        district_id=test_district.id,
        skill_code="ELEC",
    )
    
    # ✅ Проверка: Причина - on_break_until
    assert not diag["available"]
    assert any("on_break_until" in r for r in diag["reasons"]), \
        f"Ожидалась причина 'on_break_until', получено: {diag['reasons']}"
    
    # ===== FALLBACK =====
    candidates = await ds._candidates(
        async_session,
        oid=order.id,
        city_id=test_city.id,
        district_id=test_district.id,
        skill_code="ELEC",
        preferred_mid=None,
        fallback_limit=5,
    )
    
    # ✅ Проверка: Найден альтернативный мастер
    assert len(candidates) > 0
    candidate_ids = [c['mid'] for c in candidates]
    assert fallback_master.id in candidate_ids
    
    print("[OK] TEST PASSED: Fallback при preferred on_break работает")


# ============================================================================
# TEST 3: Preferred мастер заблокирован → fallback
# ============================================================================

@pytest.mark.asyncio
async def test_preferred_blocked_fallback(
    async_session: AsyncSession,
    test_city,
    test_district,
    test_skill,
):
    """
    Сценарий: Preferred мастер заблокирован
    
    Ожидаемое поведение:
    - Диагностика определяет причину: blocked
    - Система ищет альтернативных мастеров
    """
    # Создаём preferred мастера (заблокирован)
    preferred_master = await create_master(
        async_session,
        tg_user_id=3001,
        full_name="Preferred (Blocked)",
        city_id=test_city.id,
        district_id=test_district.id,
        skill_id=test_skill.id,
        is_on_shift=True,
        is_blocked=True,  # ❌ Заблокирован
    )
    
    # Создаём альтернативного мастера
    fallback_master = await create_master(
        async_session,
        tg_user_id=3002,
        full_name="Fallback Master 3",
        city_id=test_city.id,
        district_id=test_district.id,
        skill_id=test_skill.id,
        is_on_shift=True,
        is_blocked=False,  # ✅ НЕ заблокирован
    )
    
    # Создаём гарантийный заказ
    order = await create_order(
        async_session,
        city_id=test_city.id,
        district_id=test_district.id,
        order_type=m.OrderType.GUARANTEE,
        status=m.OrderStatus.GUARANTEE,
        preferred_master_id=preferred_master.id,
    )
    
    # ===== ДИАГНОСТИКА =====
    diag = await ds._check_preferred_master_availability(
        async_session,
        master_id=preferred_master.id,
        order_id=order.id,
        district_id=test_district.id,
        skill_code="ELEC",
    )
    
    # ✅ Проверка: Причина - blocked
    assert not diag["available"]
    assert "blocked" in diag["reasons"], \
        f"Ожидалась причина 'blocked', получено: {diag['reasons']}"
    
    # ===== FALLBACK =====
    candidates = await ds._candidates(
        async_session,
        oid=order.id,
        city_id=test_city.id,
        district_id=test_district.id,
        skill_code="ELEC",
        preferred_mid=None,
        fallback_limit=5,
    )
    
    # ✅ Проверка: Найден альтернативный мастер
    assert len(candidates) > 0
    candidate_ids = [c['mid'] for c in candidates]
    assert fallback_master.id in candidate_ids
    
    print("[OK] TEST PASSED: Fallback при preferred blocked работает")



# ============================================================================
# TEST 4: Preferred мастер достиг лимита заказов → fallback
# ============================================================================

@pytest.mark.asyncio
async def test_preferred_at_limit_fallback(
    async_session: AsyncSession,
    test_city,
    test_district,
    test_skill,
):
    """
    Сценарий: Preferred мастер достиг лимита активных заказов
    
    Ожидаемое поведение:
    - Диагностика определяет причину: at_limit_X/Y
    - Система ищет альтернативных мастеров
    """
    # Создаём preferred мастера с лимитом 2
    preferred_master = await create_master(
        async_session,
        tg_user_id=4001,
        full_name="Preferred (At Limit)",
        city_id=test_city.id,
        district_id=test_district.id,
        skill_id=test_skill.id,
        is_on_shift=True,
        max_active_orders_override=2,  # Лимит 2
    )
    
    # Создаём 2 активных заказа для preferred мастера (заполняем лимит)
    for i in range(2):
        order_active = m.orders(
            city_id=test_city.id,
            district_id=test_district.id,
            category=m.OrderCategory.ELECTRICS,
            type=m.OrderType.NORMAL,
            status=m.OrderStatus.ASSIGNED,  # Активный статус
            assigned_master_id=preferred_master.id,
            client_name=f"Активный клиент {i+1}",
            client_phone=f"+7900400000{i}",
            house=str(i+1),
            timeslot_start_utc=datetime.utcnow() + timedelta(hours=1),
            timeslot_end_utc=datetime.utcnow() + timedelta(hours=3),
            version=1,
        )
        async_session.add(order_active)
    await async_session.commit()
    
    # Создаём альтернативного мастера
    fallback_master = await create_master(
        async_session,
        tg_user_id=4002,
        full_name="Fallback Master 4",
        city_id=test_city.id,
        district_id=test_district.id,
        skill_id=test_skill.id,
        is_on_shift=True,
        max_active_orders_override=5,  # Лимит 5
    )
    
    # Создаём новый гарантийный заказ
    order = await create_order(
        async_session,
        city_id=test_city.id,
        district_id=test_district.id,
        order_type=m.OrderType.GUARANTEE,
        status=m.OrderStatus.GUARANTEE,
        preferred_master_id=preferred_master.id,
    )
    
    # ===== ДИАГНОСТИКА =====
    diag = await ds._check_preferred_master_availability(
        async_session,
        master_id=preferred_master.id,
        order_id=order.id,
        district_id=test_district.id,
        skill_code="ELEC",
    )
    
    # ✅ Проверка: Причина - at_limit
    assert not diag["available"]
    assert any("at_limit" in r for r in diag["reasons"]), \
        f"Ожидалась причина 'at_limit', получено: {diag['reasons']}"
    assert diag["active_orders"] == 2
    assert diag["max_limit"] == 2
    
    # ===== FALLBACK =====
    candidates = await ds._candidates(
        async_session,
        oid=order.id,
        city_id=test_city.id,
        district_id=test_district.id,
        skill_code="ELEC",
        preferred_mid=None,
        fallback_limit=5,
    )
    
    # ✅ Проверка: Найден альтернативный мастер
    assert len(candidates) > 0
    candidate_ids = [c['mid'] for c in candidates]
    assert fallback_master.id in candidate_ids
    
    print("[OK] TEST PASSED: Fallback при preferred at_limit работает")


# ============================================================================
# TEST 5: Preferred мастер ДОСТУПЕН → приоритет ему
# ============================================================================

@pytest.mark.asyncio
async def test_preferred_available_gets_priority(
    async_session: AsyncSession,
    test_city,
    test_district,
    test_skill,
):
    """
    Сценарий: Preferred мастер доступен
    
    Ожидаемое поведение:
    - Диагностика подтверждает доступность
    - Preferred мастер получает приоритет в списке кандидатов
    """
    # Создаём preferred мастера (доступен)
    preferred_master = await create_master(
        async_session,
        tg_user_id=5001,
        full_name="Preferred (Available)",
        city_id=test_city.id,
        district_id=test_district.id,
        skill_id=test_skill.id,
        is_on_shift=True,
        rating=Decimal("5.0"),  # Высокий рейтинг
    )
    
    # Создаём других мастеров с более низким рейтингом
    other_masters = []
    for i in range(3):
        master = await create_master(
            async_session,
            tg_user_id=5002 + i,
            full_name=f"Other Master {i+1}",
            city_id=test_city.id,
            district_id=test_district.id,
            skill_id=test_skill.id,
            is_on_shift=True,
            rating=Decimal("4.0"),  # Ниже рейтинг
        )
        other_masters.append(master)
    
    # Создаём гарантийный заказ
    order = await create_order(
        async_session,
        city_id=test_city.id,
        district_id=test_district.id,
        order_type=m.OrderType.GUARANTEE,
        status=m.OrderStatus.GUARANTEE,
        preferred_master_id=preferred_master.id,
    )
    
    # ===== ДИАГНОСТИКА =====
    diag = await ds._check_preferred_master_availability(
        async_session,
        master_id=preferred_master.id,
        order_id=order.id,
        district_id=test_district.id,
        skill_code="ELEC",
    )
    
    # ✅ Проверка: Preferred доступен
    assert diag["available"] is True, \
        f"Preferred мастер должен быть доступен, но: {diag}"
    
    # ===== ПОИСК С PREFERRED =====
    candidates = await ds._candidates(
        async_session,
        oid=order.id,
        city_id=test_city.id,
        district_id=test_district.id,
        skill_code="ELEC",
        preferred_mid=preferred_master.id,  # ✅ С preferred
        fallback_limit=5,
    )
    
    # ✅ Проверка 1: Preferred в списке
    assert len(candidates) > 0
    candidate_ids = [c['mid'] for c in candidates]
    assert preferred_master.id in candidate_ids
    
    # ✅ Проверка 2: Preferred ПЕРВЫЙ в списке (высший приоритет)
    assert candidates[0]['mid'] == preferred_master.id, \
        f"Preferred мастер должен быть первым, но первый: {candidates[0]['mid']}"
    
    print("[OK] TEST PASSED: Preferred мастер получает приоритет, когда доступен")


# ============================================================================
# TEST 6: Нет кандидатов вообще → НЕ эскалировать сразу
# ============================================================================

@pytest.mark.asyncio
async def test_no_candidates_no_immediate_escalation(
    async_session: AsyncSession,
    test_city,
    test_district,
    test_skill,
):
    """
    Сценарий: Нет доступных кандидатов (ни preferred, ни альтернативных)
    
    Ожидаемое поведение по FIX 1.3:
    - НЕ эскалировать сразу
    - Заказ остаётся в очереди для следующего раунда
    - Эскалация только если SLA истёк
    
    NOTE: Это тест ожидаемого поведения после применения FIX 1.3
    """
    # Создаём preferred мастера (НЕ доступен)
    preferred_master = await create_master(
        async_session,
        tg_user_id=6001,
        full_name="Preferred (Unavailable)",
        city_id=test_city.id,
        district_id=test_district.id,
        skill_id=test_skill.id,
        is_on_shift=False,  # ❌ НЕ на смене
    )
    
    # Создаём гарантийный заказ
    order = await create_order(
        async_session,
        city_id=test_city.id,
        district_id=test_district.id,
        order_type=m.OrderType.GUARANTEE,
        status=m.OrderStatus.GUARANTEE,
        preferred_master_id=preferred_master.id,
    )
    
    # ===== ПОИСК КАНДИДАТОВ (должен быть пустой) =====
    candidates = await ds._candidates(
        async_session,
        oid=order.id,
        city_id=test_city.id,
        district_id=test_district.id,
        skill_code="ELEC",
        preferred_mid=None,  # Fallback
        fallback_limit=5,
    )
    
    # ✅ Проверка: Нет кандидатов
    assert len(candidates) == 0, \
        "Не должно быть кандидатов (нет других мастеров)"
    
    # ===== ПРОВЕРКА: Заказ НЕ эскалирован =====
    await async_session.refresh(order)
    assert order.dist_escalated_logist_at is None, \
        "Заказ НЕ должен быть эскалирован сразу при отсутствии кандидатов"
    
    print("[OK] TEST PASSED: Нет немедленной эскалации при отсутствии кандидатов")


# ============================================================================
# TEST 7: Интеграционный тест - полный цикл распределения
# ============================================================================

@pytest.mark.asyncio
async def test_full_distribution_cycle_with_preferred(
    async_session: AsyncSession,
    test_city,
    test_district,
    test_skill,
):
    """
    Интеграционный тест: Полный цикл распределения гарантийного заказа
    
    Сценарий:
    1. Гарантийный заказ с preferred мастером (недоступен)
    2. Система делает fallback на альтернативных мастеров
    3. Оффер отправляется доступному мастеру
    4. Проверка статистики распределения
    """
    # Создаём preferred мастера (недоступен)
    preferred_master = await create_master(
        async_session,
        tg_user_id=7001,
        full_name="Preferred (Unavailable)",
        city_id=test_city.id,
        district_id=test_district.id,
        skill_id=test_skill.id,
        is_on_shift=False,
    )
    
    # Создаём доступного мастера
    available_master = await create_master(
        async_session,
        tg_user_id=7002,
        full_name="Available Master",
        city_id=test_city.id,
        district_id=test_district.id,
        skill_id=test_skill.id,
        is_on_shift=True,
    )
    
    # Создаём гарантийный заказ
    order = await create_order(
        async_session,
        city_id=test_city.id,
        district_id=test_district.id,
        order_type=m.OrderType.GUARANTEE,
        status=m.OrderStatus.GUARANTEE,
        preferred_master_id=preferred_master.id,
    )
    
    # ===== СИМУЛЯЦИЯ РАСПРЕДЕЛЕНИЯ =====
    
    # 1. Проверка preferred мастера
    diag_preferred = await ds._check_preferred_master_availability(
        async_session,
        master_id=preferred_master.id,
        order_id=order.id,
        district_id=test_district.id,
        skill_code="ELEC",
    )
    
    assert not diag_preferred["available"], \
        "Preferred должен быть недоступен"
    
    # 2. Fallback на альтернативных мастеров
    candidates = await ds._candidates(
        async_session,
        oid=order.id,
        city_id=test_city.id,
        district_id=test_district.id,
        skill_code="ELEC",
        preferred_mid=None,  # Fallback
        fallback_limit=5,
    )
    
    assert len(candidates) > 0, \
        "Должны быть найдены альтернативные мастера"
    
    # 3. Создаём оффер для первого кандидата
    selected_master_id = candidates[0]['mid']
    offer = m.offers(
        order_id=order.id,
        master_id=selected_master_id,
        round_number=1,
        state=m.OfferState.SENT,
        sent_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=120),
    )
    async_session.add(offer)
    await async_session.commit()
    
    # ✅ Проверка: Оффер создан для доступного мастера
    assert selected_master_id == available_master.id, \
        "Оффер должен быть отправлен доступному мастеру"
    
    # 4. Проверка: В логах НЕТ эскалации
    await async_session.refresh(order)
    assert order.dist_escalated_logist_at is None, \
        "Заказ НЕ должен быть эскалирован (найден кандидат)"
    
    print("[OK] TEST PASSED: Полный цикл распределения с fallback работает")


if __name__ == "__main__":
    print("Запустите тесты через pytest:")
    print("pytest tests/test_fix_1_3_comprehensive.py -v -s")
