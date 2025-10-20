"""
Утилиты для быстрого копирования данных (P1-19).

Предоставляет callback handlers и helper функции для копирования
телефонов, адресов и других данных одним кликом.

Подход: callback_data содержит только ID заказа и тип данных,
сами данные загружаются из БД в handler'е.
"""
from __future__ import annotations

from aiogram.types import InlineKeyboardButton


def copy_button(
    text: str, 
    order_id: int, 
    data_type: str,
    bot_prefix: str = "m"
) -> InlineKeyboardButton:
    """
    Создаёт кнопку для копирования данных заказа.
    
    Args:
        text: Текст кнопки (например "📋 Копировать телефон")
        order_id: ID заказа
        data_type: Тип данных для копирования:
            - "cph" = client_phone
            - "addr" = address
            - "mph" = master_phone (для admin)
        bot_prefix: Префикс бота ("m" для master, "adm" для admin)
    
    Returns:
        InlineKeyboardButton с callback_data вида "prefix:copy:type:order_id"
    
    Example:
        >>> copy_button("📋 Телефон", 123, "cph", "m")
        InlineKeyboardButton(text="📋 Телефон", callback_data="m:copy:cph:123")
    """
    callback_data = f"{bot_prefix}:copy:{data_type}:{order_id}"
    return InlineKeyboardButton(text=text, callback_data=callback_data)


def format_copy_message(data_type: str, data: str) -> str:
    """
    Форматирует сообщение с данными для копирования.
    
    Использует <code> теги для удобного копирования в Telegram.
    
    Args:
        data_type: Тип данных (cph, addr, mph)
        data: Данные для отображения
    
    Returns:
        HTML-форматированное сообщение
    """
    type_labels = {
        "cph": "📞 Телефон клиента",
        "mph": "📞 Телефон мастера",
        "addr": "📍 Адрес",
    }
    label = type_labels.get(data_type, "📋 Данные")
    
    # Используем <code> для моноширинного шрифта - легче копировать
    return f"<b>{label}:</b>\n\n<code>{data}</code>\n\n<i>Нажмите на текст чтобы скопировать</i>"
