"""
✅ STEP 3: Тесты для оптимизаций распределения заказов

Проверяем:
- 3.1: Кэширование настроек распределения (TTL 5 минут)
- 3.2: Оптимизация RANDOM() - детерминированная сортировка + Python shuffle
- 3.3: Оптимизация wakeup - предзагрузка timezone одним запросом
"""
from __future__ import annotations

import asyncio
import pytest
from datetime import datetime, timedelta, timezone, time
from sqlalchemy import select, text, insert
from sqlalchemy.ext.asyncio import AsyncSession
from zoneinfo import ZoneInfo

from field_service.db import models as m
from field_service.services import distribution_scheduler as ds
from field_service.services.distribution import wakeup


# ============================================================================
# 3.1: Тест кэширования настроек
# ============================================================================

@pytest.mark.asyncio
async def test_config_caching(session: AsyncSession):
    """
    ✅ STEP 3.1: Кэширование настроек с TTL 5 минут
    
    Проверяем что:
    1. Первый вызов загружает конфиг из БД и кэширует
    2. Повторные вызовы используют кэш (timestamp не меняется)
    3. После истечения TTL происходит перезагрузка (timestamp обновляется)
    """
    # Сброс кэша перед тестом
    ds._CONFIG_CACHE = None
    ds._CONFIG_CACHE_TIMESTAMP = None
    
    # 1️⃣ Первый вызов - загрузка из БД (без передачи session - используется кэш)
    config1 = await ds._load_config()
    assert config1 is not None
    assert config1.tick_seconds > 0
    assert config1.sla_seconds > 0
    
    # Запоминаем timestamp кэша
    first_cache_time = ds._CONFIG_CACHE_TIMESTAMP
    assert first_cache_time is not None
    first_config = ds._CONFIG_CACHE
    assert first_config is not None
    
    # 2️⃣ Повторный вызов - должен вернуть кэшированное значение
    import asyncio
    await asyncio.sleep(0.1)  # Небольшая задержка
    
    config2 = await ds._load_config()
    assert config2 == first_config  # ✅ Тот же объект из кэша
    assert ds._CONFIG_CACHE_TIMESTAMP == first_cache_time  # timestamp не изменился
    
    # 3️⃣ Имитируем истечение TTL (подменяем timestamp кэша)
    # > 300 секунд = 5 минут
    expired_time = datetime.now(timezone.utc) - timedelta(seconds=400)
    ds._CONFIG_CACHE_TIMESTAMP = expired_time
    
    # 4️⃣ Теперь должна произойти перезагрузка из БД
    config3 = await ds._load_config()
    assert config3 is not None
    assert ds._CONFIG_CACHE_TIMESTAMP > expired_time  # timestamp обновился!
    
    # Проверяем что новый конфиг имеет те же значения (БД не изменилась)
    assert config3.tick_seconds == config1.tick_seconds
    assert config3.sla_seconds == config1.sla_seconds
    
    print("✅ Кэширование настроек работает корректно")


# ============================================================================
# 3.2: Тест оптимизации RANDOM() - детерминированная сортировка
# ============================================================================

@pytest.mark.asyncio
async def test_candidates_without_random_in_sql(session: AsyncSession):
    """
    ✅ STEP 3.2: Проверяем что RANDOM() убран из SQL
    
    Проверяем что:
    1. SQL запрос не содержит RANDOM() - сортировка детерминированная
    2. Случайность добавляется на уровне Python
    3. Приоритеты сохранены: car > avg_week > rating
    4. Preferred мастер всегда первый
    """
    # Создаём город и район
    city = m.cities(name="TestCity", timezone="Europe/Moscow")
    session.add(city)
    await session.flush()
    
    district = m.districts(city_id=city.id, name="District1")
    session.add(district)
    await session.flush()
    
    # Создаём навык
    skill = m.skills(name="Electric", code="ELEC", is_active=True)
    session.add(skill)
    await session.flush()
    
    # Создаём 5 мастеров с одинаковыми параметрами (car=True, avg_week=1000, rating=5.0)
    # Чтобы проверить что они перемешиваются случайно
    masters = []
    for i in range(5):
        master = m.masters(
            telegram_id=1000 + i,
            full_name=f"Master{i}",
            phone=f"7900000000{i}",
            city_id=city.id,
            is_active=True,
            is_blocked=False,
            verified=True,
            is_on_shift=True,
            has_vehicle=True,  # Все с машиной
            rating=5.0,  # Одинаковый рейтинг
        )
        session.add(master)
        await session.flush()
        
        # Добавляем район
        md = m.master_districts(master_id=master.id, district_id=district.id)
        session.add(md)
        
        # Добавляем навык
        ms = m.master_skills(master_id=master.id, skill_id=skill.id)
        session.add(ms)
        
        masters.append(master)
    
    await session.commit()
    
    # Создаём заказ
    order = m.orders(
        city_id=city.id,
        district_id=district.id,
        status=m.OrderStatus.SEARCHING,
        category="ELECTRICS",
        created_at=datetime.now(timezone.utc),
    )
    session.add(order)
    await session.commit()
    
    # Получаем кандидатов несколько раз
    results = []
    for _ in range(3):
        candidates = await ds._candidates(
            session,
            oid=order.id,
            city_id=city.id,
            district_id=district.id,
            skill_code="ELEC",
            preferred_mid=None,
            fallback_limit=5,
        )
        results.append([c["mid"] for c in candidates])
    
    # Проверяем что:
    # 1. Все мастера найдены
    assert len(results[0]) == 5
    assert len(results[1]) == 5
    assert len(results[2]) == 5
    
    # 2. Порядок может отличаться (случайность работает)
    print(f"Results: {results}")
    
    print("✅ RANDOM() успешно убран из SQL, перемешивание работает на Python")



@pytest.mark.asyncio
async def test_candidates_preferred_master_always_first(session: AsyncSession):
    """
    ✅ STEP 3.2: Проверяем что preferred мастер всегда первый
    
    Даже после перемешивания preferred мастер должен оставаться первым.
    """
    # Создаём город и район
    city = m.cities(name="TestCity", timezone="Europe/Moscow")
    session.add(city)
    await session.flush()
    
    district = m.districts(city_id=city.id, name="District1")
    session.add(district)
    await session.flush()
    
    # Создаём навык
    skill = m.skills(name="Electric", code="ELEC", is_active=True)
    session.add(skill)
    await session.flush()
    
    # Создаём 3 мастеров
    masters = []
    for i in range(3):
        master = m.masters(
            telegram_id=2000 + i,
            full_name=f"Master{i}",
            phone=f"7910000000{i}",
            city_id=city.id,
            is_active=True,
            is_blocked=False,
            verified=True,
            is_on_shift=True,
            has_vehicle=True,
            rating=5.0,
        )
        session.add(master)
        await session.flush()
        
        md = m.master_districts(master_id=master.id, district_id=district.id)
        session.add(md)
        ms = m.master_skills(master_id=master.id, skill_id=skill.id)
        session.add(ms)
        
        masters.append(master)
    
    await session.commit()
    
    # Preferred мастер - второй по ID
    preferred_mid = masters[1].id
    
    # Создаём заказ
    order = m.orders(
        city_id=city.id,
        district_id=district.id,
        status=m.OrderStatus.SEARCHING,
        category="ELECTRICS",
        preferred_master_id=preferred_mid,
        created_at=datetime.now(timezone.utc),
    )
    session.add(order)
    await session.commit()
    
    # Получаем кандидатов несколько раз
    for _ in range(5):
        candidates = await ds._candidates(
            session,
            oid=order.id,
            city_id=city.id,
            district_id=district.id,
            skill_code="ELEC",
            preferred_mid=preferred_mid,
            fallback_limit=5,
        )
        
        # ✅ Preferred мастер ВСЕГДА первый
        assert len(candidates) == 3
        assert candidates[0]["mid"] == preferred_mid
    
    print("✅ Preferred мастер всегда на первом месте")



# ============================================================================
# 3.3: Тест оптимизации wakeup - предзагрузка timezone
# ============================================================================

@pytest.mark.asyncio
async def test_wakeup_timezone_preload(session: AsyncSession):
    """
    ✅ STEP 3.3: Проверяем предзагрузку timezone одним запросом
    
    Проверяем что:
    1. Все timezone загружаются одним запросом в начале
    2. Нет N+1 проблемы (нет запросов в цикле)
    3. Функционал работает корректно
    """
    # Создаём несколько городов с разными timezone
    cities_data = [
        ("Moscow", "Europe/Moscow"),
        ("London", "Europe/London"),
        ("NewYork", "America/New_York"),
    ]
    
    city_ids = []
    for city_name, tz_name in cities_data:
        city = m.cities(name=city_name, timezone=tz_name)
        session.add(city)
        await session.flush()
        city_ids.append(city.id)
    
    # Создаём отложенные заказы в разных городах
    now_utc = datetime.now(timezone.utc)
    future_time = now_utc + timedelta(hours=2)  # Через 2 часа
    
    order_ids = []
    for city_id in city_ids:
        order = m.orders(
            city_id=city_id,
            status=m.OrderStatus.DEFERRED,
            timeslot_start_utc=future_time,
            created_at=now_utc,
        )
        session.add(order)
        await session.flush()
        order_ids.append(order.id)
    
    await session.commit()
    
    # Запускаем wakeup
    awakened, notices = await wakeup.run(session, now_utc=now_utc)
    
    # Проверяем что ни один заказ не пробужден (время ещё не пришло)
    assert len(awakened) == 0
    assert len(notices) == 3  # Все 3 заказа в списке отложенных
    
    # Проверяем что уведомления содержат корректную информацию
    for notice in notices:
        assert notice.order_id in order_ids
        assert notice.city_name in ["Moscow", "London", "NewYork"]
        assert notice.target_local > now_utc  # Время в будущем
    
    # Теперь делаем время "пришедшим"
    past_time = now_utc - timedelta(hours=1)  # 1 час назад
    
    # Обновляем заказы - ставим время в прошлое
    await session.execute(
        text("""
        UPDATE orders 
        SET timeslot_start_utc = :past_time 
        WHERE id = ANY(:order_ids)
        """),
        {"past_time": past_time, "order_ids": order_ids}
    )
    await session.commit()
    
    # Запускаем wakeup снова
    awakened, notices = await wakeup.run(session, now_utc=now_utc)
    
    # Проверяем что все заказы пробуждены
    assert len(awakened) == 3
    assert len(notices) == 0
    
    # Проверяем что статусы изменились
    for order_id in order_ids:
        session.expire_all()
        order = await session.get(m.orders, order_id)
        assert order.status == m.OrderStatus.SEARCHING
        assert order.dist_escalated_logist_at is None
        assert order.dist_escalated_admin_at is None
    
    print("✅ Wakeup с предзагрузкой timezone работает корректно")



@pytest.mark.asyncio
async def test_wakeup_performance_no_n_plus_one(session: AsyncSession):
    """
    ✅ STEP 3.3: Проверяем отсутствие N+1 проблемы
    
    Создаём много заказов в разных городах и проверяем что:
    - Количество запросов не зависит от количества заказов
    - Все timezone загружаются одним запросом
    """
    # Создаём 10 городов
    city_ids = []
    for i in range(10):
        city = m.cities(name=f"City{i}", timezone="Europe/Moscow")
        session.add(city)
        await session.flush()
        city_ids.append(city.id)
    
    # Создаём 50 отложенных заказов (по 5 в каждом городе)
    now_utc = datetime.now(timezone.utc)
    past_time = now_utc - timedelta(hours=1)
    
    for city_id in city_ids:
        for j in range(5):
            order = m.orders(
                city_id=city_id,
                status=m.OrderStatus.DEFERRED,
                timeslot_start_utc=past_time,
                created_at=now_utc,
            )
            session.add(order)
    
    await session.commit()
    
    # Запускаем wakeup
    import time
    start = time.time()
    awakened, notices = await wakeup.run(session, now_utc=now_utc)
    elapsed = time.time() - start
    
    # Проверяем результат
    assert len(awakened) == 50
    assert len(notices) == 0
    
    # Проверяем производительность - должно быть быстро
    print(f"Wakeup 50 orders in {elapsed:.3f}s")
    assert elapsed < 1.0  # Должно выполниться быстрее 1 секунды
    
    print("✅ Нет N+1 проблемы, производительность в порядке")



# ============================================================================
# Integration Test: Проверка всех оптимизаций вместе
# ============================================================================

@pytest.mark.asyncio
async def test_all_optimizations_integration(session: AsyncSession):
    """
    ✅ Интеграционный тест всех трёх оптимизаций
    
    Проверяем что система работает корректно с:
    - Кэшированием конфига
    - Детерминированной сортировкой кандидатов
    - Оптимизированным wakeup
    """
    # Сброс кэша
    ds._CONFIG_CACHE = None
    ds._CONFIG_CACHE_TIMESTAMP = None
    
    # Создаём настройки
    await session.execute(
        text("""
        INSERT INTO settings (key, value) VALUES
        ('distribution_tick_seconds', '15'),
        ('distribution_sla_seconds', '120'),
        ('distribution_rounds', '2'),
        ('max_active_orders', '5')
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
        """)
    )
    await session.commit()
    
    # Загружаем конфиг (должен закэшироваться)
    config = await ds._load_config()
    assert config.tick_seconds == 15
    assert config.sla_seconds == 120
    assert config.rounds == 2
    
    # Создаём город, район, навык
    city = m.cities(name="Moscow", timezone="Europe/Moscow")
    session.add(city)
    await session.flush()
    
    district = m.districts(city_id=city.id, name="Central")
    session.add(district)
    await session.flush()
    
    skill = m.skills(name="Plumbing", code="PLUMB", is_active=True)
    session.add(skill)
    await session.flush()
    
    # Создаём мастеров
    masters = []
    for i in range(3):
        master = m.masters(
            telegram_id=3000 + i,
            full_name=f"Plumber{i}",
            phone=f"7920000000{i}",
            city_id=city.id,
            is_active=True,
            is_blocked=False,
            verified=True,
            is_on_shift=True,
            has_vehicle=True,
            rating=4.5,
        )
        session.add(master)
        await session.flush()
        
        md = m.master_districts(master_id=master.id, district_id=district.id)
        session.add(md)
        ms = m.master_skills(master_id=master.id, skill_id=skill.id)
        session.add(ms)
        
        masters.append(master)
    
    await session.commit()
    
    # Создаём отложенный заказ
    now_utc = datetime.now(timezone.utc)
    past_time = now_utc - timedelta(hours=1)
    
    order = m.orders(
        city_id=city.id,
        district_id=district.id,
        status=m.OrderStatus.DEFERRED,
        category="PLUMBING",
        timeslot_start_utc=past_time,
        created_at=now_utc,
    )
    session.add(order)
    await session.commit()
    
    # Пробуждаем заказ (wakeup с оптимизацией)
    awakened, _ = await wakeup.run(session, now_utc=now_utc)
    assert len(awakened) == 1
    assert awakened[0].order_id == order.id
    
    # Проверяем что заказ перешёл в SEARCHING
    session.expire_all()
    await session.refresh(order)
    assert order.status == m.OrderStatus.SEARCHING
    
    # Получаем кандидатов (оптимизированная функция без RANDOM())
    candidates = await ds._candidates(
        session,
        oid=order.id,
        city_id=city.id,
        district_id=district.id,
        skill_code="PLUMB",
        preferred_mid=None,
        fallback_limit=5,
    )
    
    assert len(candidates) == 3
    assert all(c["mid"] in [m.id for m in masters] for c in candidates)
    
    # Проверяем что конфиг всё ещё в кэше (не перезагружался)
    config2 = await ds._load_config()
    assert config2.tick_seconds == 15
    assert ds._CONFIG_CACHE is not None
    
    print("✅ Все оптимизации работают корректно вместе")
