from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from aiogram import Bot

from field_service.config import settings

logger = logging.getLogger(__name__)
UTC = timezone.utc


def utcnow_iso() -> str:
    """Return current UTC timestamp in ISO 8601 format with Z suffix."""
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


async def _safe_send(
    bot: Optional[Bot],
    chat_id: Optional[int],
    text: str,
    **kwargs: Any,
) -> None:
    if bot is None or chat_id is None:
        return
    if not text:
        return
    try:
        await bot.send_message(chat_id, text, **kwargs)
    except Exception:
        logger.warning("Failed to send message to chat %s", chat_id, exc_info=True)


async def send_log(
    bot: Optional[Bot],
    text: str,
    *,
    chat_id: Optional[int] = None,
    **kwargs: Any,
) -> None:
    """Send *text* to the logs channel, if configured."""
    target = chat_id if chat_id is not None else settings.logs_channel_id
    await _safe_send(bot, target, text, **kwargs)


async def send_alert(
    bot: Optional[Bot],
    text: str,
    *,
    chat_id: Optional[int] = None,
    reply_markup: Any | None = None,
    **kwargs: Any,
) -> None:
    """Send *text* to the alerts channel, if configured."""
    target = chat_id if chat_id is not None else settings.alerts_channel_id
    if reply_markup is not None:
        kwargs.setdefault("reply_markup", reply_markup)
    await _safe_send(bot, target, text, **kwargs)


def start_heartbeat(
    bot: Bot,
    *,
    bot_name: str,
    interval_seconds: int,
    chat_id: Optional[int] = None,
) -> asyncio.Task:
    """Spawn heartbeat loop for *bot* returning the created asyncio task."""

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
