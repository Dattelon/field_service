from __future__ import annotations

import html
from typing import Any, Iterable

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton

from field_service.bots.common import safe_answer_callback, safe_edit_or_send
from field_service.db import models as m
from field_service.bots.admin_bot.services import settings as admin_settings_service
from ..utils import inline_keyboard

router = Router(name="master_requisites")

PAYMENT_METHOD_LABELS = {
    "card": "Банковская карта",
    "sbp": "СБП",
    "cash": "Наличные",
}


def _format_methods(methods: Iterable[str]) -> str:
    """Форматирование списка способов оплаты."""
    items: list[str] = []
    for raw in methods:
        key = str(raw).strip().lower()
        if not key:
            continue
        label = PAYMENT_METHOD_LABELS.get(key, key.upper())
        items.append(label)
    return ", ".join(items) if items else "—"


def _format_card_block(data: dict[str, Any]) -> list[str]:
    """Форматирование блока информации о карте."""
    card_number = data.get("card_number") or ""
    card_holder = data.get("card_holder") or ""
    card_bank = data.get("card_bank") or ""
    block: list[str] = []
    if card_number or card_holder or card_bank:
        block.append("<b>💳 Карта</b>")
        if card_number:
            block.append(f"💳 Номер: {html.escape(card_number)}")
        if card_holder:
            block.append(f"👤 Держатель: {html.escape(card_holder)}")
        if card_bank:
            block.append(f"🏦 Банк: {html.escape(card_bank)}")
    return block


def _format_sbp_block(data: dict[str, Any]) -> list[str]:
    """Форматирование блока информации о СБП."""
    phone = data.get("sbp_phone") or ""
    bank = data.get("sbp_bank") or ""
    block: list[str] = []
    if phone or bank:
        block.append("<b>📱 СБП</b>")
        if phone:
            block.append(f"📱 Телефон: {html.escape(phone)}")
        if bank:
            block.append(f"🏦 Банк: {html.escape(bank)}")
    return block


def _format_requisites_text(snapshot: dict[str, Any]) -> str:
    """Форматирование реквизитов для отображения мастеру."""
    methods = _format_methods(snapshot.get("methods") or [])
    lines: list[str] = [
        "<b>💳 Реквизиты для оплаты</b>",
        "",
        f"<b>Способы оплаты:</b> {methods}",
    ]

    card_block = _format_card_block(snapshot)
    sbp_block = _format_sbp_block(snapshot)
    other_text = snapshot.get("other_text") or ""
    comment_template = snapshot.get("comment_template") or ""

    if card_block:
        lines.append("")
        lines.extend(card_block)
    if sbp_block:
        lines.append("")
        lines.extend(sbp_block)
    if other_text:
        lines.append("")
        lines.append("<b>📝 Прочие данные</b>")
        lines.append(html.escape(other_text))
    if comment_template:
        lines.append("")
        lines.append("<b>💬 Комментарий для перевода</b>")
        lines.append(html.escape(comment_template))

    lines.append("")
    lines.append("Данные актуальны. При возникновении вопросов обращайтесь к администратору.")

    return "\n".join(lines)


@router.callback_query(F.data == "m:req")
async def show_payment_requisites(
    callback: CallbackQuery,
    master: m.masters,
) -> None:
    """Обработчик для показа реквизитов владельца мастеру."""
    if not callback.message:
        await safe_answer_callback(callback)
        return

    # Получаем реквизиты владельца
    try:
        settings_service = admin_settings_service.DBSettingsService()
        snapshot = await settings_service.get_owner_pay_snapshot()
    except Exception as e:
        await safe_answer_callback(callback, "❌ Ошибка загрузки реквизитов.", show_alert=True)
        return

    # Форматируем текст
    text = _format_requisites_text(snapshot)

    # Создаем клавиатуру с кнопкой "Назад в меню"
    keyboard = inline_keyboard(
        [
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="m:menu")],
        ]
    )

    # Проверяем наличие QR-кода СБП
    qr_file_id = snapshot.get("sbp_qr_file_id") or ""

    try:
        # Если есть QR-код, отправляем его вместе с текстом
        if qr_file_id:
            # Сначала удаляем старое сообщение
            try:
                await callback.message.delete()
            except Exception:
                pass
            # Отправляем новое сообщение с фото
            await callback.message.answer_photo(
                photo=qr_file_id,
                caption=text,
                reply_markup=keyboard,
            )
        else:
            # Если QR-кода нет, просто редактируем текст
            await safe_edit_or_send(callback.message, text, keyboard)
    except Exception as e:
        # В случае ошибки отправляем текст без QR
        await safe_edit_or_send(callback.message, text, keyboard)

    await safe_answer_callback(callback)
