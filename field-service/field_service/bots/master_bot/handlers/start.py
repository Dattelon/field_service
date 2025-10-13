from __future__ import annotations

from datetime import datetime, timezone
from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from field_service.bots.common import (
    safe_answer_callback,
    safe_delete_and_send,
    safe_edit_or_send,
)
from field_service.db import models as m

from ..keyboards import main_menu_keyboard, start_onboarding_keyboard
from ..texts import START_APPROVED, START_BLOCKED, START_NOT_APPROVED
from ..utils import (
    cleanup_close_prompts,
    cleanup_finance_prompts,
    clear_step_messages,
    escape_html,
    now_utc,
)

router = Router(name="master_start")

_STATUS_TITLES = {
    m.ModerationStatus.PENDING: "На модерации",
    m.ModerationStatus.APPROVED: "Одобрено",
    m.ModerationStatus.REJECTED: "Отклонено",
}


def _format_break_time_left(break_until: datetime) -> str:
    """
    Форматирует оставшееся время перерыва в человеко-читаемый вид.
    
    Args:
        break_until: Время окончания перерыва (UTC)
    
    Returns:
        Строка вида "⏰ Перерыв до 14:30 (осталось 45 мин)"
    """
    now = now_utc()
    
    # Если перерыв уже закончился
    if break_until <= now:
        return "⏰ Перерыв закончился"
    
    # Вычисляем оставшееся время
    time_left = break_until - now
    total_seconds = int(time_left.total_seconds())
    
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    
    # Форматируем время окончания перерыва (локальное время)
    break_time_str = break_until.strftime("%H:%M")
    
    # Форматируем оставшееся время
    if hours > 0:
        time_left_str = f"{hours} ч {minutes} мин"
    else:
        time_left_str = f"{minutes} мин"
    
    return f"⏰ Перерыв до {break_time_str} (осталось {time_left_str})"


@router.message(CommandStart())
async def handle_start(message: Message, state: FSMContext, master: m.masters) -> None:
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"handle_start: START uid={message.from_user.id if message.from_user else 'None'} master_id={master.id if master else 'None'}")
    bot_instance = getattr(message, "bot", None)
    chat = getattr(message, "chat", None)
    chat_id = getattr(chat, "id", None)
    await cleanup_close_prompts(
        state,
        bot_instance,
        chat_id,
    )
    await cleanup_finance_prompts(
        state,
        bot_instance,
        chat_id,
    )
    if bot_instance and chat_id is not None:
        await clear_step_messages(bot_instance, state, chat_id)
    await state.clear()
    logger.info(f"handle_start: calling _render_start")
    try:
        await _render_start(message, master)
        logger.info(f"handle_start: _render_start completed")
    except Exception as e:
        logger.exception(f"handle_start: ERROR {e}")
        raise

@router.message(Command("cancel"))
async def handle_cancel(message: Message, state: FSMContext, master: m.masters) -> None:
    bot_instance = getattr(message, "bot", None)
    chat = getattr(message, "chat", None)
    chat_id = getattr(chat, "id", None)
    await cleanup_close_prompts(
        state,
        bot_instance,
        chat_id,
    )
    await cleanup_finance_prompts(
        state,
        bot_instance,
        chat_id,
    )
    if bot_instance and chat_id is not None:
        await clear_step_messages(bot_instance, state, chat_id)
    await state.clear()
    await _render_start(message, master)


@router.callback_query(F.data == "m:cancel")
async def handle_cancel_callback(callback: CallbackQuery, state: FSMContext, master: m.masters) -> None:
    """Обработчик для кнопки ❌ Отменить - возвращает в главное меню из любого FSM-состояния."""
    message = callback.message
    bot_instance = getattr(message, "bot", None) or getattr(callback, "bot", None)
    chat = getattr(message, "chat", None)
    chat_id = getattr(chat, "id", None)
    if chat_id is None and getattr(callback, "from_user", None) is not None:
        chat_id = getattr(callback.from_user, "id", None)
    await cleanup_close_prompts(state, bot_instance, chat_id)
    await cleanup_finance_prompts(state, bot_instance, chat_id)
    if bot_instance and chat_id is not None:
        await clear_step_messages(bot_instance, state, chat_id)
    await state.clear()

    # Подготовка контента меню
    moderation = getattr(master, "moderation_status", m.ModerationStatus.PENDING)
    verified = getattr(master, "verified", False)
    is_deleted = getattr(master, "is_deleted", False)

    if is_deleted:
        text = START_BLOCKED
        keyboard = start_onboarding_keyboard()
    elif not verified:
        text = START_NOT_APPROVED
        keyboard = start_onboarding_keyboard()
    else:
        text = START_APPROVED
        keyboard = main_menu_keyboard(master)

    if isinstance(text, (tuple, list)):
        text = "\n".join(str(part) for part in text)

    status_label = _STATUS_TITLES.get(moderation, str(moderation))
    lines = [
        "<b>Field Service — мастер</b>",
        f"Статус анкеты: {status_label}",
        "",
    ]
    
    # Если мастер на перерыве, показываем таймер
    if verified and master.shift_status == m.ShiftStatus.BREAK and master.break_until:
        break_info = _format_break_time_left(master.break_until)
        lines.append(break_info)
        lines.append("")
    
    lines.append(escape_html(text))

    # Удаляем старое сообщение и отправляем новое
    await safe_delete_and_send(callback, "\n".join(lines), keyboard)
    await safe_answer_callback(callback, "✅ Действие отменено")


@router.callback_query(F.data == "m:menu")
async def handle_menu(callback: CallbackQuery, state: FSMContext, master: m.masters) -> None:
    """Обработчик кнопки 🏠 Меню - удаляет текущее сообщение и показывает главное меню."""
    message = callback.message
    bot_instance = getattr(message, "bot", None) or getattr(callback, "bot", None)
    chat = getattr(message, "chat", None)
    chat_id = getattr(chat, "id", None)
    if chat_id is None and getattr(callback, "from_user", None) is not None:
        chat_id = getattr(callback.from_user, "id", None)
    await cleanup_close_prompts(state, bot_instance, chat_id)
    await cleanup_finance_prompts(state, bot_instance, chat_id)
    if bot_instance and chat_id is not None:
        await clear_step_messages(bot_instance, state, chat_id)
    await state.clear()

    # Подготовка контента меню
    moderation = getattr(master, "moderation_status", m.ModerationStatus.PENDING)
    verified = getattr(master, "verified", False)
    is_deleted = getattr(master, "is_deleted", False)

    if is_deleted:
        text = START_BLOCKED
        keyboard = start_onboarding_keyboard()
    elif not verified:
        text = START_NOT_APPROVED
        keyboard = start_onboarding_keyboard()
    else:
        text = START_APPROVED
        keyboard = main_menu_keyboard(master)

    if isinstance(text, (tuple, list)):
        text = "\n".join(str(part) for part in text)

    status_label = _STATUS_TITLES.get(moderation, str(moderation))
    lines = [
        "<b>Field Service — мастер</b>",
        f"Статус анкеты: {status_label}",
        "",
    ]
    
    # Если мастер на перерыве, показываем таймер
    if verified and master.shift_status == m.ShiftStatus.BREAK and master.break_until:
        break_info = _format_break_time_left(master.break_until)
        lines.append(break_info)
        lines.append("")
    
    lines.append(escape_html(text))

    # Удаляем старое сообщение и отправляем новое
    await safe_delete_and_send(callback, "\n".join(lines), keyboard)
    await safe_answer_callback(callback)


async def _render_start(message: Message, master: m.masters) -> None:
    moderation = getattr(master, "moderation_status", m.ModerationStatus.PENDING)
    verified = getattr(master, "verified", False)
    is_deleted = getattr(master, "is_deleted", False)

    if is_deleted:
        text = START_BLOCKED
        keyboard = start_onboarding_keyboard()
    elif not verified:
        text = START_NOT_APPROVED
        keyboard = start_onboarding_keyboard()
    else:
        text = START_APPROVED
        keyboard = main_menu_keyboard(master)

    # Normalize tuple/list texts to a single string
    if isinstance(text, (tuple, list)):
        text = "\n".join(str(part) for part in text)

    status_label = _STATUS_TITLES.get(moderation, str(moderation))
    lines = [
        "<b>Field Service — мастер</b>",
        f"Статус анкеты: {status_label}",
        "",
    ]
    
    # Если мастер на перерыве, показываем таймер
    if verified and master.shift_status == m.ShiftStatus.BREAK and master.break_until:
        break_info = _format_break_time_left(master.break_until)
        lines.append(break_info)
        lines.append("")
    
    lines.append(escape_html(text))
    
    await safe_edit_or_send(message, "\n".join(lines), keyboard)



