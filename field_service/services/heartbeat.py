from __future__ import annotations

import asyncio
import logging
from typing import Literal

from aiogram import Bot

from field_service.config import settings
from field_service.infra.notify import send_log

__all__ = ["run_heartbeat"]

logger = logging.getLogger(__name__)


async def run_heartbeat(
    bot: Bot,
    name: Literal["admin", "master"],
    *,
    chat_id: int | None = None,
    interval: int | None = None,
) -> None:
    """Send heartbeat messages to the logs channel every configured interval."""

    resolved = interval if interval is not None else settings.heartbeat_seconds or 60
    sleep_for = max(1.0, float(resolved))
    try:
        while True:
            await send_log(bot, f"heartbeat: {name} alive", chat_id=chat_id)
            await asyncio.sleep(sleep_for)
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("Heartbeat loop for %s bot failed", name)
