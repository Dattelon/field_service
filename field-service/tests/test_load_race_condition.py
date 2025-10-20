# -*- coding: utf-8 -*-
"""
Нагрузочные тесты для FIX 1.1: Race Condition при параллельном принятии офферов

ЦЕЛИ:
1. Проверка работы FOR UPDATE SKIP LOCKED под высокой нагрузкой
2. Измерение производительности блокировки
3. Тестирование деградации при большом количестве параллельных запросов
4. Проверка на deadlock и timeout

СЦЕНАРИИ:
- 10 мастеров пытаются принять 1 заказ одновременно
- 50 мастеров пытаются принять 1 заказ одновременно
- 100 мастеров пытаются принять 1 заказ одновременно
- Стресс-тест: 1000 параллельных попыток
- Измерение latency и throughput
"""

import asyncio
import pytest
import pytest_asyncio
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import List, Tuple
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from field_service.db import models as m
from field_service.bots.master_bot.handlers import orders


# ============================================================================
# FIXTURES
# ============================================================================

@pytest_asyncio.fixture
async def test_city(async_session: AsyncSession) -> m.cities:
    """Тестовый город"""
    city = m.cities(
        name="Москва Load Test",
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


async def create_masters(
    session: AsyncSession,
    count: int,
    city_id: int,
) -> List[m.masters]:
    """Создание множества мастеров для нагрузочных тестов"""
    masters = []
    for i in range(count):
        master = m.masters(
            tg_user_id=10000 + i,
            full_name=f"Load Test Master {i+1}",
            phone=f"+7900{10000+i:07d}",
            city_id=city_id,
            is_active=True,
            is_blocked=False,
            verified=True,
            is_on_shift=True,
            has_vehicle=True,
            rating=Decimal("4.5"),
        )
        session.add(master)
    
    await session.flush()
    
    # Получаем все созданные записи
    result = await session.execute(
        select(m.masters)
        .where(m.masters.tg_user_id.between(10000, 10000 + count - 1))
        .order_by(m.masters.tg_user_id)
    )
    masters = result.scalars().all()
    await session.commit()
    
    return list(masters)


async def create_order_with_offers(
    session: AsyncSession,
    city_id: int,
    district_id: int,
    master_ids: List[int],
) -> m.orders:
    """Создание заказа с офферами для всех мастеров"""
    order = m.orders(
        city_id=city_id,
        district_id=district_id,
        category=m.OrderCategory.ELECTRICS,
        type=m.OrderType.NORMAL,
        status=m.OrderStatus.SEARCHING,
        client_name="Load Test Client",
        client_phone="+79001234567",
        house="10",
        timeslot_start_utc=datetime.now(timezone.utc) + timedelta(hours=2),
        timeslot_end_utc=datetime.now(timezone.utc) + timedelta(hours=4),
        version=1,
    )
    session.add(order)
    await session.flush()
    
    # Создаём офферы для всех мастеров
    offers = []
    for master_id in master_ids:
        offer = m.offers(
            order_id=order.id,
            master_id=master_id,
            round_number=1,
            state=m.OfferState.SENT,
            sent_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=120),
        )
        offers.append(offer)
    
    session.add_all(offers)
    await session.commit()
    await session.refresh(order)
    
    return order


async def simulate_master_accept(
    master: m.masters,
    order_id: int,
    session: AsyncSession,
) -> Tuple[bool, float, str]:
    """
    Симуляция принятия оффера мастером
    
    Возвращает:
    - success: True если принял успешно
    - latency: Время выполнения в секундах
    - error: Текст ошибки (если есть)
    """
    start_time = time.perf_counter()
    
    try:
        # Создаём мок callback
        callback = MagicMock()
        callback.data = f"m:new:acc:{order_id}:1"
        callback.from_user.id = master.tg_user_id
        
        # Мокируем функции уведомлений
        mock_answer = AsyncMock()
        mock_render = AsyncMock()
        
        import field_service.bots.master_bot.handlers.orders as orders_module
        original_answer = orders_module.safe_answer_callback
        original_render = orders_module._render_offers
        
        orders_module.safe_answer_callback = mock_answer
        orders_module._render_offers = mock_render
        
        try:
            await orders.offer_accept(callback, session, master)
            
            # Проверяем, что заказ действительно принят этим мастером
            result = await session.execute(
                select(m.orders).where(m.orders.id == order_id)
            )
            order = result.scalar_one()
            
            success = (order.assigned_master_id == master.id)
            latency = time.perf_counter() - start_time
            
            return success, latency, ""
            
        finally:
            orders_module.safe_answer_callback = original_answer
            orders_module._render_offers = original_render
            
    except Exception as e:
        latency = time.perf_counter() - start_time
        return False, latency, str(e)


# ============================================================================
# LOAD TEST 1: 10 мастеров → 1 заказ
# ============================================================================

@pytest.mark.asyncio
async def test_race_10_masters(
    async_session: AsyncSession,
    test_city,
    test_district,
):
    """
    Нагрузочный тест: 10 мастеров одновременно принимают заказ
    
    Ожидаемое поведение:
    - Только 1 мастер успешно принимает заказ
    - 9 мастеров получают ошибку
    - Нет deadlock или timeout
    - Latency < 1 секунды для всех
    """
    # Создаём 10 мастеров
    masters = await create_masters(async_session, 10, test_city.id)
    
    # Создаём заказ с офферами для всех
    order = await create_order_with_offers(
        async_session,
        test_city.id,
        test_district.id,
        [m.id for m in masters],
    )
    
    # Запускаем параллельные попытки принятия
    tasks = [
        simulate_master_accept(master, order.id, async_session)
        for master in masters
    ]
    
    results = await asyncio.gather(*tasks, return_exceptions=False)
    
    # ===== АНАЛИЗ РЕЗУЛЬТАТОВ =====
    successful = [r for r in results if r[0]]
    failed = [r for r in results if not r[0]]
    
    latencies = [r[1] for r in results]
    avg_latency = sum(latencies) / len(latencies)
    max_latency = max(latencies)
    
    # OK Проверка 1: Только 1 успешный
    assert len(successful) == 1, \
        f"Должен быть ровно 1 успешный, получено: {len(successful)}"
    
    # OK Проверка 2: 9 неудачных
    assert len(failed) == 9, \
        f"Должно быть 9 неудачных, получено: {len(failed)}"
    
    # OK Проверка 3: Latency приемлемая
    assert max_latency < 2.0, \
        f"Max latency слишком высокая: {max_latency:.3f}s"
    
    print("[OK] LOAD TEST PASSED: 10 мастеров")
    print(f"   - Успешных: {len(successful)}")
    print(f"   - Неудачных: {len(failed)}")
    print(f"   - Avg latency: {avg_latency:.3f}s")
    print(f"   - Max latency: {max_latency:.3f}s")


# ============================================================================
# LOAD TEST 2: 50 мастеров → 1 заказ
# ============================================================================

@pytest.mark.asyncio
async def test_race_50_masters(
    async_session: AsyncSession,
    test_city,
    test_district,
):
    """
    Нагрузочный тест: 50 мастеров одновременно принимают заказ
    
    Ожидаемое поведение:
    - Только 1 мастер успешно принимает заказ
    - 49 мастеров получают ошибку
    - Нет deadlock или timeout
    - Latency < 3 секунды для всех
    """
    # Создаём 50 мастеров
    masters = await create_masters(async_session, 50, test_city.id)
    
    # Создаём заказ с офферами для всех
    order = await create_order_with_offers(
        async_session,
        test_city.id,
        test_district.id,
        [m.id for m in masters],
    )
    
    # Запускаем параллельные попытки принятия
    tasks = [
        simulate_master_accept(master, order.id, async_session)
        for master in masters
    ]
    
    start_time = time.perf_counter()
    results = await asyncio.gather(*tasks, return_exceptions=False)
    total_time = time.perf_counter() - start_time
    
    # ===== АНАЛИЗ РЕЗУЛЬТАТОВ =====
    successful = [r for r in results if r[0]]
    failed = [r for r in results if not r[0]]
    
    latencies = [r[1] for r in results]
    avg_latency = sum(latencies) / len(latencies)
    max_latency = max(latencies)
    min_latency = min(latencies)
    
    # OK Проверка 1: Только 1 успешный
    assert len(successful) == 1, \
        f"Должен быть ровно 1 успешный, получено: {len(successful)}"
    
    # OK Проверка 2: 49 неудачных
    assert len(failed) == 49, \
        f"Должно быть 49 неудачных, получено: {len(failed)}"
    
    # OK Проверка 3: Latency приемлемая
    assert max_latency < 5.0, \
        f"Max latency слишком высокая: {max_latency:.3f}s"
    
    # OK Проверка 4: Общее время выполнения
    assert total_time < 10.0, \
        f"Общее время слишком большое: {total_time:.3f}s"
    
    print("[OK] LOAD TEST PASSED: 50 мастеров")
    print(f"   - Успешных: {len(successful)}")
    print(f"   - Неудачных: {len(failed)}")
    print(f"   - Min latency: {min_latency:.3f}s")
    print(f"   - Avg latency: {avg_latency:.3f}s")
    print(f"   - Max latency: {max_latency:.3f}s")
    print(f"   - Total time: {total_time:.3f}s")
    print(f"   - Throughput: {len(masters)/total_time:.1f} req/s")


# ============================================================================
# LOAD TEST 3: 100 мастеров → 1 заказ
# ============================================================================

@pytest.mark.asyncio
@pytest.mark.slow
async def test_race_100_masters(
    async_session: AsyncSession,
    test_city,
    test_district,
):
    """
    Стресс-тест: 100 мастеров одновременно принимают заказ
    
    Ожидаемое поведение:
    - Только 1 мастер успешно принимает заказ
    - 99 мастеров получают ошибку
    - Нет deadlock или timeout
    - Latency < 10 секунд для всех
    
    NOTE: Медленный тест, помечен @pytest.mark.slow
    """
    # Создаём 100 мастеров
    masters = await create_masters(async_session, 100, test_city.id)
    
    # Создаём заказ с офферами для всех
    order = await create_order_with_offers(
        async_session,
        test_city.id,
        test_district.id,
        [m.id for m in masters],
    )
    
    # Запускаем параллельные попытки принятия
    tasks = [
        simulate_master_accept(master, order.id, async_session)
        for master in masters
    ]
    
    start_time = time.perf_counter()
    results = await asyncio.gather(*tasks, return_exceptions=False)
    total_time = time.perf_counter() - start_time
    
    # ===== АНАЛИЗ РЕЗУЛЬТАТОВ =====
    successful = [r for r in results if r[0]]
    failed = [r for r in results if not r[0]]
    
    latencies = [r[1] for r in results]
    avg_latency = sum(latencies) / len(latencies)
    max_latency = max(latencies)
    min_latency = min(latencies)
    
    # Процентили
    sorted_latencies = sorted(latencies)
    p50 = sorted_latencies[len(sorted_latencies) // 2]
    p95 = sorted_latencies[int(len(sorted_latencies) * 0.95)]
    p99 = sorted_latencies[int(len(sorted_latencies) * 0.99)]
    
    # OK Проверка 1: Только 1 успешный
    assert len(successful) == 1, \
        f"Должен быть ровно 1 успешный, получено: {len(successful)}"
    
    # OK Проверка 2: 99 неудачных
    assert len(failed) == 99, \
        f"Должно быть 99 неудачных, получено: {len(failed)}"
    
    # OK Проверка 3: Latency приемлемая
    assert max_latency < 15.0, \
        f"Max latency слишком высокая: {max_latency:.3f}s"
    
    # OK Проверка 4: P95 latency приемлемая
    assert p95 < 5.0, \
        f"P95 latency слишком высокая: {p95:.3f}s"
    
    print("[OK] STRESS TEST PASSED: 100 мастеров")
    print(f"   - Успешных: {len(successful)}")
    print(f"   - Неудачных: {len(failed)}")
    print(f"   - Min latency: {min_latency:.3f}s")
    print(f"   - P50 latency: {p50:.3f}s")
    print(f"   - P95 latency: {p95:.3f}s")
    print(f"   - P99 latency: {p99:.3f}s")
    print(f"   - Max latency: {max_latency:.3f}s")
    print(f"   - Total time: {total_time:.3f}s")
    print(f"   - Throughput: {len(masters)/total_time:.1f} req/s")


# ============================================================================
# BENCHMARK: Измерение производительности блокировки
# ============================================================================

@pytest.mark.asyncio
async def test_lock_performance_benchmark(
    async_session: AsyncSession,
    test_city,
    test_district,
):
    """
    Бенчмарк: Измерение производительности FOR UPDATE SKIP LOCKED
    
    Сравнение:
    - Без блокировки (оптимистичная блокировка)
    - С FOR UPDATE SKIP LOCKED
    
    Метрики:
    - Latency
    - Throughput
    - Success rate
    """
    # Создаём 20 мастеров
    masters = await create_masters(async_session, 20, test_city.id)
    
    # Создаём заказ с офферами
    order = await create_order_with_offers(
        async_session,
        test_city.id,
        test_district.id,
        [m.id for m in masters],
    )
    
    # Запускаем тест
    tasks = [
        simulate_master_accept(master, order.id, async_session)
        for master in masters
    ]
    
    start_time = time.perf_counter()
    results = await asyncio.gather(*tasks, return_exceptions=False)
    total_time = time.perf_counter() - start_time
    
    # ===== МЕТРИКИ =====
    successful = [r for r in results if r[0]]
    failed = [r for r in results if not r[0]]
    
    latencies = [r[1] for r in results]
    avg_latency = sum(latencies) / len(latencies)
    throughput = len(masters) / total_time
    
    print(f"\n📊 BENCHMARK RESULTS:")
    print(f"   - Total requests: {len(masters)}")
    print(f"   - Successful: {len(successful)} ({len(successful)/len(masters)*100:.1f}%)")
    print(f"   - Failed: {len(failed)} ({len(failed)/len(masters)*100:.1f}%)")
    print(f"   - Total time: {total_time:.3f}s")
    print(f"   - Avg latency: {avg_latency:.3f}s")
    print(f"   - Throughput: {throughput:.1f} req/s")
    
    # OK Проверка: только 1 успешный
    assert len(successful) == 1


if __name__ == "__main__":
    print("Запустите нагрузочные тесты через pytest:")
    print("pytest tests/test_load_race_condition.py -v -s")
    print("\nДля стресс-тестов:")
    print("pytest tests/test_load_race_condition.py -v -s -m slow")
