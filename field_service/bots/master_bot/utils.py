from __future__ import annotations

import html
import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Iterable, Optional

from aiogram import Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

UTC = timezone.utc


def inline_keyboard(rows: Iterable[Iterable[InlineKeyboardButton]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[button for button in row] for row in rows])


def yes_no_keyboard(callback_yes: str, callback_no: str) -> InlineKeyboardMarkup:
    return inline_keyboard([
        [InlineKeyboardButton(text="Да", callback_data=callback_yes)],
        [InlineKeyboardButton(text="Нет", callback_data=callback_no)],
    ])


async def delete_message_silent(bot: Bot, chat_id: int, message_id: int) -> None:
    try:
        await bot.delete_message(chat_id, message_id)
    except Exception:
        pass


async def push_step_message(
    source: Message | CallbackQuery,
    state: FSMContext,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> Message:
    message = source if isinstance(source, Message) else source.message
    sent = await message.answer(text, reply_markup=reply_markup)
    data = await state.get_data()
    previous_id = data.get("last_step_msg_id")
    if previous_id:
        await delete_message_silent(message.bot, message.chat.id, previous_id)
    all_ids = list(data.get("step_msg_ids", []))
    all_ids.append(sent.message_id)
    await state.update_data(last_step_msg_id=sent.message_id, step_msg_ids=all_ids)
    return sent


async def clear_step_messages(bot: Bot, state: FSMContext, chat_id: int) -> None:
    data = await state.get_data()
    for message_id in data.get("step_msg_ids", []):
        await delete_message_silent(bot, chat_id, message_id)
    await state.update_data(last_step_msg_id=None, step_msg_ids=[])


def now_utc() -> datetime:
    return datetime.now(UTC)


def normalize_money(text: str | None) -> Optional[Decimal]:
    if not text:
        return None
    prepared = text.strip().replace(",", ".")
    if not prepared:
        return None
    if not re.fullmatch(r"^\d{1,7}(?:\.\d{1,2})?$", prepared):
        return None
    value = Decimal(prepared)
    if value <= 0:
        return None
    return value


def escape_html(value: str | None) -> str:
    return html.escape(value or "")
