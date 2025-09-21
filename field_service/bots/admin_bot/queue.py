from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from .dto import StaffRole, StaffUser
from .filters import StaffRoleFilter
from .keyboards import main_menu

queue_router = Router(name="admin_queue")

_ALLOWED_ROLES = {StaffRole.GLOBAL_ADMIN, StaffRole.CITY_ADMIN, StaffRole.LOGIST}


def _queue_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Фильтры", callback_data="adm:q:flt")
    builder.button(text="Список", callback_data="adm:q:list:1")
    builder.button(text="Назад", callback_data="adm:q:bk")
    builder.adjust(1)
    return builder.as_markup()


def _back_to_queue_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Назад", callback_data="adm:q")
    builder.adjust(1)
    return builder.as_markup()


@queue_router.callback_query(
    F.data == "adm:q",
    StaffRoleFilter(_ALLOWED_ROLES),
)
async def cb_queue_menu(cq: CallbackQuery, staff: StaffUser) -> None:
    keyboard = _queue_menu_keyboard()
    await cq.message.edit_text("Очередь (WIP)", reply_markup=keyboard)
    await cq.answer()


@queue_router.callback_query(
    F.data == "adm:q:flt",
    StaffRoleFilter(_ALLOWED_ROLES),
)
async def cb_queue_filters(cq: CallbackQuery, staff: StaffUser) -> None:
    keyboard = _back_to_queue_keyboard()
    await cq.message.edit_text("Фильтры (WIP)", reply_markup=keyboard)
    await cq.answer()


@queue_router.callback_query(
    F.data.startswith("adm:q:list:"),
    StaffRoleFilter(_ALLOWED_ROLES),
)
async def cb_queue_list(cq: CallbackQuery, staff: StaffUser) -> None:
    try:
        page = int(cq.data.split(":")[3])
    except (IndexError, ValueError):
        await cq.answer("Некорректная страница", show_alert=True)
        return
    keyboard = _back_to_queue_keyboard()
    await cq.message.edit_text(f"Список (WIP), page={page}", reply_markup=keyboard)
    await cq.answer()


@queue_router.callback_query(
    F.data.startswith("adm:q:card:"),
    StaffRoleFilter(_ALLOWED_ROLES),
)
async def cb_queue_card(cq: CallbackQuery, staff: StaffUser) -> None:
    try:
        order_id = int(cq.data.split(":")[3])
    except (IndexError, ValueError):
        await cq.answer("Некорректная заявка", show_alert=True)
        return
    keyboard = _back_to_queue_keyboard()
    await cq.message.edit_text(f"Карточка (WIP), id={order_id}", reply_markup=keyboard)
    await cq.answer()


@queue_router.callback_query(
    F.data == "adm:q:bk",
    StaffRoleFilter(_ALLOWED_ROLES),
)
async def cb_queue_back(cq: CallbackQuery, staff: StaffUser) -> None:
    await cq.message.edit_text("Главное меню", reply_markup=main_menu(staff))
    await cq.answer()
