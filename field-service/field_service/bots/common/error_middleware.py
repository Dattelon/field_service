from __future__ import annotations

import logging
from typing import Optional

from aiogram import Dispatcher
from aiogram.types import (
    CallbackQuery,
    ChatJoinRequest,
    ChatMemberUpdated,
    ErrorEvent,
    InlineQuery,
    Message,
    PreCheckoutQuery,
    ShippingQuery,
    TelegramObject,
    Update,
)

from field_service.infra.notify import send_alert, send_log

__all__ = ["setup_error_middleware"]

logger = logging.getLogger(__name__)


class _AlertingErrorHandler:
    def __init__(
        self,
        *,
        bot,
        bot_label: str,
        logs_chat_id: int | None,
        alerts_chat_id: int | None,
    ) -> None:
        self._bot = bot
        self._bot_label = bot_label
        self._logs_chat_id = logs_chat_id
        self._alerts_chat_id = alerts_chat_id

    async def __call__(self, event: ErrorEvent) -> bool:
        update = event.update
        update_type = _detect_update_type(update)
        user_id = _extract_user_id(update)
        header = f"❗ Ошибка {self._bot_label}"
        subheader = "Подробности см. в логах."
        lines = [header, subheader, f"Update: {update_type}"]
        if user_id is not None:
            lines.append(f'User: {user_id}')
        message = '\n'.join(lines)
        exception = getattr(event, 'exception', None)
        if exception is not None:
            logger.error(
                'Unhandled exception in %s',
                self._bot_label,
                exc_info=(type(exception), exception, exception.__traceback__),
            )
        else:
            logger.error('Unhandled error in %s without exception object', self._bot_label)
        await send_log(self._bot, message, chat_id=self._logs_chat_id)
        await send_alert(self._bot, message, chat_id=self._alerts_chat_id, exc=exception)
        return True


def setup_error_middleware(
    dp: Dispatcher,
    *,
    bot,
    bot_label: str,
    logs_chat_id: int | None,
    alerts_chat_id: int | None,
) -> None:
    """Attach unified error handler to dispatcher."""

    handler = _AlertingErrorHandler(
        bot=bot,
        bot_label=bot_label,
        logs_chat_id=logs_chat_id,
        alerts_chat_id=alerts_chat_id,
    )
    # Register a bound coroutine function explicitly to avoid un-awaited coroutine warnings
    dp.errors.register(handler.__call__)


def _detect_update_type(update: Update | TelegramObject | None) -> str:
    if update is None:
        return "unknown"
    update_type = getattr(update, "event_type", None) or getattr(update, "update_type", None)
    if update_type:
        return str(update_type)
    return type(update).__name__


def _extract_user_id(update: Update | TelegramObject | None) -> Optional[int]:
    if update is None:
        return None
    direct = getattr(update, "from_user", None)
    if direct is not None:
        return getattr(direct, "id", None)

    candidates = [
        getattr(update, attr, None)
        for attr in (
            "message",
            "edited_message",
            "callback_query",
            "inline_query",
            "chosen_inline_result",
            "shipping_query",
            "pre_checkout_query",
            "poll_answer",
            "my_chat_member",
            "chat_member",
            "chat_join_request",
        )
    ]
    for candidate in candidates:
        if candidate is None:
            continue
        user = getattr(candidate, "from_user", None) or getattr(candidate, "user", None)
        if user is not None:
            user_id = getattr(user, "id", None)
            if user_id is not None:
                return user_id
    return None

