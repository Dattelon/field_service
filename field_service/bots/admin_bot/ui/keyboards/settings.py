"""Admin bot keyboards."""
from __future__ import annotations

from typing import Mapping, Sequence, Optional

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from ...core.dto import CommissionDetail, StaffUser


def settings_menu_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🕙 Рабочий день", callback_data="adm:s:group:workday")
    kb.button(text="⚖️ Распределение", callback_data="adm:s:group:distribution")
    kb.button(text="⛔️ Лимиты", callback_data="adm:s:group:limits")
    kb.button(text="🆘 Поддержка", callback_data="adm:s:group:support")
    kb.button(text="🗺 Гео", callback_data="adm:s:group:geo")
    kb.button(text="📣 Каналы", callback_data="adm:s:group:channels")
    kb.adjust(2, 2, 2)
    kb.button(text="  ", callback_data="adm:menu")
    return kb.as_markup()




def settings_group_keyboard(
    group_key: str, field_buttons: Sequence[tuple[str, str]]
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for field_key, label in field_buttons:
        kb.button(text=f"{label}", callback_data=f"adm:s:edit:{group_key}:{field_key}")
    kb.adjust(1)
    kb.button(text="⬅️ Назад", callback_data="adm:s")
    return kb.as_markup()




def logs_menu_keyboard(*, can_clear: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🔄 Обновить", callback_data="adm:l:refresh")
    if can_clear:
        kb.button(text="🧹 Очистить", callback_data="adm:l:clear")
        kb.adjust(2)
    else:
        kb.adjust(1)
    kb.button(text="⬅️ В меню", callback_data="adm:menu")
    return kb.as_markup()


__all__ = [
    "back_to_menu",
    "finance_card_actions",
    "finance_menu",
    "finance_reject_cancel_keyboard",
    "finance_segment_keyboard",
    "main_menu",
    "orders_menu",
    "reports_menu_keyboard",
    "reports_periods_keyboard",
    "manual_candidates_keyboard",
    "manual_confirm_keyboard",
    "new_order_attachments_keyboard",
    "new_order_city_keyboard",
    "new_order_confirm_keyboard",
    "new_order_district_keyboard",
    "new_order_slot_keyboard",
    "new_order_street_keyboard",
    "new_order_street_manual_keyboard",
    "new_order_street_search_keyboard",
    "new_order_street_mode_keyboard",
    "order_card_keyboard",
    "reports_menu_keyboard",
    "queue_list_keyboard",
    "settings_menu_keyboard",
    "settings_group_keyboard",
    "logs_menu_keyboard",
]



