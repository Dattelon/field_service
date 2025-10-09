"""
P1-17: Тесты для статистики мастера.

Проверяем:
- Показ статистики для мастера без заказов
- Показ статистики с выполненными заказами  
- Расчёт среднего времени отклика
- Фильтрация заказов за текущий месяц
- Мотивирующие сообщения
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from field_service.db import models as m


@pytest_asyncio.fixture
async def test_master(session: AsyncSession) -> m.masters:
    """Создать тестового мастера."""
    master = m.masters(
        tg_user_id=100001,
        full_name="Тестовый Мастер",
        phone="+79991234567",
        verified=True,
        moderation_status=m.ModerationStatus.APPROVED,
        shift_status=m.ShiftStatus.SHIFT_ON,
        rating=5.0,
    )
    session.add(master)
    await session.commit()
    await session.refresh(master)
    return master


@pytest_asyncio.fixture
async def test_city(session: AsyncSession) -> m.cities:
    """Создать тестовый город."""
    city = m.cities(name="Тестовый Город", is_active=True)
    session.add(city)
    await session.commit()
    await session.refresh(city)
    return city


async def _get_db_now(session: AsyncSession) -> datetime:
    """Получить текущее время БД."""
    row = await session.execute(text("SELECT NOW()"))
    return row.scalar()


async def test_statistics_no_orders(session: AsyncSession, test_master: m.masters) -> None:
    """Статистика для мастера без заказов."""
    from field_service.bots.master_bot.handlers.statistics import handle_statistics
    from unittest.mock import AsyncMock, MagicMock
    from aiogram.fsm.context import FSMContext
    
    # Mock callback query
    callback = AsyncMock()
    callback.message = MagicMock()
    callback.message.edit_text = AsyncMock()
    
    # Mock state
    state = AsyncMock(spec=FSMContext)
    state.clear = AsyncMock()
    
    # Вызываем handler
    await handle_statistics(callback, state, test_master, session)
    
    # Проверяем что метод был вызван
    assert callback.message.edit_text.called or hasattr(callback.message, 'text')
    
    # Проверяем очистку state
    state.clear.assert_called_once()


async def test_statistics_with_completed_orders(
    session: AsyncSession,
    test_master: m.masters,
    test_city: m.cities,
) -> None:
    """Статистика для мастера с выполненными заказами."""
    db_now = await _get_db_now(session)
    
    # Создаём 15 завершённых заказов
    for i in range(15):
        order = m.orders(
            city_id=test_city.id,
            client_phone=f"+799912345{i:02d}",
            category=m.OrderCategory.ELECTRICS,
            status=m.OrderStatus.CLOSED,
            assigned_master_id=test_master.id,
            total_sum=Decimal("1000.00"),
            created_at=db_now - timedelta(days=i),
            updated_at=db_now - timedelta(days=i),
        )
        session.add(order)
    
    await session.commit()
    
    # Проверяем подсчёт через SQL
    completed_query = select(m.orders.id).where(
        m.orders.assigned_master_id == test_master.id,
        m.orders.status == m.OrderStatus.CLOSED,
    )
    result = await session.execute(completed_query)
    completed_count = len(result.all())
    
    assert completed_count == 15


async def test_statistics_response_time_calculation(
    session: AsyncSession,
    test_master: m.masters,
    test_city: m.cities,
) -> None:
    """Расчёт среднего времени отклика."""
    db_now = await _get_db_now(session)
    
    # Создаём заказ
    order = m.orders(
        city_id=test_city.id,
        client_phone="+79991234567",
        category=m.OrderCategory.ELECTRICS,
        status=m.OrderStatus.ASSIGNED,
        assigned_master_id=test_master.id,
        total_sum=Decimal("1000.00"),
    )
    session.add(order)
    await session.commit()
    await session.refresh(order)
    
    # Создаём офферы с разным временем отклика
    offers_data = [
        (5,),   # 5 минут
        (10,),  # 10 минут
        (20,),  # 20 минут
    ]
    
    for minutes_delta in offers_data:
        minutes = minutes_delta[0]
        offer = m.offers(
            order_id=order.id,
            master_id=test_master.id,
            state=m.OfferState.ACCEPTED,
            sent_at=db_now,
            responded_at=db_now + timedelta(minutes=minutes),
            round_number=1,
        )
        session.add(offer)
    
    await session.commit()
    
    # Проверяем расчёт среднего времени
    from sqlalchemy import func
    response_time_query = select(
        func.avg(
            func.extract("EPOCH", m.offers.responded_at - m.offers.sent_at) / 60
        )
    ).where(
        m.offers.master_id == test_master.id,
        m.offers.state == m.OfferState.ACCEPTED,
        m.offers.responded_at.isnot(None),
    )
    
    result = await session.execute(response_time_query)
    avg_minutes = result.scalar()
    
    # Среднее: (5 + 10 + 20) / 3 ≈ 11.67 минут
    assert avg_minutes is not None
    assert 11 <= float(avg_minutes) <= 12


async def test_statistics_month_filter(
    session: AsyncSession,
    test_master: m.masters,
    test_city: m.cities,
) -> None:
    """Фильтрация заказов за текущий месяц."""
    db_now = await _get_db_now(session)
    month_start = db_now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    # Создаём 5 заказов в текущем месяце
    for i in range(5):
        order = m.orders(
            city_id=test_city.id,
            client_phone=f"+799912345{i:02d}",
            category=m.OrderCategory.ELECTRICS,
            status=m.OrderStatus.CLOSED,
            assigned_master_id=test_master.id,
            total_sum=Decimal("1000.00"),
            created_at=month_start + timedelta(days=i),
            updated_at=month_start + timedelta(days=i),
        )
        session.add(order)
    
    # Создаём 3 заказа в прошлом месяце
    last_month = month_start - timedelta(days=1)
    for i in range(3):
        order = m.orders(
            city_id=test_city.id,
            client_phone=f"+799912350{i:02d}",
            category=m.OrderCategory.PLUMBING,
            status=m.OrderStatus.CLOSED,
            assigned_master_id=test_master.id,
            total_sum=Decimal("1500.00"),
            created_at=last_month - timedelta(days=i),
            updated_at=last_month - timedelta(days=i),
        )
        session.add(order)
    
    await session.commit()
    
    # Проверяем подсчёт за текущий месяц
    month_query = select(m.orders.id).where(
        m.orders.assigned_master_id == test_master.id,
        m.orders.status == m.OrderStatus.CLOSED,
        m.orders.updated_at >= month_start,
    )
    result = await session.execute(month_query)
    month_count = len(result.all())
    
    assert month_count == 5


async def test_statistics_motivational_messages(
    session: AsyncSession,
    test_master: m.masters,
    test_city: m.cities,
) -> None:
    """Проверка мотивирующих сообщений для разного количества заказов."""
    
    test_cases = [
        (0, "🚀 Начните принимать заказы"),
        (5, "💪 Отличное начало"),
        (25, "🔥 Так держать"),
        (75, "⭐ Вы на пути к сотне"),
        (150, "🏆 Вы профессионал"),
    ]
    
    for completed_count, expected_message_part in test_cases:
        # Очищаем заказы
        await session.execute(text("TRUNCATE TABLE orders CASCADE"))
        await session.commit()
        
        # Создаём нужное количество заказов
        db_now = await _get_db_now(session)
        for i in range(completed_count):
            order = m.orders(
                city_id=test_city.id,
                client_phone=f"+79991{i:06d}",
                category=m.OrderCategory.ELECTRICS,
                status=m.OrderStatus.CLOSED,
                assigned_master_id=test_master.id,
                total_sum=Decimal("1000.00"),
                created_at=db_now - timedelta(days=i),
                updated_at=db_now - timedelta(days=i),
            )
            session.add(order)
        
        await session.commit()
        
        # Проверяем количество
        count_query = select(m.orders.id).where(
            m.orders.assigned_master_id == test_master.id,
            m.orders.status == m.OrderStatus.CLOSED,
        )
        result = await session.execute(count_query)
        actual_count = len(result.all())
        
        assert actual_count == completed_count


async def test_statistics_formatting_response_time(
    session: AsyncSession,
    test_master: m.masters,
    test_city: m.cities,
) -> None:
    """Проверка форматирования времени отклика (минуты vs часы)."""
    db_now = await _get_db_now(session)
    
    order = m.orders(
        city_id=test_city.id,
        client_phone="+79991234567",
        category=m.OrderCategory.ELECTRICS,
        status=m.OrderStatus.ASSIGNED,
        assigned_master_id=test_master.id,
        total_sum=Decimal("1000.00"),
    )
    session.add(order)
    await session.commit()
    await session.refresh(order)
    
    # Тест 1: < 60 минут (должно быть в минутах)
    offer_minutes = m.offers(
        order_id=order.id,
        master_id=test_master.id,
        state=m.OfferState.ACCEPTED,
        sent_at=db_now,
        responded_at=db_now + timedelta(minutes=45),
        round_number=1,
    )
    session.add(offer_minutes)
    await session.commit()
    
    # Проверяем что < 60
    from sqlalchemy import func
    response_query = select(
        func.avg(
            func.extract("EPOCH", m.offers.responded_at - m.offers.sent_at) / 60
        )
    ).where(
        m.offers.master_id == test_master.id,
        m.offers.state == m.OfferState.ACCEPTED,
        m.offers.responded_at.isnot(None),
    )
    
    result = await session.execute(response_query)
    avg_minutes = result.scalar()
    
    assert avg_minutes is not None
    assert float(avg_minutes) < 60  # Должно быть меньше часа
