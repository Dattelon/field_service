from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from aiogram import Bot

from field_service.db.session import SessionLocal
from field_service.services import live_log
from field_service.services.commission_service import apply_overdue_commissions

UTC = timezone.utc
logger = logging.getLogger("watchdogs")


async def watchdog_commissions_overdue(
    bot: Bot,
    alerts_chat_id: Optional[int],
    interval_seconds: int = 60,
) -> None:
    """Periodically block overdue commissions and notify admins."""
    while True:
        try:
            async with SessionLocal() as session:
                blocked_masters = await apply_overdue_commissions(
                    session, now=datetime.now(UTC)
                )
                await session.commit()

            if blocked_masters:
                details = ", ".join(str(mid) for mid in blocked_masters)
                message = (
                    "[finance] commission_overdue autoblock "
                    f"count={len(blocked_masters)} masters=[{details}]"
                )
                live_log.push("watchdog", message, level="WARN")
                if alerts_chat_id is not None and bot is not None:
                    try:
                        await bot.send_message(alerts_chat_id, message)
                    except Exception:
                        logger.warning("watchdog notification failed", exc_info=True)
                        live_log.push("watchdog", "notification send failed", level="WARN")
                else:
                    logger.info(message)
        except Exception as exc:
            logger.exception("watchdog_commissions_overdue error")
            live_log.push("watchdog", f"watchdog_commissions_overdue error: {exc}", level="ERROR")

        await asyncio.sleep(interval_seconds)
