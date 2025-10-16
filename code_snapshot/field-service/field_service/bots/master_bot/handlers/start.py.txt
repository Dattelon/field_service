from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from field_service.bots.common import safe_answer_callback, safe_edit_or_send
from field_service.db import models as m

from ..keyboards import main_menu_keyboard, start_onboarding_keyboard
from ..texts import START_APPROVED, START_BLOCKED, START_NOT_APPROVED
from ..utils import escape_html

router = Router(name="master_start")

_STATUS_TITLES = {
    m.ModerationStatus.PENDING: "На модерации",
    m.ModerationStatus.APPROVED: "Одобрено",
    m.ModerationStatus.REJECTED: "Отклонено",
}


@router.message(CommandStart())
async def handle_start(message: Message, state: FSMContext, master: m.masters) -> None:
    await state.clear()
    await _render_start(message, master)

@router.message(Command("cancel"))
async def handle_cancel(message: Message, state: FSMContext, master: m.masters) -> None:
    await state.clear()
    await _render_start(message, master)


@router.callback_query(F.data == "m:cancel")
async def handle_cancel_callback(callback: CallbackQuery, state: FSMContext, master: m.masters) -> None:
    """Обработчик для кнопки ❌ Отменить - возвращает в главное меню из любого FSM-состояния."""
    await state.clear()
    if callback.message:
        await _render_start(callback.message, master)
    await safe_answer_callback(callback, "✅ Действие отменено")


@router.callback_query(F.data == "m:menu")
async def handle_menu(callback: CallbackQuery, state: FSMContext, master: m.masters) -> None:
    await state.clear()
    if callback.message:
        await _render_start(callback.message, master)
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
        escape_html(text),
    ]
    await safe_edit_or_send(message, "\n".join(lines), keyboard)



