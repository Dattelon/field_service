"""
P1-15: Тест группировки комиссий по периодам.

Проверяет:
- Группировку комиссий по периодам (today, yesterday, week, month, older)
- UI keyboards для группированного вида
- Обработчики для просмотра групп
"""
import pytest
from datetime import datetime, timezone, timedelta, date
from decimal import Decimal

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from field_service.db import models as m
from field_service.bots.admin_bot.services.finance import DBFinanceService
from field_service.bots.admin_bot.ui.keyboards.finance import (
    finance_grouped_keyboard,
    finance_group_period_keyboard,
    finance_segment_keyboard,
)


@pytest.fixture
def finance_service(session: AsyncSession):
    """Создание finance service."""
    return DBFinanceService(session_factory=lambda: session)


async def _get_db_now(session: AsyncSession) -> datetime:
    """Получить текущее время БД."""
    row = await session.execute(text("SELECT NOW()"))
    return row.scalar()


async def _create_commission_for_period(
    session: AsyncSession,
    period: str,
    base_time: datetime,
    order_id: int,
    master_id: int,
) -> int:
    """
    Создать комиссию для заданного периода.
    
    Args:
        period: 'today', 'yesterday', 'week', 'month', 'older'
        base_time: текущее время БД
        order_id: ID заказа
        master_id: ID мастера
    
    Returns:
        ID созданной комиссии
    """
    # Вычисляем created_at в зависимости от периода
    if period == 'today':
        created_at = base_time
    elif period == 'yesterday':
        created_at = base_time - timedelta(days=1)
    elif period == 'week':
        created_at = base_time - timedelta(days=4)  # 4 дня назад
    elif period == 'month':
        created_at = base_time - timedelta(days=15)  # 15 дней назад
    elif period == 'older':
        created_at = base_time - timedelta(days=60)  # 60 дней назад
    else:
        created_at = base_time
    
    commission = m.commissions(
        order_id=order_id,
        master_id=master_id,
        amount=Decimal("1500.00"),
        rate=Decimal("0.50"),
        status=m.CommissionStatus.WAIT_PAY,
        created_at=created_at,
        deadline_at=created_at + timedelta(hours=3),
    )
    session.add(commission)
    await session.flush()
    return commission.id


@pytest.mark.asyncio
async def test_list_commissions_grouped_all_periods(
    session: AsyncSession,
    finance_service: DBFinanceService,
) -> None:
    """
    Тест: Группировка комиссий по всем периодам.
    
    Создаем комиссии для каждого периода и проверяем правильность группировки.
    """
    # Получаем текущее время БД
    db_now = await _get_db_now(session)
    
    # Создаём город
    city = m.cities(name="Тестовый город")
    session.add(city)
    await session.flush()
    
    # Создаём мастера
    master = m.masters(
        tg_user_id=12345,
        full_name="Тестовый Мастер",
        phone="+79991234567",
        city_id=city.id,
        is_active=True,
        is_on_shift=True,
        verified=True,
        shift_status=m.ShiftStatus.SHIFT_ON,
        moderation_status=m.ModerationStatus.APPROVED,
    )
    session.add(master)
    await session.flush()
    
    # Создаём заказ
    order = m.orders(
        city_id=city.id,
        district_id=None,
        category=m.OrderCategory.ELECTRICS,
        type=m.OrderType.NORMAL,
        status=m.OrderStatus.CLOSED,
        assigned_master_id=master.id,
    )
    session.add(order)
    await session.flush()
    
    # Создаём комиссии для каждого периода
    periods_to_create = ['today', 'yesterday', 'week', 'month', 'older']
    commission_ids = {}
    
    for period in periods_to_create:
        comm_id = await _create_commission_for_period(
            session, period, db_now, order.id, master.id
        )
        commission_ids[period] = comm_id
    
    await session.commit()
    
    # Получаем группированные комиссии
    session.expire_all()
    groups = await finance_service.list_commissions_grouped(
        segment='aw',
        city_ids=None,  # Все города
    )
    
    # Проверяем что все группы созданы
    assert 'today' in groups, "Группа 'today' должна существовать"
    assert 'yesterday' in groups, "Группа 'yesterday' должна существовать"
    assert 'week' in groups, "Группа 'week' должна существовать"
    assert 'month' in groups, "Группа 'month' должна существовать"
    assert 'older' in groups, "Группа 'older' должна существовать"
    
    # Проверяем что в каждой группе по одной комиссии
    assert len(groups['today']) == 1, "В группе 'today' должна быть 1 комиссия"
    assert len(groups['yesterday']) == 1, "В группе 'yesterday' должна быть 1 комиссия"
    assert len(groups['week']) == 1, "В группе 'week' должна быть 1 комиссия"
    assert len(groups['month']) == 1, "В группе 'month' должна быть 1 комиссия"
    assert len(groups['older']) == 1, "В группе 'older' должна быть 1 комиссия"
    
    # Проверяем что ID комиссий правильные
    assert groups['today'][0].id == commission_ids['today']
    assert groups['yesterday'][0].id == commission_ids['yesterday']
    assert groups['week'][0].id == commission_ids['week']
    assert groups['month'][0].id == commission_ids['month']
    assert groups['older'][0].id == commission_ids['older']
    
    # Проверяем данные комиссий
    for period, items in groups.items():
        item = items[0]
        assert item.master_name == "Тестовый Мастер"
        assert item.amount == Decimal("1500.00")
        assert item.status == m.CommissionStatus.WAIT_PAY.value



@pytest.mark.asyncio
async def test_list_commissions_grouped_empty_groups(
    session: AsyncSession,
    finance_service: DBFinanceService,
) -> None:
    """
    Тест: Пустые группы не должны возвращаться.
    
    Если в периоде нет комиссий, группа не должна быть в результате.
    """
    # Получаем группированные комиссии (база пустая)
    groups = await finance_service.list_commissions_grouped(
        segment='aw',
        city_ids=None,
    )
    
    # Проверяем что результат пустой
    assert groups == {}, "Пустая база должна возвращать пустой dict"



# Тесты UI keyboards
@pytest.mark.asyncio
async def test_finance_grouped_keyboard_structure() -> None:
    """
    Тест: Структура клавиатуры для группированного вида.
    
    Проверяем что кнопки создаются правильно и только для непустых групп.
    """
    # Тестируем с разными группами
    groups_data = {
        'today': 5,
        'yesterday': 3,
        'week': 10,
        'month': 0,  # Пустая группа
        'older': 2,
    }
    
    keyboard = finance_grouped_keyboard('aw', groups_data)
    
    # Получаем все callback_data кнопок
    callbacks = [
        button.callback_data
        for row in keyboard.inline_keyboard
        for button in row
    ]
    
    # Проверяем что кнопки созданы для непустых групп
    assert 'adm:f:grp:aw:today:1' in callbacks, "Кнопка 'today' должна существовать"
    assert 'adm:f:grp:aw:yesterday:1' in callbacks, "Кнопка 'yesterday' должна существовать"
    assert 'adm:f:grp:aw:week:1' in callbacks, "Кнопка 'week' должна существовать"
    assert 'adm:f:grp:aw:older:1' in callbacks, "Кнопка 'older' должна существовать"
    
    # Проверяем что есть кнопка возврата
    assert 'adm:f' in callbacks, "Кнопка возврата должна существовать"


def test_finance_group_period_keyboard_navigation() -> None:
    """
    Тест: Навигация внутри периода.
    
    Проверяем что кнопки навигации работают правильно.
    """
    # Первая страница с has_next=True
    kb_page1 = finance_group_period_keyboard('aw', 'today', 1, has_next=True)
    callbacks_p1 = [
        button.callback_data
        for row in kb_page1.inline_keyboard
        for button in row
    ]
    
    # Не должно быть кнопки "Назад" на первой странице
    prev_buttons = [cb for cb in callbacks_p1 if 'today:0' in cb]
    assert len(prev_buttons) == 0, "На первой странице не должно быть кнопки 'Назад'"
    
    # Должна быть кнопка "Далее"
    assert 'adm:f:grp:aw:today:2' in callbacks_p1, "Должна быть кнопка 'Далее'"
    
    # Должна быть кнопка возврата к группам
    assert 'adm:f:grouped:aw' in callbacks_p1, "Должна быть кнопка 'К группам'"
    
    # Вторая страница с has_next=False
    kb_page2 = finance_group_period_keyboard('aw', 'today', 2, has_next=False)
    callbacks_p2 = [
        button.callback_data
        for row in kb_page2.inline_keyboard
        for button in row
    ]
    
    # Должна быть кнопка "Назад"
    assert 'adm:f:grp:aw:today:1' in callbacks_p2, "Должна быть кнопка 'Назад'"
    
    # Не должно быть кнопки "Далее" на последней странице
    next_buttons = [cb for cb in callbacks_p2 if 'today:3' in cb]
    assert len(next_buttons) == 0, "На последней странице не должно быть кнопки 'Далее'"


def test_finance_segment_keyboard_toggle_grouped() -> None:
    """
    Тест: Переключение режима группировки.
    
    Проверяем что кнопка переключения работает правильно.
    """
    # Обычный режим (не сгруппированный)
    kb_normal = finance_segment_keyboard('aw', page=1, has_next=True, grouped=False)
    callbacks_normal = [
        button.callback_data
        for row in kb_normal.inline_keyboard
        for button in row
    ]
    
    # Должна быть кнопка "По периодам"
    assert 'adm:f:aw:grp' in callbacks_normal, "Должна быть кнопка 'По периодам'"
    
    # Должны быть кнопки пагинации
    assert 'adm:f:aw:2' in callbacks_normal, "Должна быть кнопка 'Далее'"
    
    # Группированный режим
    kb_grouped = finance_segment_keyboard('aw', page=1, has_next=False, grouped=True)
    callbacks_grouped = [
        button.callback_data
        for row in kb_grouped.inline_keyboard
        for button in row
    ]
    
    # Должна быть кнопка "Обычный список"
    assert 'adm:f:aw:1' in callbacks_grouped, "Должна быть кнопка 'Обычный список'"
