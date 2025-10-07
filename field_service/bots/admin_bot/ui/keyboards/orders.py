"""Admin bot keyboards."""
from __future__ import annotations

from typing import Mapping, Sequence, Optional

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from ...core.dto import (
    CommissionDetail,
    MasterBrief,
    OrderAttachment,
    OrderListItem,
    StaffUser,
)
from ...ui.texts import master_brief_line


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
    is_deferred: bool = False,  # ⚠️ Новый параметр
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
    
    # ⚠️ Кнопка активации DEFERRED заказа
    if is_deferred:
        actions.button(text='! Перевести в поиск мастера', callback_data=f'adm:q:activate:{order_id}')
    
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


def queue_return_confirm_keyboard(order_id: int) -> InlineKeyboardMarkup:
    """P0-3: Клавиатура подтверждения возврата заказа в поиск."""
    kb = InlineKeyboardBuilder()
    kb.button(text='✅ Да, вернуть в поиск', callback_data=f'adm:q:ret:confirm:{order_id}')
    kb.button(text='❌ Отменить', callback_data=f'adm:q:card:{order_id}')
    kb.adjust(1)
    return kb.as_markup()




def assign_menu_keyboard(order_id: int, *, allow_auto: bool = True) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if allow_auto:
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
        nav.button(text="◀️ Назад", callback_data=f"adm:new:city_page:{page - 1}")
    if page < total_pages:
        nav.button(text="▶️ Далее", callback_data=f"adm:new:city_page:{page + 1}")
    nav.button(text="🔍 Поиск", callback_data="adm:new:city_search")
    nav.button(text="✖️ Отменить", callback_data="adm:new:cancel")
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
    if districts:
        kb.adjust(1)
    kb.button(text="🚫 Без района", callback_data="adm:new:district:none")
    nav = InlineKeyboardBuilder()
    if page > 1:
        nav.button(text="◀️ Назад", callback_data=f"adm:new:district_page:{page - 1}")
    if has_next:
        nav.button(text="▶️ Далее", callback_data=f"adm:new:district_page:{page + 1}")
    nav.button(text="⬅️ Назад", callback_data="adm:new:city_back")
    kb.attach(nav)
    return kb.as_markup()




def new_order_street_mode_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🔍 Найти улицу", callback_data="adm:new:street:search")
    kb.button(text="✏️ Ввести вручную", callback_data="adm:new:street:manual")
    kb.button(text="🚫 Без улицы", callback_data="adm:new:street:none")
    kb.button(text="⬅️ Назад", callback_data="adm:new:district_back")
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






