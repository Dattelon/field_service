"""
Middleware       .

  callback handlers    
      "".
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
    Middleware       .

     callback handlers   :
    1.  
    2.     FSM
    3.   UI   ""
    """

    def __init__(self, enabled: bool = True):
        """
         middleware.

        Args:
            enabled: / 
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
          middleware.

        Args:
            handler:  handler  
            event:   Telegram
            data:  

        Returns:
             handler  None  
        """
        if not self.enabled:
            return await handler(event, data)

        #   CallbackQuery
        if not isinstance(event, CallbackQuery):
            return await handler(event, data)

        callback = event

        try:
            #   handler
            return await handler(event, data)

        except Exception as exc:
            logger.error(
                f"Error in callback handler: {callback.data}",
                exc_info=exc,
                extra={
                    "user_id": callback.from_user.id,
                    "callback_data": callback.data,
                },
            )

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

            await self._show_error_with_retry(callback, exc)

            return None

    async def _show_error_with_retry(
        self,
        callback: CallbackQuery,
        exc: Exception,
    ) -> None:
        """
              .

        Args:
            callback: CallbackQuery  
            exc:   
        """
        error_text = (
            " <b>   </b>\n\n"
            " :\n"
            "    \n"
            "   \n"
            "    \n\n"
            " :"
        )

        builder = InlineKeyboardBuilder()
        builder.button(text="Повторить", callback_data="retry:execute")
        builder.button(text="Отмена", callback_data="retry:cancel")
        builder.adjust(2)

        try:
            await callback.message.edit_text(
                text=error_text,
                reply_markup=builder.as_markup(),
            )
        except Exception:
            #    ,   
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
     retry middleware  dispatcher.

    Args:
        dp: Dispatcher
        enabled: / 
    """
    middleware = RetryMiddleware(enabled=enabled)
    dp.callback_query.middleware(middleware)
