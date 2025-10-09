from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Optional

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup
from sqlalchemy import select, update

from field_service.db.session import SessionLocal
from field_service.db import models as m

UTC = timezone.utc


async def _drain_outbox_once(bot: Bot) -> None:
    async with SessionLocal() as session:
        rows = await session.execute(
            select(
                m.notifications_outbox.id,
                m.notifications_outbox.master_id,
                m.notifications_outbox.event,  # P1-16: добавили event
                m.notifications_outbox.payload,
                m.masters.tg_user_id,
            )
            .join(m.masters, m.masters.id == m.notifications_outbox.master_id)
            .where(m.notifications_outbox.processed_at.is_(None))
            .order_by(m.notifications_outbox.id.asc())
            .limit(50)
        )
        items = rows.all()
        if not items:
            return
        now = datetime.now(UTC)
        for outbox_id, master_id, event, payload, tg_user_id in items:
            if not tg_user_id:
                # пометим как обработанное без отправки
                await session.execute(
                    update(m.notifications_outbox)
                    .where(m.notifications_outbox.id == outbox_id)
                    .values(processed_at=now)
                )
                continue
            text = str((payload or {}).get("message") or "Новая заявка")
            
            # P1-16: Для напоминания о перерыве добавляем клавиатуру
            reply_markup: Optional[InlineKeyboardMarkup] = None
            if event == "break_reminder":
                from field_service.bots.master_bot.keyboards import break_reminder_keyboard
                reply_markup = break_reminder_keyboard()
            
            try:
                await bot.send_message(
                    int(tg_user_id),
                    text,
                    reply_markup=reply_markup,
                    parse_mode="HTML"
                )
            finally:
                await session.execute(
                    update(m.notifications_outbox)
                    .where(m.notifications_outbox.id == outbox_id)
                    .values(processed_at=now)
                )
        await session.commit()


async def run_master_notifications(bot: Bot, *, interval_seconds: int = 5) -> None:
    sleep_for = max(1, int(interval_seconds))
    while True:
        try:
            await _drain_outbox_once(bot)
        except Exception:
            # Не падаем из‑за сбоев доставки, просто пишем в лог stderr
            pass
        await asyncio.sleep(sleep_for)

