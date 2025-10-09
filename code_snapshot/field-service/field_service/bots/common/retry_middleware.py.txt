"""
Middleware для перехвата ошибок и предложения повтора действия.

Оборачивает все callback handlers и при возникновении исключения
сохраняет контекст и показывает пользователю кнопку "Повторить".
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, TelegramObject
from aiogram.utils.keyboard import InlineKeyboardBuilder

from .retry_context import save_retry_context

__all__ = ["RetryMiddleware", "setup_retry_middleware"]

logger = logging.getLogger(__name__)


class RetryMiddleware(BaseMiddleware):
    """
    Middleware для отлова ошибок и предложения повтора действия.

    Оборачивает callback handlers и при ошибке:
    1. Логирует исключение
    2. Сохраняет контекст действия в FSM
    3. Показывает пользователю UI с кнопкой "Повторить"
    """

    def __init__(self, enabled: bool = True):
        """
        Инициализация middleware.

        Args:
            enabled: Включить/выключить функциональность
        """
        self.enabled = enabled
        super().__init__()

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        """
        Основная логика middleware.

        Args:
            handler: Следующий handler в цепочке
            event: Событие от Telegram
            data: Данные контекста

        Returns:
            Результат handler или None при ошибке
        """
        if not self.enabled:
            return await handler(event, data)

        # Обрабатываем только CallbackQuery
        if not isinstance(event, CallbackQuery):
            return await handler(event, data)

        callback = event

        try:
            # Выполняем основной handler
            return await handler(event, data)

        except Exception as exc:
            # Логируем ошибку
            logger.error(
                f"Error in callback handler: {callback.data}",
                exc_info=exc,
                extra={
                    "user_id": callback.from_user.id,
                    "callback_data": callback.data,
                },
            )

            # Сохраняем контекст для повтора
            state = data.get("state")
            if state and callback.data:
                await save_retry_context(
                    state=state,
                    callback_data=callback.data,
                    user_id=callback.from_user.id,
                    chat_id=callback.message.chat.id,
                    message_id=callback.message.message_id,
                    attempt=1,
                )

            # Показываем сообщение об ошибке с кнопкой повтора
            await self._show_error_with_retry(callback, exc)

            # Не пробрасываем исключение дальше
            return None

    async def _show_error_with_retry(
        self,
        callback: CallbackQuery,
        exc: Exception,
    ) -> None:
        """
        Показать сообщение об ошибке с кнопкой повтора.

        Args:
            callback: CallbackQuery с ошибкой
            exc: Исключение которое произошло
        """
        # Формируем текст ошибки
        error_text = (
            "❌ <b>Не удалось выполнить действие</b>\n\n"
            "Возможные причины:\n"
            "• Временные проблемы с сетью\n"
            "• Превышено время ожидания\n"
            "• Технические работы на сервере\n\n"
            "Вы можете:"
        )

        # Создаём кнопки
        builder = InlineKeyboardBuilder()
        builder.button(text="🔄 Повторить", callback_data="retry:execute")
        builder.button(text="❌ Отменить", callback_data="retry:cancel")
        builder.adjust(2)

        try:
            await callback.message.edit_text(
                text=error_text,
                reply_markup=builder.as_markup(),
            )
        except Exception:
            # Если не удалось отредактировать, отправляем новое сообщение
            try:
                await callback.message.answer(
                    text=error_text,
                    reply_markup=builder.as_markup(),
                )
            except Exception as send_exc:
                logger.error(
                    "Failed to send error message",
                    exc_info=send_exc,
                )


def setup_retry_middleware(dp, enabled: bool = True) -> None:
    """
    Подключить retry middleware к dispatcher.

    Args:
        dp: Dispatcher
        enabled: Включить/выключить функциональность
    """
    middleware = RetryMiddleware(enabled=enabled)
    dp.callback_query.middleware(middleware)
