from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import logging
from typing import Optional

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from field_service.db.session import SessionLocal
from field_service.db import models as m

UTC = timezone.utc
MAX_SEND_ATTEMPTS = 5
logger = logging.getLogger(__name__)


@asynccontextmanager
async def _maybe_session(session: Optional[AsyncSession]):
    """Context manager для работы с опциональной сессией."""
    if session is not None:
        # Используем переданную сессию, не закрываем её
        yield session
        return
    # Создаём временную сессию через SessionLocal
    async with SessionLocal() as s:
        yield s


async def _drain_outbox_once(bot: Bot, *, session: Optional[AsyncSession] = None) -> None:
    """Обработать один батч уведомлений из outbox.
    
    Args:
        bot: Bot instance для отправки сообщений
        session: Опциональная тестовая сессия
    """
    async with _maybe_session(session) as s:
        rows = await s.execute(
            select(
                m.notifications_outbox.id,
                m.notifications_outbox.master_id,
                m.notifications_outbox.event,  # P1-16: добавили event
                m.notifications_outbox.payload,
                m.masters.tg_user_id,
                m.notifications_outbox.attempt_count,
            )
            .join(m.masters, m.masters.id == m.notifications_outbox.master_id)
            .where(m.notifications_outbox.processed_at.is_(None))
            .order_by(m.notifications_outbox.id.asc())
            .limit(50)
        )
        items = rows.all()
        if not items:
            return
        for (
            outbox_id,
            master_id,
            event,
            payload,
            tg_user_id,
            attempt_count,
        ) in items:
            if not tg_user_id:
                # пометим как обработанное без отправки
                await s.execute(
                    update(m.notifications_outbox)
                    .where(m.notifications_outbox.id == outbox_id)
                    .values(processed_at=datetime.now(UTC))
                )
                continue
            text = str((payload or {}).get("message") or "Новая заявка")
            
            # P1-16: Для напоминания о перерыве добавляем клавиатуру
            reply_markup: Optional[InlineKeyboardMarkup] = None
            if event == "break_reminder":
                from field_service.bots.master_bot.keyboards import break_reminder_keyboard
                reply_markup = break_reminder_keyboard()
            
            current_attempt = (attempt_count or 0) + 1
            try:
                await bot.send_message(
                    int(tg_user_id),
                    text,
                    reply_markup=reply_markup,
                    parse_mode="HTML"
                )
            except Exception as exc:
                logger.exception(
                    "Failed to send notification %s for master %s", outbox_id, master_id
                )
                values: dict[str, object] = {
                    "attempt_count": current_attempt,
                    "last_error": str(exc),
                }
                if current_attempt >= MAX_SEND_ATTEMPTS:
                    values["processed_at"] = datetime.now(UTC)
                await s.execute(
                    update(m.notifications_outbox)
                    .where(m.notifications_outbox.id == outbox_id)
                    .values(**values)
                )
            else:
                await s.execute(
                    update(m.notifications_outbox)
                    .where(m.notifications_outbox.id == outbox_id)
                    .values(
                        processed_at=datetime.now(UTC),
                        attempt_count=current_attempt,
                        last_error=None,
                    )
                )
        await s.commit()


async def run_master_notifications(
    bot: Bot, 
    *, 
    interval_seconds: int = 5,
    session: Optional[AsyncSession] = None
) -> None:
    """Периодически обрабатывать очередь уведомлений.
    
    Args:
        bot: Bot instance для отправки сообщений
        interval_seconds: Интервал проверки в секундах
        session: Опциональная тестовая сессия (для тестов)
    """
    sleep_for = max(1, int(interval_seconds))
    while True:
        try:
            await _drain_outbox_once(bot, session=session)
        except Exception:
            # Не падаем из‑за сбоев доставки, просто пишем в лог stderr
            logger.exception("Failed to drain notifications outbox")
        await asyncio.sleep(sleep_for)
