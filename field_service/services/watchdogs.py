from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from field_service.db.session import SessionLocal
from field_service.infra.notify import send_alert
from field_service.services import live_log
from field_service.services.commission_service import (
    CommissionOverdueEvent,
    apply_overdue_commissions,
)

UTC = timezone.utc
logger = logging.getLogger("watchdogs")


async def watchdog_commissions_overdue(
    bot: Bot,
    alerts_chat_id: Optional[int],
    interval_seconds: int = 600,
    *,
    iterations: int | None = None,
) -> None:
    """Periodically block overdue commissions and notify admins."""

    sleep_for = max(60, int(interval_seconds) if interval_seconds else 600)
    loops_done = 0
    while True:
        try:
            async with SessionLocal() as session:
                events = await apply_overdue_commissions(session, now=datetime.now(UTC))
                await session.commit()

            if events:
                live_log.push("watchdog", f"commission_overdue count={len(events)}", level="WARN")
                for event in events:
                    live_log.push(
                        "watchdog",
                        f"commission_overdue cid={event.commission_id} order={event.order_id} master={event.master_id}",
                        level="WARN",
                    )
                if alerts_chat_id is not None and bot is not None:
                    for event in events:
                        await _notify_overdue_commission(bot, alerts_chat_id, event)
                for event in events:
                    logger.info(
                        "commission_overdue cid=%s order=%s master=%s",
                        event.commission_id,
                        event.order_id,
                        event.master_id,
                    )
        except Exception as exc:
            logger.exception("watchdog_commissions_overdue error")
            live_log.push("watchdog", f"watchdog_commissions_overdue error: {exc}", level="ERROR")

        loops_done += 1
        if iterations is not None and loops_done >= iterations:
            break

        await asyncio.sleep(sleep_for)


async def _notify_overdue_commission(bot: Bot, chat_id: int, event: CommissionOverdueEvent) -> None:
    name = event.master_full_name or "Неизвестный мастер"
    message = (
        f"🚫 Просрочка комиссии #{event.commission_id} (заказ #{event.order_id}). "
        f"Мастер {name}, id={event.master_id} заблокирован."
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Открыть комиссию",
                    callback_data=f"adm:f:cm:{event.commission_id}",
                )
            ]
        ]
    )
    try:
        await send_alert(bot, message, chat_id=chat_id, reply_markup=keyboard)
    except Exception:
        logger.warning("watchdog notification failed", exc_info=True)
        live_log.push("watchdog", "notification send failed", level="WARN")
