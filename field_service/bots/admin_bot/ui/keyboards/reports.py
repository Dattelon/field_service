"""Admin bot keyboards."""
from __future__ import annotations

from typing import Mapping, Sequence, Optional

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from ...core.dto import CommissionDetail, StaffUser


def reports_menu_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📦 Заказы (CSV/XLSX)", callback_data="adm:r:o")
    kb.button(text="💸 Комиссии (CSV/XLSX)", callback_data="adm:r:c")
    kb.button(text="👥 Реферальные (CSV/XLSX)", callback_data="adm:r:rr")
    kb.button(text="⬅️ В меню", callback_data="adm:menu")
    kb.adjust(1)
    return kb.as_markup()




def reports_periods_keyboard() -> InlineKeyboardMarkup:
    """Quick period choices for reports export."""
    kb = InlineKeyboardBuilder()
    kb.button(text="Сегодня", callback_data="adm:r:pd:today")
    kb.button(text="Вчера", callback_data="adm:r:pd:yesterday")
    kb.button(text="Последние 7 дней", callback_data="adm:r:pd:last7")
    kb.button(text="Текущий месяц", callback_data="adm:r:pd:this_month")
    kb.button(text="Прошлый месяц", callback_data="adm:r:pd:prev_month")
    kb.button(text="Выбрать вручную", callback_data="adm:r:pd:custom")
    kb.button(text="⬅️ Назад", callback_data="adm:r")
    kb.adjust(2, 2, 2, 1, 1)
    return kb.as_markup()



