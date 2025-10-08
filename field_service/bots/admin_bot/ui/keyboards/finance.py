"""Admin bot keyboards."""
from __future__ import annotations

from typing import Mapping, Sequence, Optional

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from ...core.dto import CommissionDetail, StaffRole, StaffUser


def finance_menu(staff: StaffUser) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="⏳ Ожидают оплаты", callback_data="adm:f:aw:1")
    kb.button(text="✅ Оплаченные", callback_data="adm:f:pd:1")
    kb.button(text="⏰ Просроченные", callback_data="adm:f:ov:1")
    if staff.role is StaffRole.GLOBAL_ADMIN:
        kb.button(text="⚡ Одобрить все", callback_data="adm:f:bulk")  # P2-11: Массовое одобрение
        kb.button(text="💼 Реквизиты владельца", callback_data="adm:f:set")
    kb.button(text="⬅️ В меню", callback_data="adm:menu")
    kb.adjust(2, 2) if staff.role != StaffRole.GLOBAL_ADMIN else kb.adjust(2, 2, 1, 1)
    return kb.as_markup()




def finance_segment_keyboard(seg: str, page: int, has_next: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if page > 1:
        kb.button(text="◀️ Назад", callback_data=f"adm:f:{seg}:{page - 1}")
    if has_next:
        kb.button(text="▶️ Далее", callback_data=f"adm:f:{seg}:{page + 1}")
    kb.button(text="⬅️ Назад", callback_data="adm:f")
    kb.adjust(2)
    return kb.as_markup()




def finance_card_actions(detail: CommissionDetail, segment: str, page: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🧾 Открыть чек", callback_data=f"adm:f:cm:open:{detail.id}")

    status = (detail.status or "").upper()
    if status in {"WAIT_PAY", "REPORTED", "OVERDUE"}:
        kb.button(text="✅ Подтвердить", callback_data=f"adm:f:cm:ok:{detail.id}")
    if status in {"WAIT_PAY", "REPORTED"}:
        kb.button(text="❌ Отклонить", callback_data=f"adm:f:cm:rej:{detail.id}")
    if detail.master_id is not None:
        kb.button(text="🚫 Заблокировать", callback_data=f"adm:f:cm:blk:{detail.id}")
    kb.button(text="⬅️ Назад", callback_data=f"adm:f:{segment}:{page}")
    kb.adjust(1)
    return kb.as_markup()




def finance_reject_cancel_keyboard(commission_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ Назад", callback_data=f"adm:f:cm:card:{commission_id}")
    return kb.as_markup()




def owner_pay_actions_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=" ", callback_data="adm:f:set:edit")
    kb.button(text="  ", callback_data="adm:f:set:bc")
    kb.button(text=" ", callback_data="adm:f")
    kb.adjust(2, 1)
    return kb.as_markup()




def owner_pay_edit_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    field_labels = [
        ("methods", " "),
        ("card_number", " "),
        ("card_holder", " "),
        ("card_bank", " "),
        ("sbp_phone", " "),
        ("sbp_bank", " "),
        ("sbp_qr_file_id", "QR-"),
        ("other_text", ""),
        ("comment_template", " "),
    ]
    for field, label in field_labels:
        kb.button(text=label, callback_data=f"adm:f:set:field:{field}")
    kb.adjust(2)
    kb.button(text=" ", callback_data="adm:f:set")
    return kb.as_markup()




