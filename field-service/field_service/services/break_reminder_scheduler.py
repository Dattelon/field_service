"""
P1-16: НАПОМИНАНИЕ ОБ ОКОНЧАНИИ ПЕРЕРЫВА

За 10 минут до окончания перерыва отправляет напоминание мастеру
с предложением вернуться на смену или продлить перерыв.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from field_service.db import models as m
from field_service.db.session import SessionLocal
from field_service.services import live_log

UTC = timezone.utc

# За сколько минут до окончания перерыва отправлять напоминание
REMINDER_MINUTES_BEFORE = 10

# ID уведомления для дедупликации (чтобы не отправлять дважды одному мастеру)
_reminded_master_ids: set[int] = set()


async def _check_breaks_once() -> None:
    """Проверяет все перерывы и отправляет напоминания за 10 минут до окончания."""
    async with SessionLocal() as session:
        now = datetime.now(UTC)
        reminder_threshold = now + timedelta(minutes=REMINDER_MINUTES_BEFORE)
        
        # Находим всех мастеров на перерыве, у которых перерыв заканчивается в ближайшие 10 минут
        result = await session.execute(
            select(m.masters.id, m.masters.tg_user_id, m.masters.break_until)
            .where(
                m.masters.shift_status == m.ShiftStatus.BREAK,
                m.masters.break_until.isnot(None),
                m.masters.break_until <= reminder_threshold,
                m.masters.break_until > now,
            )
        )
        
        masters = result.all()
        
        if not masters:
            return
        
        # Отправляем напоминания только тем, кому ещё не отправляли
        for master_id, tg_user_id, break_until in masters:
            if master_id in _reminded_master_ids:
                continue  # Уже отправляли напоминание
            
            if not tg_user_id:
                continue  # Нет Telegram ID
            
            # Вычисляем сколько минут осталось
            time_left = break_until - now
            minutes_left = int(time_left.total_seconds() / 60)
            
            # Формируем сообщение
            message = (
                f"⏰ <b>Перерыв заканчивается через {minutes_left} мин</b>\n\n"
                "Готовы вернуться на смену?\n\n"
                "Нажмите кнопку ниже или продлите перерыв ещё на 2 часа."
            )
            
            # Добавляем в очередь уведомлений
            await session.execute(
                insert(m.notifications_outbox).values(
                    master_id=master_id,
                    event="break_reminder",
                    payload={
                        "message": message,
                        "minutes_left": minutes_left,
                        "break_until": break_until.isoformat(),
                    }
                )
            )
            
            # Помечаем, что отправили напоминание
            _reminded_master_ids.add(master_id)
            
            live_log.push(
                "break_reminder",
                f"Sent break reminder to master#{master_id}, {minutes_left}min left",
                level="INFO"
            )
        
        await session.commit()


async def _cleanup_reminded_set(session: AsyncSession | None = None) -> None:
    """
    Очищаем набор напоминаний для мастеров, у которых перерыв уже закончился.
    Это позволяет отправить напоминание снова, если мастер возьмёт новый перерыв.
    
    Args:
        session: Опциональная сессия для тестов
    """
    if session is not None:
        # Используем переданную сессию (для тестов)
        await _cleanup_impl(session)
    else:
        # Создаём свою сессию
        async with SessionLocal() as session:
            await _cleanup_impl(session)


async def _cleanup_impl(session: AsyncSession) -> None:
    """Внутренняя реализация очистки."""
    now = datetime.now(UTC)
    
    # Находим всех мастеров из _reminded_master_ids
    if not _reminded_master_ids:
        return
    
    result = await session.execute(
        select(m.masters.id)
        .where(
            m.masters.id.in_(_reminded_master_ids),
            # Перерыв закончился или мастер уже не на перерыве
            (m.masters.break_until.is_(None)) | (m.masters.break_until < now)
        )
    )
    
    finished_master_ids = {row[0] for row in result.all()}
    
    # Удаляем из набора
    _reminded_master_ids.difference_update(finished_master_ids)
    
    if finished_master_ids:
        live_log.push(
            "break_reminder",
            f"Cleaned up {len(finished_master_ids)} finished breaks from reminder set",
            level="DEBUG"
        )


async def run_break_reminder(*, interval_seconds: int = 60) -> None:
    """
    Основной цикл планировщика напоминаний о перерывах.
    
    Args:
        interval_seconds: Интервал проверки в секундах (по умолчанию 60 сек)
    """
    sleep_for = max(10, int(interval_seconds))
    
    live_log.push(
        "break_reminder",
        f"Break reminder scheduler started (interval={sleep_for}s, reminder={REMINDER_MINUTES_BEFORE}min before)",
        level="INFO"
    )
    
    while True:
        try:
            await _check_breaks_once()
            await _cleanup_reminded_set()
        except Exception as exc:
            live_log.push(
                "break_reminder",
                f"Error in break reminder: {exc}",
                level="ERROR"
            )
        
        await asyncio.sleep(sleep_for)
