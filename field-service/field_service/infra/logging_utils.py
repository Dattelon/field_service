from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from aiogram import Bot

from field_service.config import settings
from field_service.infra.notify import send_alert, send_log

__all__ = ["utcnow_iso", "start_heartbeat", "send_log", "send_alert"]

logger = logging.getLogger(__name__)
UTC = timezone.utc


def utcnow_iso() -> str:
    """Return current UTC timestamp in ISO 8601 format with Z suffix."""
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def start_heartbeat(
    bot: Bot,
    *,
    bot_name: str,
    interval_seconds: int,
    chat_id: int | None = None,
) -> asyncio.Task:
    """Spawn heartbeat loop for *bot* returning the created asyncio task.

    Deprecated in favour of field_service.services.heartbeat.run_heartbeat.
    """

    interval = max(5, int(interval_seconds) if interval_seconds else 60)
    target = chat_id if chat_id is not None else settings.logs_channel_id

    async def _heartbeat_loop() -> None:
        try:
            while True:
                message = f"[{bot_name}] Heartbeat OK {utcnow_iso()}"
                await send_log(bot, message, chat_id=target)
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Heartbeat loop stopped unexpectedly")

    return asyncio.create_task(_heartbeat_loop(), name=f"{bot_name}_heartbeat")
