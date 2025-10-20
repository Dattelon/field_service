# -*- coding: utf-8 -*-
"""Тесты для проверки поддержки опциональной сессии в watchdog-функциях."""
from __future__ import annotations

import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy import select

from field_service.db import models as m
from field_service.services.watchdogs import expire_old_breaks
from field_service.services.unassigned_monitor import scan_and_notify
from tests.factories import ensure_city, ensure_master, create_order


@pytest.mark.asyncio
async def test_expire_old_breaks_with_test_session(async_session):
    """Тест expire_old_breaks с внешней тестовой сессией.
    
    Проверяет что:
    1. Функция принимает тестовую сессию
    2. Изменения видны в той же транзакции
    3. Данные не коммитятся в основную БД
    """
    # Arrange: создаём мастера на перерыве с истёкшим break_until
    city = await ensure_city(async_session)
    master = await ensure_master(async_session, city=city, phone="+79991234567")
    
    # Устанавливаем перерыв который уже истёк
    master.shift_status = m.ShiftStatus.BREAK
    master.is_on_shift = False
    master.break_until = datetime.now(timezone.utc) - timedelta(minutes=5)
    await async_session.flush()
    
    # Проверяем начальное состояние
    assert master.shift_status == m.ShiftStatus.BREAK
    assert master.break_until is not None
    
    # Act: вызываем функцию с тестовой сессией
    count = await expire_old_breaks(session=async_session)
    
    # Assert: проверяем результат
    assert count == 1, "Должен быть завершён 1 перерыв"
    
    # Проверяем что изменения видны в текущей транзакции
    await async_session.refresh(master)
    assert master.shift_status == m.ShiftStatus.SHIFT_OFF
    assert master.is_on_shift is False
    assert master.break_until is None
    
    # Проверяем что запись существует в тестовой транзакции
    result = await async_session.execute(
        select(m.masters).where(m.masters.id == master.id)
    )
    updated_master = result.scalar_one()
    assert updated_master.shift_status == m.ShiftStatus.SHIFT_OFF


@pytest.mark.asyncio
async def test_expire_old_breaks_multiple_masters(async_session):
    """Тест expire_old_breaks с несколькими мастерами на перерыве."""
    # Arrange: создаём 3 мастеров с разными состояниями перерыва
    city = await ensure_city(async_session)
    
    # Мастер 1: перерыв истёк
    master1 = await ensure_master(async_session, city=city, phone="+79991111111")
    master1.shift_status = m.ShiftStatus.BREAK
    master1.break_until = datetime.now(timezone.utc) - timedelta(minutes=10)
    
    # Мастер 2: перерыв ещё не истёк
    master2 = await ensure_master(async_session, city=city, phone="+79992222222")
    master2.shift_status = m.ShiftStatus.BREAK
    master2.break_until = datetime.now(timezone.utc) + timedelta(minutes=10)
    
    # Мастер 3: перерыв истёк
    master3 = await ensure_master(async_session, city=city, phone="+79993333333")
    master3.shift_status = m.ShiftStatus.BREAK
    master3.break_until = datetime.now(timezone.utc) - timedelta(minutes=5)
    
    await async_session.flush()
    
    # Act
    count = await expire_old_breaks(session=async_session)
    
    # Assert
    assert count == 2, "Должны быть завершены 2 перерыва"
    
    # Проверяем состояния
    await async_session.refresh(master1)
    await async_session.refresh(master2)
    await async_session.refresh(master3)
    
    assert master1.shift_status == m.ShiftStatus.SHIFT_OFF
    assert master2.shift_status == m.ShiftStatus.BREAK  # не изменился
    assert master3.shift_status == m.ShiftStatus.SHIFT_OFF


@pytest.mark.asyncio
async def test_scan_and_notify_with_test_session(async_session):
    """Тест scan_and_notify с внешней тестовой сессией.
    
    Проверяет что:
    1. Функция принимает тестовую сессию
    2. Корректно подсчитывает неназначенные заказы
    3. Учитывает временной порог 10 минут
    """
    # Arrange: создаём заказы с разным временем создания
    city = await ensure_city(async_session)
    
    # Старый заказ (> 10 минут)
    old_order = await create_order(
        async_session,
        city=city,
        status="SEARCHING"
    )
    old_order.created_at = datetime.now(timezone.utc) - timedelta(minutes=15)
    
    # Недавний заказ (< 10 минут)
    recent_order = await create_order(
        async_session,
        city=city,
        status="SEARCHING"
    )
    recent_order.created_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    
    # Заказ не в статусе SEARCHING
    assigned_order = await create_order(
        async_session,
        city=city,
        status="ASSIGNED"
    )
    assigned_order.created_at = datetime.now(timezone.utc) - timedelta(minutes=20)
    
    await async_session.flush()
    
    # Act
    count = await scan_and_notify(session=async_session)
    
    # Assert
    assert count == 1, "Должен найтись только 1 старый неназначенный заказ"


@pytest.mark.asyncio
async def test_scan_and_notify_no_old_orders(async_session):
    """Тест scan_and_notify когда нет старых заказов."""
    # Arrange: создаём только недавние заказы
    city = await ensure_city(async_session)
    
    for i in range(3):
        order = await create_order(
            async_session,
            city=city,
            status="SEARCHING"
        )
        order.created_at = datetime.now(timezone.utc) - timedelta(minutes=2)
    
    await async_session.flush()
    
    # Act
    count = await scan_and_notify(session=async_session)
    
    # Assert
    assert count == 0, "Не должно быть старых неназначенных заказов"


@pytest.mark.asyncio
async def test_watchdog_session_isolation(async_session):
    """Тест изоляции транзакций при использовании тестовой сессии.
    
    Проверяет что изменения внутри watchdog функций
    не видны за пределами тестовой транзакции.
    """
    # Arrange
    city = await ensure_city(async_session)
    master = await ensure_master(async_session, city=city, phone="+79994444444")
    master.shift_status = m.ShiftStatus.BREAK
    master.break_until = datetime.now(timezone.utc) - timedelta(minutes=5)
    await async_session.flush()
    
    initial_id = master.id
    
    # Act: вызываем функцию с тестовой сессией
    count = await expire_old_breaks(session=async_session)
    
    # Assert: изменения видны в текущей транзакции
    await async_session.refresh(master)
    assert master.shift_status == m.ShiftStatus.SHIFT_OFF
    
    # Проверяем что объект всё ещё доступен в тестовой сессии
    result = await async_session.execute(
        select(m.masters).where(m.masters.id == initial_id)
    )
    found_master = result.scalar_one()
    assert found_master.id == initial_id
    assert found_master.shift_status == m.ShiftStatus.SHIFT_OFF


@pytest.mark.asyncio
async def test_multiple_watchdog_calls_same_session(async_session):
    """Тест множественных вызовов watchdog функций в одной сессии."""
    # Arrange
    city = await ensure_city(async_session)
    
    # Создаём мастеров на перерыве
    for i in range(3):
        master = await ensure_master(
            async_session, 
            city=city, 
            phone=f"+7999555{i:04d}"
        )
        master.shift_status = m.ShiftStatus.BREAK
        master.break_until = datetime.now(timezone.utc) - timedelta(minutes=5)
    
    # Создаём старые заказы
    for i in range(2):
        order = await create_order(async_session, city=city, status="SEARCHING")
        order.created_at = datetime.now(timezone.utc) - timedelta(minutes=15)
    
    await async_session.flush()
    
    # Act: первый вызов
    breaks_count = await expire_old_breaks(session=async_session)
    assert breaks_count == 3
    
    # Act: второй вызов на той же сессии
    orders_count = await scan_and_notify(session=async_session)
    assert orders_count == 2
    
    # Act: повторный вызов expire_old_breaks не должен найти новых перерывов
    breaks_count_2 = await expire_old_breaks(session=async_session)
    assert breaks_count_2 == 0, "Все перерывы уже завершены"
