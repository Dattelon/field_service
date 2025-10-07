from __future__ import annotations

import logging
import traceback
from typing import Any
import html

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest

from field_service.config import settings

__all__ = ["send_log", "send_alert", "send_report"]

_MAX_MESSAGE_LEN = 4096
_logger = logging.getLogger(__name__)


def _trim_message(text: str) -> str:
    text = (text or "").strip()
    if len(text) <= _MAX_MESSAGE_LEN:
        return text
    return text[: _MAX_MESSAGE_LEN - 3] + "..."


def _compose_alert(text: str, exc: BaseException | None) -> str:
    parts: list[str] = []
    if text:
        parts.append(text.strip())
    if exc is not None:
        parts.append(f"{type(exc).__name__}: {exc}")
        tb_lines = traceback.format_exception(exc.__class__, exc, exc.__traceback__)
        cleaned = [line.strip() for line in tb_lines if line.strip()]
        if cleaned:
            parts.append("Traceback:")
            parts.extend(cleaned[:3])
    return _trim_message("\n".join(parts))


async def _safe_send(
    bot: Bot | None,
    chat_id: int | None,
    text: str,
    **kwargs: Any,
) -> None:
    if bot is None or chat_id is None:
        return
    payload = html.escape(_trim_message(text), quote=False)
    if not payload:
        return
    try:
        await bot.send_message(chat_id, payload, **kwargs)
    except TelegramBadRequest as exc:
        _logger.warning("Failed to deliver message to chat_id=%s: %s", chat_id, exc)
    except Exception:
        _logger.warning("Failed to deliver message to chat_id=%s", chat_id, exc_info=True)


async def send_log(
    bot: Bot | None,
    text: str,
    *,
    chat_id: int | None = None,
    **kwargs: Any,
) -> None:
    """Send *text* to the logs channel, if configured."""

    target = chat_id if chat_id is not None else settings.logs_channel_id
    await _safe_send(bot, target, text, **kwargs)


async def send_alert(
    bot: Bot | None,
    text: str,
    *,
    chat_id: int | None = None,
    exc: BaseException | None = None,
    **kwargs: Any,
) -> None:
    """Send alert notification to the configured channel."""

    target = chat_id if chat_id is not None else settings.alerts_channel_id
    payload = _compose_alert(text, exc)
    await _safe_send(bot, target, payload, **kwargs)



async def send_report(
    bot: Bot | None,
    text: str,
    *,
    chat_id: int | None = None,
    **kwargs: Any,
) -> None:
    """Send report notification to the configured channel."""

    target = chat_id if chat_id is not None else settings.reports_channel_id
    await _safe_send(bot, target, text, **kwargs)
