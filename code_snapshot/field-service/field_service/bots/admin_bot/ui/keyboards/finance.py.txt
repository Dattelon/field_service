"""Admin bot keyboards."""
from __future__ import annotations

from typing import Mapping, Sequence, Optional

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from ...core.dto import CommissionDetail, StaffUser, StaffRole


def finance_menu(staff: StaffUser) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="  ", callback_data="adm:f:aw:1")
    kb.button(text=" ", callback_data="adm:f:pd:1")
    kb.button(text=" ", callback_data="adm:f:ov:1")
    kb.button(text="  ", callback_data="adm:f:grouped:aw")  # P1-15: 
    if staff.role is StaffRole.GLOBAL_ADMIN:
        kb.button(text="  ", callback_data="adm:f:bulk")  # P2-11:  
        kb.button(text="  ", callback_data="adm:f:set")
    kb.button(text="  ", callback_data="adm:menu")
    if staff.role != StaffRole.GLOBAL_ADMIN:
        kb.adjust(2, 2, 1)
    else:
        kb.adjust(2, 2, 2, 1)
    return kb.as_markup()


def finance_grouped_keyboard(segment: str, groups: dict[str, int]) -> InlineKeyboardMarkup:
    """
    P1-15:     .
    
    Args:
        segment: 'aw', 'pd', 'ov'
        groups: dict      
    """
    kb = InlineKeyboardBuilder()
    
    #   
    period_labels = {
        'today': f"  ({groups.get('today', 0)})",
        'yesterday': f"  ({groups.get('yesterday', 0)})",
        'week': f"   ({groups.get('week', 0)})",
        'month': f"   ({groups.get('month', 0)})",
        'older': f"  ({groups.get('older', 0)})",
    }
    
    #     
    for period in ['today', 'yesterday', 'week', 'month', 'older']:
        count = groups.get(period, 0)
        if count > 0:
            kb.button(
                text=period_labels[period],
                callback_data=f"adm:f:grp:{segment}:{period}:1"
            )
    
    #  
    kb.button(text=" ", callback_data="adm:f")
    kb.adjust(1)
    return kb.as_markup()


def finance_group_period_keyboard(segment: str, period: str, page: int, has_next: bool) -> InlineKeyboardMarkup:
    """
    P1-15:      .
    
    Args:
        segment: 'aw', 'pd', 'ov'
        period: 'today', 'yesterday', 'week', 'month', 'older'
        page:  
        has_next:    
    """
    kb = InlineKeyboardBuilder()
    
    #   
    if page > 1:
        kb.button(text=" ", callback_data=f"adm:f:grp:{segment}:{period}:{page - 1}")
    if has_next:
        kb.button(text=" ", callback_data=f"adm:f:grp:{segment}:{period}:{page + 1}")
    
    #    
    kb.button(text="  ", callback_data=f"adm:f:grouped:{segment}")
    kb.adjust(2, 1)
    return kb.as_markup()




def finance_segment_keyboard(seg: str, page: int, has_next: bool, grouped: bool = False) -> InlineKeyboardMarkup:
    """P1-15:      ."""
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    kb = InlineKeyboardBuilder()
    
    #     
    if not grouped:
        if page > 1:
            kb.button(text=" ", callback_data=f"adm:f:{seg}:{page - 1}")
        if has_next:
            kb.button(text=" ", callback_data=f"adm:f:{seg}:{page + 1}")
    
    #   
    if grouped:
        kb.button(text="  ", callback_data=f"adm:f:{seg}:1")
    else:
        kb.button(text="  ", callback_data=f"adm:f:{seg}:grp")
    
    kb.button(text=" ", callback_data="adm:f")
    kb.adjust(2, 1) if not grouped else kb.adjust(1, 1)
    return kb.as_markup()




def finance_card_actions(detail: CommissionDetail, segment: str, page: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="  ", callback_data=f"adm:f:cm:open:{detail.id}")

    status = (detail.status or "").upper()
    if status in {"WAIT_PAY", "REPORTED", "OVERDUE"}:
        kb.button(text=" ", callback_data=f"adm:f:cm:ok:{detail.id}")
    if status in {"WAIT_PAY", "REPORTED"}:
        kb.button(text=" ", callback_data=f"adm:f:cm:rej:{detail.id}")
    if detail.master_id is not None:
        kb.button(text=" ", callback_data=f"adm:f:cm:blk:{detail.id}")
    kb.button(text=" ", callback_data=f"adm:f:{segment}:{page}")
    kb.adjust(1)
    return kb.as_markup()




def finance_reject_cancel_keyboard(commission_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=" ", callback_data=f"adm:f:cm:card:{commission_id}")
    return kb.as_markup()




def owner_pay_actions_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=" ", callback_data="adm:f:set:edit")
    kb.button(text=" ", callback_data="adm:f")
    kb.adjust(1)
    return kb.as_markup()




def owner_pay_edit_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    field_labels = [
        ("methods", "  "),
        ("card_number", "  "),
        ("card_holder", "  "),
        ("card_bank", "  "),
        ("sbp_phone", "  "),
        ("sbp_bank", "  "),
        ("sbp_qr_file_id", " QR- "),
        ("other_text", " "),
        ("comment_template", "  "),
    ]
    for field, label in field_labels:
        kb.button(text=label, callback_data=f"adm:f:set:field:{field}")
    kb.adjust(2)
    kb.button(text=" ", callback_data="adm:f:set")
    return kb.as_markup()




