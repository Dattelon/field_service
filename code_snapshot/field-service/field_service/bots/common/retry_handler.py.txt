"""
Обработчик повтора действий после ошибок.

Отвечает за выполнение повторных попыток с сохранённым контекстом
и управление лимитом попыток.
"""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Update

from .retry_context import (
    RetryContext,
    clear_retry_context,
    load_retry_context,
    save_retry_context,
)

__all__ = ["retry_router"]

logger = logging.getLogger(__name__)

retry_router = Router(name="retry")


@retry_router.callback_query(F.data == "retry:execute")
async def retry_execute(callback: CallbackQuery, state: FSMContext):
    """
    Повторить последнее действие.

    Загружает сохранённый контекст, проверяет лимит попыток,
    и повторяет действие с исходным callback_data.

    Args:
        callback: CallbackQuery от кнопки "Повторить"
        state: FSM контекст
    """
    # Загружаем контекст
    ctx = await load_retry_context(state)

    if not ctx:
        await callback.answer(
            "❌ Не удалось загрузить контекст повтора",
            show_alert=True,
        )
        return

    if not ctx.can_retry():
        await callback.answer(
            f"❌ Превышено максимальное количество попыток ({RetryContext.MAX_ATTEMPTS})",
            show_alert=True,
        )
        await clear_retry_context(state)
        return

    # Увеличиваем счётчик попыток
    await save_retry_context(
        state=state,
        callback_data=ctx.callback_data,
        user_id=ctx.user_id,
        chat_id=ctx.chat_id,
        message_id=ctx.message_id,
        attempt=ctx.attempt + 1,
    )

    # Информируем пользователя
    await callback.answer(
        "🔄 Повторяю действие...",
        show_alert=False,
    )

    # Логируем повтор
    logger.info(
        f"Retrying action: {ctx.callback_data}, attempt {ctx.attempt + 1}",
        extra={
            "user_id": ctx.user_id,
            "callback_data": ctx.callback_data,
            "attempt": ctx.attempt + 1,
        },
    )

    # Создаем копию callback с оригинальным callback_data
    # CallbackQuery это frozen Pydantic модель, поэтому используем model_copy
    modified_callback = callback.model_copy(update={"data": ctx.callback_data})

    # Повторяем обработку
    # Router автоматически найдёт нужный handler по callback.data
    try:
        # Получаем dispatcher и триггерим повторную обработку
        from aiogram import Bot

        bot: Bot = callback.bot
        # Исправлено: bot это не словарь в aiogram 3.x, используем workflow_data
        dp = bot.workflow_data.get("dp") if hasattr(bot, "workflow_data") else None

        if dp:
            # Создаем новый Update с модифицированным callback
            update = Update(
                update_id=0,  # Не важно для повторной обработки
                callback_query=modified_callback,
            )
            
            # Обрабатываем через dispatcher
            await dp.feed_update(bot, update)

            # Если успешно - очищаем контекст
            await clear_retry_context(state)
        else:
            # Fallback: если dispatcher не сохранён
            logger.warning("Dispatcher not found in bot storage")
            await callback.answer(
                "❌ Не удалось повторить действие (dispatcher не найден)",
                show_alert=True,
            )

    except Exception as exc:
        logger.error(
            f"Retry failed: {ctx.callback_data}",
            exc_info=exc,
        )
        # Middleware снова перехватит и предложит повтор


@retry_router.callback_query(F.data == "retry:cancel")
async def retry_cancel(callback: CallbackQuery, state: FSMContext):
    """
    Отменить повтор действия.

    Args:
        callback: CallbackQuery от кнопки "Отменить"
        state: FSM контекст
    """
    await clear_retry_context(state)

    await callback.message.edit_text(
        text="✅ Действие отменено",
    )

    await callback.answer()

    logger.info(
        "Retry cancelled by user",
        extra={
            "user_id": callback.from_user.id,
        },
    )
