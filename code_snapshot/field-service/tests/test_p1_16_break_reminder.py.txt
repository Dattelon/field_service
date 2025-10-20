"""
Тест P1-16: Напоминание об окончании перерыва

Проверяет внутреннюю логику планировщика напоминаний.
ПРИМЕЧАНИЕ: Тесты используют тестовую БД PostgreSQL, включая notifications_outbox,
что позволяет проверять постановку уведомлений в очередь.
"""
import pytest
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from sqlalchemy import func, select, text

from field_service.db import models as m
from field_service.services import break_reminder_scheduler as scheduler


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
    scheduler._reminded_master_breaks.clear()
    
    # Получаем текущее время БД
    db_now_row = await session.execute(text("SELECT NOW()"))
    db_now = db_now_row.scalar()
    reminder_threshold = db_now + timedelta(minutes=scheduler.REMINDER_MINUTES_BEFORE)
    
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
    scheduler._reminded_master_breaks.clear()
    
    # Получаем текущее время БД
    db_now_row = await session.execute(text("SELECT NOW()"))
    db_now = db_now_row.scalar()
    reminder_threshold = db_now + timedelta(minutes=scheduler.REMINDER_MINUTES_BEFORE)
    
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
    """Тест: Дедупликация напоминаний через _reminded_master_breaks."""
    scheduler._reminded_master_breaks.clear()

    # Первый раз - мастер не в наборе
    assert master_on_break.id not in scheduler._reminded_master_breaks

    # Добавляем в набор (имитируем отправку)
    scheduler._reminded_master_breaks[master_on_break.id] = master_on_break.break_until

    # Второй раз - мастер уже в наборе, повторная отправка не должна произойти
    assert master_on_break.id in scheduler._reminded_master_breaks
    assert (
        scheduler._reminded_master_breaks[master_on_break.id] == master_on_break.break_until
    )


@pytest.mark.asyncio
async def test_cleanup_reminded_set(session, master_on_break):
    """Тест: Логика очистки набора напоминаний."""
    scheduler._reminded_master_breaks.clear()

    # Добавляем мастера в набор напоминаний
    scheduler._reminded_master_breaks[master_on_break.id] = master_on_break.break_until
    assert master_on_break.id in scheduler._reminded_master_breaks

    # Завершаем перерыв (переводим мастера на смену)
    master_on_break.shift_status = m.ShiftStatus.SHIFT_ON
    master_on_break.is_on_shift = True
    master_on_break.break_until = None
    await session.commit()

    # Очищаем кэш и обновляем объект
    session.expire_all()
    await session.refresh(master_on_break)

    # Запускаем очистку с передачей сессии
    await scheduler._cleanup_reminded_set(session=session)

    # Проверяем что мастер удалён из набора
    assert (
        master_on_break.id not in scheduler._reminded_master_breaks
    ), "Мастер должен быть удалён из набора после окончания перерыва"


@pytest.mark.asyncio
async def test_reminder_requeued_after_break_extension(
    session, master_on_break, monkeypatch
):
    """Тест: Повторное напоминание ставится после продления перерыва."""
    scheduler._reminded_master_breaks.clear()

    @asynccontextmanager
    async def _session_override():
        yield session

    monkeypatch.setattr(scheduler, "SessionLocal", lambda: _session_override())

    # Устанавливаем перерыв так, чтобы он подходил под критерии напоминания
    master_on_break.shift_status = m.ShiftStatus.BREAK
    master_on_break.is_on_shift = False
    master_on_break.break_until = datetime.now(timezone.utc) + timedelta(
        minutes=scheduler.REMINDER_MINUTES_BEFORE - 1
    )
    await session.commit()
    await session.refresh(master_on_break)

    notifications_count = await session.scalar(
        select(func.count()).select_from(m.notifications_outbox)
    )
    assert notifications_count == 0

    await scheduler._check_breaks_once()

    notifications_count = await session.scalar(
        select(func.count()).select_from(m.notifications_outbox)
    )
    assert notifications_count == 1
    assert master_on_break.id in scheduler._reminded_master_breaks

    # Продлеваем перерыв и убеждаемся, что запись в кэше очищается
    master_on_break.break_until = datetime.now(timezone.utc) + timedelta(minutes=30)
    await session.commit()
    await session.refresh(master_on_break)

    await scheduler._cleanup_reminded_set(session=session)
    assert master_on_break.id not in scheduler._reminded_master_breaks

    # Снова сокращаем перерыв, чтобы он подходил для напоминания
    master_on_break.break_until = datetime.now(timezone.utc) + timedelta(
        minutes=scheduler.REMINDER_MINUTES_BEFORE - 1
    )
    await session.commit()
    await session.refresh(master_on_break)

    await scheduler._check_breaks_once()

    notifications_count = await session.scalar(
        select(func.count()).select_from(m.notifications_outbox)
    )
    assert notifications_count == 2
    assert master_on_break.id in scheduler._reminded_master_breaks


@pytest.mark.asyncio
async def test_break_duration_constant():
    """Тест: Проверяем константы."""
    assert (
        scheduler.REMINDER_MINUTES_BEFORE == 10
    ), "Напоминание должно отправляться за 10 минут"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
