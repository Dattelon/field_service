from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError, TelegramRetryAfter
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message


_LOGGER = logging.getLogger(__name__)
_T = TypeVar("_T")


class _SendQueue:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()

    async def call(self, factory: Callable[[], Awaitable[_T]]) -> _T:
        delay = 1.0
        while True:
            async with self._lock:
                try:
                    return await factory()
                except TelegramRetryAfter as exc:  # pragma: no cover - network timing
                    wait_time = max(float(exc.retry_after), delay)
                except TelegramBadRequest as exc:  # pragma: no cover - network timing
                    message = (exc.message or "").lower()
                    if "too many requests" not in message:
                        raise
                    wait_time = delay
                except TelegramNetworkError:  # pragma: no cover - flaky network
                    wait_time = delay
            await asyncio.sleep(wait_time)
            delay = min(delay * 2, 30.0)


_SEND_QUEUES: dict[int, _SendQueue] = {}


def _normalize_markup(markup: InlineKeyboardMarkup | None) -> Any:
    if markup is None:
        return None
    for attr in ("model_dump", "to_python", "dict"):
        method = getattr(markup, attr, None)
        if callable(method):
            try:
                return method(exclude_none=True) if attr != "to_python" else method()
            except TypeError:
                try:
                    return method()
                except TypeError:
                    continue
    inline_keyboard = getattr(markup, "inline_keyboard", None)
    if inline_keyboard is None:
        return repr(markup)
    normalized: list[list[Any]] = []
    for row in inline_keyboard:
        row_payload: list[Any] = []
        for button in row:
            payload: Any = button
            for attr in ("model_dump", "to_python", "dict"):
                method = getattr(button, attr, None)
                if callable(method):
                    try:
                        payload = (
                            method(exclude_none=True) if attr != "to_python" else method()
                        )
                    except TypeError:
                        try:
                            payload = method()
                        except TypeError:
                            continue
                    break
            row_payload.append(payload)
        normalized.append(row_payload)
    return normalized


def _queue_for(bot: Bot) -> _SendQueue:
    key = id(bot)
    queue = _SEND_QUEUES.get(key)
    if queue is None:
        queue = _SendQueue()
        _SEND_QUEUES[key] = queue
    return queue


async def _queue_call(bot: Bot, factory: Callable[[], Awaitable[_T]]) -> _T:
    queue = _queue_for(bot)
    return await queue.call(factory)


async def safe_edit_or_send(
    event: Message | CallbackQuery,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    **kwargs: Any,
) -> Message | None:
    """Edit the source message when possible or send a replacement."""

    if isinstance(event, CallbackQuery):
        message = event.message
        if message is not None:
            _LOGGER.info("safe_edit_or_send: attempting to edit message in chat %s", message.chat.id)
            try:
                result = await _queue_call(
                    message.bot,
                    lambda: message.edit_text(text, reply_markup=reply_markup, **kwargs),
                )
                _LOGGER.info("safe_edit_or_send: message edited successfully")
                return result
            except TelegramBadRequest as exc:
                message_text = (exc.message or "").lower()
                _LOGGER.info("safe_edit_or_send: edit failed with TelegramBadRequest: %s", exc.message)
                if "message is not modified" in message_text:
                    if reply_markup is not None:
                        current_markup = _normalize_markup(message.reply_markup)
                        new_markup = _normalize_markup(reply_markup)
                        if current_markup != new_markup:
                            _LOGGER.info("safe_edit_or_send: updating reply markup only")
                            try:
                                await _queue_call(
                                    message.bot,
                                    lambda: message.edit_reply_markup(
                                        reply_markup=reply_markup
                                    ),
                                )
                            except TelegramBadRequest as markup_exc:
                                _LOGGER.warning(
                                    "safe_edit_or_send markup edit failed: %s",
                                    markup_exc,
                                    exc_info=True,
                                )
                            else:
                                _LOGGER.info("safe_edit_or_send: markup updated successfully")
                                return message
                    _LOGGER.info(
                        "safe_edit_or_send: text unchanged, sending new message to chat %s", message.chat.id
                    )
                if "message to edit not found" not in message_text and "message can't be edited" not in message_text:
                    _LOGGER.warning("safe_edit_or_send edit failed: %s", exc, exc_info=True)
                target_chat = message.chat.id
                _LOGGER.info("safe_edit_or_send: sending new message to chat %s", target_chat)
                result = await _queue_call(
                    message.bot,
                    lambda: message.bot.send_message(
                        target_chat,
                        text,
                        reply_markup=reply_markup,
                        **kwargs,
                    ),
                )
                _LOGGER.info("safe_edit_or_send: new message sent successfully")
                return result
        _LOGGER.info("safe_edit_or_send: callback message is None, sending to user %s", event.from_user.id if event.from_user else None)
        if event.from_user is not None:
            return await _queue_call(
                event.bot,
                lambda: event.bot.send_message(
                    event.from_user.id,
                    text,
                    reply_markup=reply_markup,
                    **kwargs,
                ),
            )
        _LOGGER.warning("safe_edit_or_send: both message and from_user are None, cannot send message")
        return None

    if isinstance(event, Message):
        return await _queue_call(
            event.bot,
            lambda: event.answer(text, reply_markup=reply_markup, **kwargs),
        )

    raise TypeError(f"Unsupported event type: {type(event)!r}")


async def safe_answer_callback(
    callback: CallbackQuery,
    text: str | None = None,
    *,
    show_alert: bool = False,
    fallback_message: str = "Кнопка устарела, нажмите /start",
) -> None:
    """Answer callback queries, handling stale or repeated callbacks."""

    if callback is None:
        return
    try:
        await _queue_call(callback.bot, lambda: callback.answer(text, show_alert=show_alert))
    except TelegramBadRequest as exc:
        message = (exc.message or "").lower()
        if "query is too old" in message:
            if callback.from_user is not None:
                await _queue_call(
                    callback.bot,
                    lambda: callback.bot.send_message(callback.from_user.id, fallback_message),
                )
            return
        if "query id not found" in message:
            return
        raise


async def safe_send_message(bot: Bot, chat_id: int, text: str, **kwargs: Any) -> Message:
    return await _queue_call(bot, lambda: bot.send_message(chat_id, text, **kwargs))


async def safe_delete_and_send(
    callback: CallbackQuery,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    **kwargs: Any,
) -> Message | None:
    """Delete the callback message and send a new one. Perfect for menu navigation."""
    if callback.message is None:
        if callback.from_user is not None:
            return await _queue_call(
                callback.bot,
                lambda: callback.bot.send_message(
                    callback.from_user.id,
                    text,
                    reply_markup=reply_markup,
                    **kwargs,
                ),
            )
        return None

    # Удаляем старое сообщение
    try:
        await _queue_call(callback.bot, lambda: callback.message.delete())
    except TelegramBadRequest as exc:
        _LOGGER.debug("safe_delete_and_send: delete failed: %s", exc, exc_info=True)

    # Отправляем новое
    chat_id = callback.message.chat.id
    return await _queue_call(
        callback.bot,
        lambda: callback.bot.send_message(
            chat_id,
            text,
            reply_markup=reply_markup,
            **kwargs,
        ),
    )
