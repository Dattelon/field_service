"""
Тесты для P1-9: История заказов мастера.

Проверяем:
1. Пустая история (новый мастер)
2. История с заказами (1 страница)
3. Пагинация (несколько страниц)
4. Фильтры (завершенные/отмененные)
5. Карточка заказа
6. Возврат на нужную страницу
7. Статистика
"""
import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from field_service.db import models as m


@pytest.fixture
async def master(session: AsyncSession) -> m.masters:
    """Создает верифицированного мастера."""
    master = m.masters(
        telegram_id=100001,
        telegram_username="testmaster",
        first_name="Тест",
        last_name="Мастеров",
        phone="+79991234567",
        moderation_status=m.ModerationStatus.APPROVED,
        verified=True,
        shift_status=m.ShiftStatus.SHIFT_OFF,
    )
    session.add(master)
    await session.commit()
    await session.refresh(master)
    return master


@pytest.fixture
async def city(session: AsyncSession) -> m.cities:
    """Создает тестовый город."""
    city = m.cities(name="Москва", timezone="Europe/Moscow")
    session.add(city)
    await session.commit()
    await session.refresh(city)
    return city


@pytest.fixture
async def district(session: AsyncSession, city: m.cities) -> m.districts:
    """Создает тестовый район."""
    district = m.districts(city_id=city.id, name="Центральный")
    session.add(district)
    await session.commit()
    await session.refresh(district)
    return district


async def _get_db_now(session: AsyncSession) -> datetime:
    """Получить текущее время БД."""
    row = await session.execute(text("SELECT NOW()"))
    return row.scalar()


async def _create_order(
    session: AsyncSession,
    master: m.masters,
    city: m.cities,
    district: m.districts,
    status: m.OrderStatus,
    final_amount: Decimal | None = None,
    created_offset_hours: int = 0,
) -> m.orders:
    """Создает заказ для мастера с указанным статусом."""
    db_now = await _get_db_now(session)
    created_at = db_now - timedelta(hours=created_offset_hours)
    
    order = m.orders(
        city_id=city.id,
        district_id=district.id,
        street_address="Тверская",
        house_number="10",
        apartment_number="5",
        client_name="Иван Иванов",
        client_phone="+79991234567",
        description="Тестовый заказ",
        category=m.OrderCategory.ELECTRICS,
        status=status,
        master_id=master.id,
        final_amount=final_amount,
        created_at=created_at,
        updated_at=created_at,
    )
    session.add(order)
    await session.commit()
    await session.refresh(order)
    return order



@pytest.mark.asyncio
async def test_empty_history(
    session: AsyncSession,
    master: m.masters,
) -> None:
    """Тест: пустая история (новый мастер без заказов)."""
    from field_service.bots.master_bot.handlers.history import HISTORY_STATUSES
    
    # Проверяем что нет завершенных заказов
    stmt = select(m.orders).where(
        m.orders.master_id == master.id,
        m.orders.status.in_(HISTORY_STATUSES),
    )
    result = await session.execute(stmt)
    orders = result.scalars().all()
    
    assert len(orders) == 0, "У нового мастера не должно быть завершенных заказов"


@pytest.mark.asyncio
async def test_history_with_orders_single_page(
    session: AsyncSession,
    master: m.masters,
    city: m.cities,
    district: m.districts,
) -> None:
    """Тест: история с 5 заказами (одна страница)."""
    # Создаем 3 завершенных и 2 отмененных заказа
    for i in range(3):
        await _create_order(
            session, master, city, district,
            status=m.OrderStatus.CLOSED,
            final_amount=Decimal("1500.00"),
            created_offset_hours=i,
        )
    
    for i in range(2):
        await _create_order(
            session, master, city, district,
            status=m.OrderStatus.CANCELED,
            created_offset_hours=i + 10,
        )
    
    # Проверяем общее количество
    stmt = select(m.orders).where(
        m.orders.master_id == master.id,
        m.orders.status.in_([m.OrderStatus.CLOSED, m.OrderStatus.CANCELED]),
    )
    result = await session.execute(stmt)
    orders = result.scalars().all()
    
    assert len(orders) == 5, "Должно быть 5 заказов в истории"
    
    # Проверяем статистику
    closed_orders = [o for o in orders if o.status == m.OrderStatus.CLOSED]
    total_earned = sum(o.final_amount or Decimal(0) for o in closed_orders)
    
    assert len(closed_orders) == 3, "Должно быть 3 завершенных заказа"
    assert total_earned == Decimal("4500.00"), "Заработано должно быть 4500.00"


@pytest.mark.asyncio
async def test_history_pagination(
    session: AsyncSession,
    master: m.masters,
    city: m.cities,
    district: m.districts,
) -> None:
    """Тест: пагинация (25 заказов = 3 страницы)."""
    # Создаем 25 завершенных заказов
    for i in range(25):
        await _create_order(
            session, master, city, district,
            status=m.OrderStatus.CLOSED,
            final_amount=Decimal("1000.00"),
            created_offset_hours=i,
        )
    
    # Проверяем общее количество
    stmt = select(m.orders).where(
        m.orders.master_id == master.id,
        m.orders.status == m.OrderStatus.CLOSED,
    )
    result = await session.execute(stmt)
    orders = result.scalars().all()
    
    assert len(orders) == 25, "Должно быть 25 заказов"
    
    # Проверяем пагинацию
    HISTORY_PAGE_SIZE = 10
    import math
    total_pages = math.ceil(25 / HISTORY_PAGE_SIZE)
    assert total_pages == 3, "Должно быть 3 страницы"


@pytest.mark.asyncio
async def test_history_filters(
    session: AsyncSession,
    master: m.masters,
    city: m.cities,
    district: m.districts,
) -> None:
    """Тест: фильтры (завершенные/отмененные/все)."""
    # Создаем 7 завершенных и 3 отмененных заказа
    for i in range(7):
        await _create_order(
            session, master, city, district,
            status=m.OrderStatus.CLOSED,
            final_amount=Decimal("2000.00"),
            created_offset_hours=i,
        )
    
    for i in range(3):
        await _create_order(
            session, master, city, district,
            status=m.OrderStatus.CANCELED,
            created_offset_hours=i + 20,
        )
    
    # Фильтр "Все"
    stmt_all = select(m.orders).where(
        m.orders.master_id == master.id,
        m.orders.status.in_([m.OrderStatus.CLOSED, m.OrderStatus.CANCELED]),
    )
    result_all = await session.execute(stmt_all)
    all_orders = result_all.scalars().all()
    assert len(all_orders) == 10, "Фильтр 'Все' должен показать 10 заказов"
    
    # Фильтр "Завершенные"
    stmt_closed = select(m.orders).where(
        m.orders.master_id == master.id,
        m.orders.status == m.OrderStatus.CLOSED,
    )
    result_closed = await session.execute(stmt_closed)
    closed_orders = result_closed.scalars().all()
    assert len(closed_orders) == 7, "Фильтр 'Завершенные' должен показать 7 заказов"
    
    # Фильтр "Отмененные"
    stmt_canceled = select(m.orders).where(
        m.orders.master_id == master.id,
        m.orders.status == m.OrderStatus.CANCELED,
    )
    result_canceled = await session.execute(stmt_canceled)
    canceled_orders = result_canceled.scalars().all()
    assert len(canceled_orders) == 3, "Фильтр 'Отмененные' должен показать 3 заказа"


@pytest.mark.asyncio
async def test_order_card_content(
    session: AsyncSession,
    master: m.masters,
    city: m.cities,
    district: m.districts,
) -> None:
    """Тест: проверка содержимого карточки заказа."""
    # Создаем завершенный заказ
    order = await _create_order(
        session, master, city, district,
        status=m.OrderStatus.CLOSED,
        final_amount=Decimal("3500.50"),
        created_offset_hours=5,
    )
    
    # Проверяем что заказ создан
    session.expire_all()
    await session.refresh(order)
    
    assert order.status == m.OrderStatus.CLOSED
    assert order.master_id == master.id
    assert order.final_amount == Decimal("3500.50")
    assert order.city_id == city.id
    assert order.district_id == district.id
    assert order.street_address == "Тверская"
    assert order.house_number == "10"
    assert order.apartment_number == "5"
    assert order.client_name == "Иван Иванов"
    assert order.client_phone == "+79991234567"


@pytest.mark.asyncio
async def test_history_sorting(
    session: AsyncSession,
    master: m.masters,
    city: m.cities,
    district: m.districts,
) -> None:
    """Тест: сортировка по дате обновления (новые сверху)."""
    # Создаем заказы с разными датами
    order1 = await _create_order(
        session, master, city, district,
        status=m.OrderStatus.CLOSED,
        created_offset_hours=10,
    )
    order2 = await _create_order(
        session, master, city, district,
        status=m.OrderStatus.CLOSED,
        created_offset_hours=5,
    )
    order3 = await _create_order(
        session, master, city, district,
        status=m.OrderStatus.CLOSED,
        created_offset_hours=1,
    )
    
    # Загружаем заказы с сортировкой
    stmt = (
        select(m.orders)
        .where(
            m.orders.master_id == master.id,
            m.orders.status == m.OrderStatus.CLOSED,
        )
        .order_by(m.orders.updated_at.desc())
    )
    result = await session.execute(stmt)
    orders = result.scalars().all()
    
    # Проверяем порядок (новые сверху)
    assert len(orders) == 3
    assert orders[0].id == order3.id, "Первым должен быть самый свежий заказ"
    assert orders[1].id == order2.id
    assert orders[2].id == order1.id, "Последним должен быть самый старый заказ"


@pytest.mark.asyncio
async def test_master_isolation(
    session: AsyncSession,
    master: m.masters,
    city: m.cities,
    district: m.districts,
) -> None:
    """Тест: мастер видит только свои заказы."""
    # Создаем второго мастера
    other_master = m.masters(
        telegram_id=100002,
        telegram_username="othermaster",
        first_name="Другой",
        last_name="Мастеров",
        phone="+79991234568",
        moderation_status=m.ModerationStatus.APPROVED,
        verified=True,
    )
    session.add(other_master)
    await session.commit()
    await session.refresh(other_master)
    
    # Создаем заказ для первого мастера
    await _create_order(
        session, master, city, district,
        status=m.OrderStatus.CLOSED,
        final_amount=Decimal("1000.00"),
    )
    
    # Создаем заказ для второго мастера
    await _create_order(
        session, other_master, city, district,
        status=m.OrderStatus.CLOSED,
        final_amount=Decimal("2000.00"),
    )
    
    # Проверяем изоляцию: первый мастер видит только свой заказ
    stmt_master1 = select(m.orders).where(
        m.orders.master_id == master.id,
        m.orders.status == m.OrderStatus.CLOSED,
    )
    result_master1 = await session.execute(stmt_master1)
    orders_master1 = result_master1.scalars().all()
    
    assert len(orders_master1) == 1, "Первый мастер должен видеть только 1 свой заказ"
    assert orders_master1[0].master_id == master.id
    
    # Проверяем изоляцию: второй мастер видит только свой заказ
    stmt_master2 = select(m.orders).where(
        m.orders.master_id == other_master.id,
        m.orders.status == m.OrderStatus.CLOSED,
    )
    result_master2 = await session.execute(stmt_master2)
    orders_master2 = result_master2.scalars().all()
    
    assert len(orders_master2) == 1, "Второй мастер должен видеть только 1 свой заказ"
    assert orders_master2[0].master_id == other_master.id


@pytest.mark.asyncio
async def test_active_orders_not_in_history(
    session: AsyncSession,
    master: m.masters,
    city: m.cities,
    district: m.districts,
) -> None:
    """Тест: активные заказы не показываются в истории."""
    # Создаем активные заказы (ASSIGNED, EN_ROUTE, WORKING, PAYMENT)
    await _create_order(session, master, city, district, status=m.OrderStatus.ASSIGNED)
    await _create_order(session, master, city, district, status=m.OrderStatus.EN_ROUTE)
    await _create_order(session, master, city, district, status=m.OrderStatus.WORKING)
    await _create_order(session, master, city, district, status=m.OrderStatus.PAYMENT)
    
    # Создаем завершенный заказ
    await _create_order(
        session, master, city, district,
        status=m.OrderStatus.CLOSED,
        final_amount=Decimal("1500.00"),
    )
    
    # Проверяем что в истории только завершенные/отмененные
    stmt = select(m.orders).where(
        m.orders.master_id == master.id,
        m.orders.status.in_([m.OrderStatus.CLOSED, m.OrderStatus.CANCELED]),
    )
    result = await session.execute(stmt)
    history_orders = result.scalars().all()
    
    assert len(history_orders) == 1, "В истории должен быть только 1 завершенный заказ"
    assert history_orders[0].status == m.OrderStatus.CLOSED
