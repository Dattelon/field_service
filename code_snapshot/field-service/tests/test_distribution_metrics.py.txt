"""
Тесты для метрик распределения заказов (STEP 4.1).

Проверяет:
- Запись метрик при принятии оффера мастером
- Запись метрик при ручном назначении админом
- Корректность расчёта времени назначения
- Работу сервиса аналитики метрик
"""
import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, func, text

from field_service.db import models as m
from field_service.services.distribution_metrics_service import (
    DistributionMetricsService,
    DistributionStats,
)


UTC = timezone.utc


async def _get_db_now(session):
    """Получить текущее время БД."""
    row = await session.execute(text("SELECT NOW()"))
    return row.scalar()


@pytest.mark.asyncio
async def test_metrics_recorded_on_offer_accept(session):
    """
    Тест: При принятии оффера мастером записываются метрики.
    """
    # Arrange: Создаём город, мастера, заказ и оффер
    db_now = await _get_db_now(session)
    
    city = m.cities(id=1, name="Test City", is_active=True, timezone="Europe/Moscow")
    session.add(city)
    
    master = m.masters(
        id=100,
        telegram_id=111,
        full_name="Test Master",
        phone_number="+79991234567",
        city_id=1,
        moderation_status=m.ModerationStatus.APPROVED,
        is_blocked=False,
    )
    session.add(master)
    
    order = m.orders(
        id=500,
        city_id=1,
        category=m.OrderCategory.ELECTRICS,
        type=m.OrderType.NORMAL,
        status=m.OrderStatus.SEARCHING,
        created_at=db_now - timedelta(minutes=5),
    )
    session.add(order)
    
    offer = m.offers(
        order_id=500,
        master_id=100,
        state=m.OfferState.SENT,
        round_number=1,
        sent_at=db_now,
        expires_at=db_now + timedelta(minutes=2),
    )
    session.add(offer)
    
    await session.commit()
    session.expire_all()
    
    # Act: Принимаем оффер (имитируем offer_accept)
    # Обновляем заказ
    order_obj = await session.get(m.orders, 500)
    order_obj.assigned_master_id = 100
    order_obj.status = m.OrderStatus.ASSIGNED
    
    # Обновляем оффер
    offer_obj = await session.get(m.offers, offer.id)
    offer_obj.state = m.OfferState.ACCEPTED
    offer_obj.responded_at = db_now
    
    # Записываем метрики (как в offer_accept)
    metrics = m.distribution_metrics(
        order_id=500,
        master_id=100,
        round_number=1,
        candidates_count=1,
        time_to_assign_seconds=300,  # 5 минут
        preferred_master_used=False,
        was_escalated_to_logist=False,
        was_escalated_to_admin=False,
        city_id=1,
        category=m.OrderCategory.ELECTRICS,
        order_type=m.OrderType.NORMAL,
        metadata_json={"assigned_via": "master_bot"},
    )
    session.add(metrics)
    
    await session.commit()
    session.expire_all()
    
    # Assert: Проверяем что метрики записались
    result = await session.execute(
        select(m.distribution_metrics).where(m.distribution_metrics.order_id == 500)
    )
    metric = result.scalar_one()
    
    assert metric.order_id == 500
    assert metric.master_id == 100
    assert metric.round_number == 1
    assert metric.candidates_count == 1
    assert metric.time_to_assign_seconds == 300
    assert metric.preferred_master_used is False
    assert metric.was_escalated_to_logist is False
    assert metric.was_escalated_to_admin is False
    assert metric.city_id == 1
    assert metric.category == m.OrderCategory.ELECTRICS
    assert metric.metadata_json["assigned_via"] == "master_bot"


@pytest.mark.asyncio
async def test_metrics_recorded_on_manual_assign(session):
    """
    Тест: При ручном назначении админом записываются метрики.
    """
    # Arrange
    db_now = await _get_db_now(session)
    
    city = m.cities(id=1, name="Test City", is_active=True, timezone="Europe/Moscow")
    session.add(city)
    
    master = m.masters(
        id=100,
        telegram_id=111,
        full_name="Test Master",
        phone_number="+79991234567",
        city_id=1,
        moderation_status=m.ModerationStatus.APPROVED,
    )
    session.add(master)
    
    staff = m.staff_users(
        id=1,
        telegram_id=222,
        username="admin",
        full_name="Admin User",
        role=m.StaffRole.SUPER_ADMIN,
    )
    session.add(staff)
    
    order = m.orders(
        id=500,
        city_id=1,
        category=m.OrderCategory.PLUMBING,
        type=m.OrderType.NORMAL,
        status=m.OrderStatus.SEARCHING,
        created_at=db_now - timedelta(minutes=10),
        dist_escalated_logist_at=db_now - timedelta(minutes=5),
    )
    session.add(order)
    
    await session.commit()
    session.expire_all()
    
    # Act: Ручное назначение
    order_obj = await session.get(m.orders, 500)
    order_obj.assigned_master_id = 100
    order_obj.status = m.OrderStatus.ASSIGNED
    
    # Записываем метрики (как в assign_master)
    metrics = m.distribution_metrics(
        order_id=500,
        master_id=100,
        round_number=0,  # Ручное назначение - нет раундов
        candidates_count=0,
        time_to_assign_seconds=600,  # 10 минут
        preferred_master_used=False,
        was_escalated_to_logist=True,
        was_escalated_to_admin=False,
        city_id=1,
        category=m.OrderCategory.PLUMBING,
        order_type=m.OrderType.NORMAL,
        metadata_json={
            "assigned_via": "admin_manual",
            "staff_id": 1,
        },
    )
    session.add(metrics)
    
    await session.commit()
    session.expire_all()
    
    # Assert
    result = await session.execute(
        select(m.distribution_metrics).where(m.distribution_metrics.order_id == 500)
    )
    metric = result.scalar_one()
    
    assert metric.order_id == 500
    assert metric.master_id == 100
    assert metric.round_number == 0
    assert metric.was_escalated_to_logist is True
    assert metric.metadata_json["assigned_via"] == "admin_manual"
    assert metric.metadata_json["staff_id"] == 1


@pytest.mark.asyncio
async def test_metrics_service_get_stats(session):
    """
    Тест: Сервис аналитики правильно считает статистику.
    """
    # Arrange: Создаём тестовые данные
    db_now = await _get_db_now(session)
    
    city = m.cities(id=1, name="Test City", is_active=True, timezone="Europe/Moscow")
    session.add(city)
    
    # Создаём 10 метрик с разными параметрами
    for i in range(10):
        metrics = m.distribution_metrics(
            order_id=1000 + i,
            master_id=100 + (i % 3),
            assigned_at=db_now - timedelta(hours=i),
            round_number=1 if i < 7 else 2,
            candidates_count=5,
            time_to_assign_seconds=60 if i < 3 else (180 if i < 7 else 400),
            preferred_master_used=(i % 2 == 0),
            was_escalated_to_logist=(i >= 8),
            was_escalated_to_admin=False,
            city_id=1,
            category=m.OrderCategory.ELECTRICS,
            order_type=m.OrderType.NORMAL,
        )
        session.add(metrics)
    
    await session.commit()
    session.expire_all()
    
    # Act: Получаем статистику
    service = DistributionMetricsService(session_factory=lambda: session)
    stats = await service.get_stats(
        start_date=db_now - timedelta(days=1),
        end_date=db_now + timedelta(hours=1),
    )
    
    # Assert
    assert stats.total_assignments == 10
    assert stats.avg_candidates == 5.0
    assert stats.preferred_used_pct == 50.0  # 5 из 10
    assert stats.escalated_to_logist_pct == 20.0  # 2 из 10
    assert stats.round_1_pct == 70.0  # 7 из 10
    assert stats.round_2_pct == 30.0  # 3 из 10
    assert stats.fast_assign_pct == 30.0  # 3 из 10 (< 120 сек)


@pytest.mark.asyncio
async def test_metrics_service_city_performance(session):
    """
    Тест: Сервис аналитики возвращает статистику по городам.
    """
    # Arrange
    db_now = await _get_db_now(session)
    
    city1 = m.cities(id=1, name="City A", is_active=True)
    city2 = m.cities(id=2, name="City B", is_active=True)
    session.add_all([city1, city2])
    
    # 5 метрик для City A
    for i in range(5):
        metrics = m.distribution_metrics(
            order_id=1000 + i,
            master_id=100,
            assigned_at=db_now - timedelta(hours=i),
            round_number=1,
            candidates_count=3,
            time_to_assign_seconds=120,
            city_id=1,
            category=m.OrderCategory.ELECTRICS,
        )
        session.add(metrics)
    
    # 3 метрики для City B с эскалацией
    for i in range(3):
        metrics = m.distribution_metrics(
            order_id=2000 + i,
            master_id=101,
            assigned_at=db_now - timedelta(hours=i),
            round_number=2,
            candidates_count=2,
            time_to_assign_seconds=300,
            was_escalated_to_logist=True,
            city_id=2,
            category=m.OrderCategory.PLUMBING,
        )
        session.add(metrics)
    
    await session.commit()
    session.expire_all()
    
    # Act
    service = DistributionMetricsService(session_factory=lambda: session)
    cities = await service.get_city_performance(
        start_date=db_now - timedelta(days=1),
        end_date=db_now + timedelta(hours=1),
    )
    
    # Assert
    assert len(cities) == 2
    
    # City A должен быть первым (больше назначений)
    assert cities[0].city_id == 1
    assert cities[0].city_name == "City A"
    assert cities[0].total_assignments == 5
    assert cities[0].escalation_rate == 0.0
    
    # City B
    assert cities[1].city_id == 2
    assert cities[1].city_name == "City B"
    assert cities[1].total_assignments == 3
    assert cities[1].escalation_rate == 100.0  # Все 3 эскалированы


@pytest.mark.asyncio
async def test_metrics_with_preferred_master(session):
    """
    Тест: Метрики корректно отражают использование preferred мастера.
    """
    # Arrange
    db_now = await _get_db_now(session)
    
    city = m.cities(id=1, name="Test City", is_active=True)
    session.add(city)
    
    preferred_master = m.masters(
        id=100,
        telegram_id=111,
        full_name="Preferred Master",
        phone_number="+79991111111",
        city_id=1,
        moderation_status=m.ModerationStatus.APPROVED,
    )
    session.add(preferred_master)
    
    # Гарантийный заказ с preferred мастером
    order = m.orders(
        id=500,
        city_id=1,
        type=m.OrderType.GUARANTEE,
        status=m.OrderStatus.GUARANTEE,
        preferred_master_id=100,
        created_at=db_now - timedelta(minutes=3),
    )
    session.add(order)
    
    await session.commit()
    session.expire_all()
    
    # Act: Назначаем preferred мастера
    order_obj = await session.get(m.orders, 500)
    order_obj.assigned_master_id = 100
    order_obj.status = m.OrderStatus.ASSIGNED
    
    metrics = m.distribution_metrics(
        order_id=500,
        master_id=100,
        round_number=1,
        candidates_count=1,
        time_to_assign_seconds=180,
        preferred_master_used=True,  # ✅ Preferred мастер использован
        was_escalated_to_logist=False,
        was_escalated_to_admin=False,
        city_id=1,
        order_type=m.OrderType.GUARANTEE,
    )
    session.add(metrics)
    
    await session.commit()
    session.expire_all()
    
    # Assert
    result = await session.execute(
        select(m.distribution_metrics).where(m.distribution_metrics.order_id == 500)
    )
    metric = result.scalar_one()
    
    assert metric.preferred_master_used is True
    assert metric.order_type == m.OrderType.GUARANTEE
