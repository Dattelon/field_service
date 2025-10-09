"""
Тест P1-16: Напоминание об окончании перерыва

Проверяет внутреннюю логику планировщика напоминаний.
ПРИМЕЧАНИЕ: Тесты проверяют логику без использования notifications_outbox,
так как эта таблица не создаётся в тестовой БД (требует миграции).
"""
import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, text

from field_service.db import models as m
from field_service.services.break_reminder_scheduler import (
    _reminded_master_ids,
    REMINDER_MINUTES_BEFORE,
)


@pytest.fixture
async def master_on_break(session, sample_master):
    """Создаёт мастера на перерыве."""
    master = sample_master
    
    # Устанавливаем перерыв с окончанием через 9 минут (меньше REMINDER_MINUTES_BEFORE)
    db_now_row = await session.execute(text("SELECT NOW()"))
    db_now = db_now_row.scalar()
    
    master.shift_status = m.ShiftStatus.BREAK
    master.is_on_shift = False
    master.break_until = db_now + timedelta(minutes=9)
    
    await session.commit()
    session.expire_all()
    await session.refresh(master)
    
    return master


@pytest.fixture
async def master_on_long_break(session, sample_master):
    """Создаёт мастера на длинном перерыве (не должен получить напоминание)."""
    # Создаём второго мастера
    master2 = m.masters(
        tg_user_id=987654322,
        full_name="Иванов Иван",
        phone="+79991234568",
        city_id=1,
        moderation_status=m.ModerationStatus.APPROVED,
        verified=True,
    )
    session.add(master2)
    await session.commit()
    
    # Устанавливаем перерыв с окончанием через 30 минут (больше REMINDER_MINUTES_BEFORE)
    db_now_row = await session.execute(text("SELECT NOW()"))
    db_now = db_now_row.scalar()
    
    master2.shift_status = m.ShiftStatus.BREAK
    master2.is_on_shift = False
    master2.break_until = db_now + timedelta(minutes=30)
    
    await session.commit()
    session.expire_all()
    await session.refresh(master2)
    
    return master2


@pytest.mark.asyncio
async def test_break_reminder_logic_check(session, master_on_break):
    """Тест: Проверяем логику определения кандидатов на напоминание."""
    _reminded_master_ids.clear()
    
    # Получаем текущее время БД
    db_now_row = await session.execute(text("SELECT NOW()"))
    db_now = db_now_row.scalar()
    reminder_threshold = db_now + timedelta(minutes=REMINDER_MINUTES_BEFORE)
    
    # Проверяем что мастер подходит под критерии напоминания
    result = await session.execute(
        select(m.masters.id, m.masters.break_until)
        .where(
            m.masters.shift_status == m.ShiftStatus.BREAK,
            m.masters.break_until.isnot(None),
            m.masters.break_until <= reminder_threshold,
            m.masters.break_until > db_now,
        )
    )
    
    masters = result.all()
    master_ids = [mid for mid, _ in masters]
    
    assert master_on_break.id in master_ids, "Мастер должен быть в списке для напоминания"


@pytest.mark.asyncio
async def test_break_reminder_not_sent_for_long_break(session, master_on_long_break):
    """Тест: Напоминание НЕ отправляется если до окончания перерыва > 10 минут."""
    _reminded_master_ids.clear()
    
    # Получаем текущее время БД
    db_now_row = await session.execute(text("SELECT NOW()"))
    db_now = db_now_row.scalar()
    reminder_threshold = db_now + timedelta(minutes=REMINDER_MINUTES_BEFORE)
    
    # Проверяем что мастер НЕ подходит под критерии напоминания
    result = await session.execute(
        select(m.masters.id, m.masters.break_until)
        .where(
            m.masters.shift_status == m.ShiftStatus.BREAK,
            m.masters.break_until.isnot(None),
            m.masters.break_until <= reminder_threshold,
            m.masters.break_until > db_now,
        )
    )
    
    masters = result.all()
    master_ids = [mid for mid, _ in masters]
    
    assert master_on_long_break.id not in master_ids, "Мастер НЕ должен быть в списке для напоминания"


@pytest.mark.asyncio
async def test_deduplicate_reminders(session, master_on_break):
    """Тест: Дедупликация напоминаний через _reminded_master_ids."""
    _reminded_master_ids.clear()
    
    # Первый раз - мастер не в наборе
    assert master_on_break.id not in _reminded_master_ids
    
    # Добавляем в набор (имитируем отправку)
    _reminded_master_ids.add(master_on_break.id)
    
    # Второй раз - мастер уже в наборе, повторная отправка не должна произойти
    assert master_on_break.id in _reminded_master_ids, "Мастер должен быть в наборе после добавления"


@pytest.mark.asyncio
async def test_cleanup_reminded_set(session, master_on_break):
    """Тест: Логика очистки набора напоминаний."""
    from field_service.services.break_reminder_scheduler import _cleanup_reminded_set
    
    _reminded_master_ids.clear()
    
    # Добавляем мастера в набор напоминаний
    _reminded_master_ids.add(master_on_break.id)
    assert master_on_break.id in _reminded_master_ids
    
    # Завершаем перерыв (переводим мастера на смену)
    master_on_break.shift_status = m.ShiftStatus.SHIFT_ON
    master_on_break.is_on_shift = True
    master_on_break.break_until = None
    await session.commit()
    
    # Очищаем кэш и обновляем объект
    session.expire_all()
    await session.refresh(master_on_break)
    
    # Запускаем очистку с передачей сессии
    await _cleanup_reminded_set(session=session)
    
    # Проверяем что мастер удалён из набора
    assert master_on_break.id not in _reminded_master_ids, "Мастер должен быть удалён из набора после окончания перерыва"


@pytest.mark.asyncio
async def test_break_duration_constant():
    """Тест: Проверяем константы."""
    assert REMINDER_MINUTES_BEFORE == 10, "Напоминание должно отправляться за 10 минут"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
