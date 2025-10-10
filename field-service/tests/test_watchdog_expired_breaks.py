"""
Тесты для watchdog_expired_breaks и гибких перерывов
"""
import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, text

from field_service.db import models as m
from field_service.services.watchdogs import watchdog_expired_breaks

UTC = timezone.utc


async def _get_db_now(session):
    """Получить текущее время БД для синхронизации."""
    row = await session.execute(text("SELECT NOW()"))
    return row.scalar()


@pytest.mark.asyncio
async def test_watchdog_expired_breaks_basic(session, clean_db):
    """
    Тест базовой функциональности watchdog_expired_breaks:
    - Мастер на перерыве с истёкшим временем должен быть снят со смены
    - shift_status = SHIFT_OFF
    - is_on_shift = False
    - break_until = None
    """
    db_now = await _get_db_now(session)
    
    # Создаём город
    city = m.cities(name="Москва", timezone="Europe/Moscow")
    session.add(city)
    await session.commit()
    
    # Создаём мастера на перерыве с истёкшим временем
    master = m.masters(
        tg_user_id=12345,
        full_name="Тестовый Мастер",
        phone="+79001234567",
        city_id=city.id,
        verified=True,
        moderation_status=m.ModerationStatus.APPROVED,
        shift_status=m.ShiftStatus.BREAK,
        is_on_shift=False,
        break_until=db_now - timedelta(minutes=5),  # Перерыв закончился 5 минут назад
    )
    session.add(master)
    await session.commit()
    
    master_id = master.id
    
    # Запускаем watchdog (1 итерация)
    await watchdog_expired_breaks(interval_seconds=60, iterations=1)
    
    # Проверяем что мастер снят со смены
    session.expire_all()
    result = await session.execute(
        select(m.masters).where(m.masters.id == master_id)
    )
    updated_master = result.scalar_one()
    
    assert updated_master.shift_status == m.ShiftStatus.SHIFT_OFF
    assert updated_master.is_on_shift is False
    assert updated_master.break_until is None


@pytest.mark.asyncio
async def test_watchdog_expired_breaks_not_expired(session, clean_db):
    """
    Тест что watchdog НЕ снимает мастеров с активным перерывом.
    """
    db_now = await _get_db_now(session)
    
    # Создаём город
    city = m.cities(name="Москва", timezone="Europe/Moscow")
    session.add(city)
    await session.commit()
    
    # Создаём мастера на перерыве с НЕ истёкшим временем
    master = m.masters(
        tg_user_id=12345,
        full_name="Тестовый Мастер",
        phone="+79001234567",
        city_id=city.id,
        verified=True,
        moderation_status=m.ModerationStatus.APPROVED,
        shift_status=m.ShiftStatus.BREAK,
        is_on_shift=False,
        break_until=db_now + timedelta(minutes=30),  # Перерыв ещё не закончился
    )
    session.add(master)
    await session.commit()
    
    master_id = master.id
    
    # Запускаем watchdog (1 итерация)
    await watchdog_expired_breaks(interval_seconds=60, iterations=1)
    
    # Проверяем что мастер остался на перерыве
    session.expire_all()
    result = await session.execute(
        select(m.masters).where(m.masters.id == master_id)
    )
    updated_master = result.scalar_one()
    
    assert updated_master.shift_status == m.ShiftStatus.BREAK
    assert updated_master.is_on_shift is False
    assert updated_master.break_until is not None


@pytest.mark.asyncio
async def test_watchdog_expired_breaks_multiple_masters(session, clean_db):
    """
    Тест что watchdog обрабатывает нескольких мастеров одновременно.
    """
    db_now = await _get_db_now(session)
    
    # Создаём город
    city = m.cities(name="Москва", timezone="Europe/Moscow")
    session.add(city)
    await session.commit()
    
    # Создаём 3 мастеров:
    # 1. С истёкшим перерывом
    # 2. С активным перерывом
    # 3. Не на перерыве
    master1 = m.masters(
        tg_user_id=11111,
        full_name="Мастер 1",
        phone="+79001111111",
        city_id=city.id,
        verified=True,
        moderation_status=m.ModerationStatus.APPROVED,
        shift_status=m.ShiftStatus.BREAK,
        is_on_shift=False,
        break_until=db_now - timedelta(minutes=10),  # Истёк
    )
    
    master2 = m.masters(
        tg_user_id=22222,
        full_name="Мастер 2",
        phone="+79002222222",
        city_id=city.id,
        verified=True,
        moderation_status=m.ModerationStatus.APPROVED,
        shift_status=m.ShiftStatus.BREAK,
        is_on_shift=False,
        break_until=db_now + timedelta(minutes=20),  # Активный
    )
    
    master3 = m.masters(
        tg_user_id=33333,
        full_name="Мастер 3",
        phone="+79003333333",
        city_id=city.id,
        verified=True,
        moderation_status=m.ModerationStatus.APPROVED,
        shift_status=m.ShiftStatus.SHIFT_ON,
        is_on_shift=True,
        break_until=None,  # Не на перерыве
    )
    
    session.add_all([master1, master2, master3])
    await session.commit()
    
    master1_id = master1.id
    master2_id = master2.id
    master3_id = master3.id
    
    # Запускаем watchdog (1 итерация)
    await watchdog_expired_breaks(interval_seconds=60, iterations=1)
    
    # Проверяем результаты
    session.expire_all()
    
    # Мастер 1 должен быть снят со смены
    result1 = await session.execute(
        select(m.masters).where(m.masters.id == master1_id)
    )
    updated_master1 = result1.scalar_one()
    assert updated_master1.shift_status == m.ShiftStatus.SHIFT_OFF
    assert updated_master1.is_on_shift is False
    assert updated_master1.break_until is None
    
    # Мастер 2 должен остаться на перерыве
    result2 = await session.execute(
        select(m.masters).where(m.masters.id == master2_id)
    )
    updated_master2 = result2.scalar_one()
    assert updated_master2.shift_status == m.ShiftStatus.BREAK
    assert updated_master2.is_on_shift is False
    assert updated_master2.break_until is not None
    
    # Мастер 3 должен остаться на смене
    result3 = await session.execute(
        select(m.masters).where(m.masters.id == master3_id)
    )
    updated_master3 = result3.scalar_one()
    assert updated_master3.shift_status == m.ShiftStatus.SHIFT_ON
    assert updated_master3.is_on_shift is True
    assert updated_master3.break_until is None


@pytest.mark.asyncio
async def test_watchdog_expired_breaks_edge_case_exactly_now(session, clean_db):
    """
    Тест граничного случая: break_until ровно равен NOW().
    Должен быть обработан как истёкший.
    """
    db_now = await _get_db_now(session)
    
    # Создаём город
    city = m.cities(name="Москва", timezone="Europe/Moscow")
    session.add(city)
    await session.commit()
    
    # Создаём мастера с break_until = NOW()
    master = m.masters(
        tg_user_id=12345,
        full_name="Тестовый Мастер",
        phone="+79001234567",
        city_id=city.id,
        verified=True,
        moderation_status=m.ModerationStatus.APPROVED,
        shift_status=m.ShiftStatus.BREAK,
        is_on_shift=False,
        break_until=db_now,  # Ровно сейчас
    )
    session.add(master)
    await session.commit()
    
    master_id = master.id
    
    # Запускаем watchdog (1 итерация)
    await watchdog_expired_breaks(interval_seconds=60, iterations=1)
    
    # Проверяем что мастер снят со смены
    session.expire_all()
    result = await session.execute(
        select(m.masters).where(m.masters.id == master_id)
    )
    updated_master = result.scalar_one()
    
    assert updated_master.shift_status == m.ShiftStatus.SHIFT_OFF
    assert updated_master.is_on_shift is False
    assert updated_master.break_until is None
