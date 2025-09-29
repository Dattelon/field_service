from __future__ import annotations

from typing import Sequence

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from .dto import (
    CommissionDetail,
    CommissionListItem,
    MasterBrief,
    MasterDetail,
    MasterListItem,
    OrderAttachment,
    OrderListItem,
    StaffRole,
    StaffUser,
)
from .texts import master_brief_line




def main_menu(staff: StaffUser) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📋 Очередь", callback_data="adm:q")
    kb.button(text="➕ Новый заказ", callback_data="adm:new")
    kb.button(text="👷 Мастера", callback_data="adm:m")
    kb.button(text="🛠 Модерация", callback_data="adm:mod")
    kb.button(text="💰 Финансы", callback_data="adm:f")
    kb.button(text="📊 Отчеты", callback_data="adm:r")
    kb.button(text="⚙️ Настройки", callback_data="adm:s")
    if staff.role is StaffRole.GLOBAL_ADMIN:
        kb.button(text="👤 Сотрудники/Доступ", callback_data="adm:staff:menu")
    kb.button(text="🧾 Логи", callback_data="adm:l")
    kb.adjust(2, 2, 2, 2, 1)
    return kb.as_markup()


def back_to_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ В меню", callback_data="adm:menu")
    return kb.as_markup()


def queue_list_keyboard(
    items: Sequence[OrderListItem], *, page: int, has_next: bool
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for order in items:
        kb.button(text=f"#{order.id}", callback_data=f"adm:q:card:{order.id}")
    if items:
        kb.adjust(1)
    nav = InlineKeyboardBuilder()
    nav_count = 0
    if page > 1:
        nav.button(text="◀️ Назад", callback_data=f"adm:q:list:{page - 1}")
        nav_count += 1
    if has_next:
        nav.button(text="▶️ Далее", callback_data=f"adm:q:list:{page + 1}")
        nav_count += 1
    if nav_count:
        nav.adjust(nav_count)
        kb.attach(nav)
    controls = InlineKeyboardBuilder()
    controls.button(text="🔎 Фильтры", callback_data="adm:q:flt")
    controls.button(text="⬅️ В меню", callback_data="adm:menu")
    controls.adjust(2)
    kb.attach(controls)
    return kb.as_markup()


def order_card_keyboard(
    order_id: int,
    attachments: Sequence[OrderAttachment] = (),
    *,
    allow_return: bool = True,
    allow_cancel: bool = True,
    show_guarantee: bool = False,
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for attachment in attachments:
        title = attachment.file_name or f' #{attachment.id}'
        kb.button(
            text=f'📎 {title}',
            callback_data=f'adm:q:att:{order_id}:{attachment.id}',
        )
    if attachments:
        kb.adjust(1)
    actions = InlineKeyboardBuilder()
    if show_guarantee:
        actions.button(text='🛡 Гарантия', callback_data=f'adm:q:gar:{order_id}')
    actions.button(text='👥 Назначить', callback_data=f'adm:q:as:{order_id}')
    if allow_return:
        actions.button(text='⬅️ Назад', callback_data=f'adm:q:ret:{order_id}')
    if allow_cancel:
        actions.button(text='✖️ Отменить', callback_data=f'adm:q:cnl:{order_id}')
    actions.button(text='📋 К списку', callback_data='adm:q:list:1')
    actions.adjust(1)
    kb.attach(actions)
    return kb.as_markup()









def queue_cancel_keyboard(order_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text='⬅️ Назад', callback_data=f'adm:q:cnl:bk:{order_id}')
    return kb.as_markup()


def assign_menu_keyboard(order_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text='⚡️ Автораспределение', callback_data=f'adm:q:as:auto:{order_id}')
    kb.button(text='👤 Выбрать мастера', callback_data=f'adm:q:as:man:{order_id}:1')
    kb.button(text='⬅️ Назад', callback_data=f'adm:q:card:{order_id}')
    kb.adjust(1)
    return kb.as_markup()

def manual_candidates_keyboard(
    order_id: int,
    masters: Sequence[MasterBrief],
    *,
    page: int,
    has_next: bool,
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for master in masters:
        kb.button(
            text=master_brief_line(master),
            callback_data=f"adm:q:as:check:{order_id}:{page}:{master.id}"
        )
    kb.adjust(1)
    nav = InlineKeyboardBuilder()
    if page > 1:
        nav.button(text="◀️ Назад", callback_data=f"adm:q:as:man:{order_id}:{page - 1}")
    if has_next:
        nav.button(text="▶️ Далее", callback_data=f"adm:q:as:man:{order_id}:{page + 1}")
    nav.button(text="⬅️ Назад", callback_data=f"adm:q:card:{order_id}")
    kb.attach(nav)
    return kb.as_markup()


def manual_confirm_keyboard(order_id: int, master_id: int, page: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Назначить", callback_data=f"adm:q:as:pick:{order_id}:{page}:{master_id}")
    kb.button(text="⬅️ Назад", callback_data=f"adm:q:as:man:{order_id}:{page}")
    return kb.as_markup()


def finance_menu(staff: StaffUser) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="⏳ Ожидают оплаты", callback_data="adm:f:aw:1")
    kb.button(text="✅ Оплаченные", callback_data="adm:f:pd:1")
    kb.button(text="⏰ Просроченные", callback_data="adm:f:ov:1")
    if staff.role is StaffRole.GLOBAL_ADMIN:
        kb.button(text="💼 Реквизиты владельца", callback_data="adm:f:set")
    kb.button(text="⬅️ В меню", callback_data="adm:menu")
    kb.adjust(2, 2)
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


def new_order_city_keyboard(
    city_buttons: Sequence[tuple[int, str]],
    *,
    page: int,
    total_pages: int,
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for city_id, name in city_buttons:
        kb.button(text=name, callback_data=f"adm:new:city:{city_id}")
    kb.adjust(2)
    nav = InlineKeyboardBuilder()
    if page > 1:
        nav.button(text="", callback_data=f"adm:new:city_page:{page - 1}")
    if page < total_pages:
        nav.button(text="", callback_data=f"adm:new:city_page:{page + 1}")
    nav.button(text=" ", callback_data="adm:new:city_search")
    nav.button(text=" ", callback_data="adm:new:cancel")
    kb.attach(nav)
    return kb.as_markup()


def new_order_district_keyboard(
    districts: Sequence[tuple[int, str]],
    *,
    page: int,
    has_next: bool,
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for district_id, name in districts:
        kb.button(text=name, callback_data=f"adm:new:district:{district_id}")
    kb.button(text="   ", callback_data="adm:new:district:none")
    nav = InlineKeyboardBuilder()
    if page > 1:
        nav.button(text="", callback_data=f"adm:new:district_page:{page - 1}")
    if has_next:
        nav.button(text="", callback_data=f"adm:new:district_page:{page + 1}")
    nav.button(text=" ", callback_data="adm:new:city_back")
    kb.attach(nav)
    return kb.as_markup()


def new_order_street_mode_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="  ", callback_data="adm:new:street:search")
    kb.button(text="  ", callback_data="adm:new:street:manual")
    kb.button(text="   ", callback_data="adm:new:street:none")
    kb.button(text=" ", callback_data="adm:new:district_back")
    kb.adjust(1)
    return kb.as_markup()


def new_order_street_keyboard(streets: Sequence[tuple[int, str]]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for street_id, label in streets:
        kb.button(text=label, callback_data=f"adm:new:street:{street_id}")
    kb.button(text="🔍 Искать снова", callback_data="adm:new:street:search_again")
    kb.button(text="⬅️ Назад", callback_data="adm:new:street:back")
    kb.adjust(1)
    return kb.as_markup()


def new_order_street_manual_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ Назад", callback_data="adm:new:street:manual_back")
    return kb.as_markup()


def new_order_street_search_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ Назад", callback_data="adm:new:street:search_back")
    kb.button(text="✖️ Отменить", callback_data="adm:new:cancel")
    kb.adjust(1)
    return kb.as_markup()


def new_order_attachments_keyboard(has_any: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📎 Добавить", callback_data="adm:new:att:add")
    kb.button(text="✅ Готово", callback_data="adm:new:att:done")
    if has_any:
        kb.button(text="🧹 Очистить", callback_data="adm:new:att:clear")
    kb.adjust(1)
    return kb.as_markup()


def new_order_slot_keyboard(options: Sequence[tuple[str, str]]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for key, label in options:
        kb.button(text=label, callback_data=f"adm:new:slot:{key}")
    kb.adjust(1)
    kb.button(text="✖️ Отменить", callback_data="adm:new:cancel")
    return kb.as_markup()


def new_order_asap_late_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Ок", callback_data="adm:new:slot:lateok")
    kb.button(text="🔁 Перезапланировать", callback_data="adm:new:slot:reslot")
    kb.adjust(1)
    return kb.as_markup()



def new_order_confirm_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Подтвердить", callback_data="adm:new:confirm")
    kb.button(text="⬅️ Назад", callback_data="adm:new:cancel")
    return kb.as_markup()




def reports_menu_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📦 Заказы (CSV/XLSX)", callback_data="adm:r:o")
    kb.button(text="💸 Комиссии (CSV/XLSX)", callback_data="adm:r:c")
    kb.button(text="👥 Реферальные (CSV/XLSX)", callback_data="adm:r:rr")
    kb.button(text="⬅️ В меню", callback_data="adm:menu")
    kb.adjust(1)
    return kb.as_markup()

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
