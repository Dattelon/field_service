# field_service/bots/admin_bot/handlers/logs.py
"""Обработчики для просмотра и управления логами."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from field_service.services import live_log

from ...core.dto import StaffRole, StaffUser
from ...core.filters import StaffRoleFilter
from ...ui.keyboards import logs_menu_keyboard
from ..common.helpers import LOG_ENTRIES_LIMIT, _format_log_entries


router = Router(name="admin_logs")


@router.callback_query(
    F.data == "adm:l",
    StaffRoleFilter({StaffRole.GLOBAL_ADMIN, StaffRole.CITY_ADMIN, StaffRole.LOGIST}),
)
async def cb_logs_menu(cq: CallbackQuery, staff: StaffUser) -> None:
    """Показать логи."""
    entries = live_log.snapshot(LOG_ENTRIES_LIMIT)
    text = _format_log_entries(entries)
    keyboard = logs_menu_keyboard(can_clear=staff.role is StaffRole.GLOBAL_ADMIN)
    await cq.message.edit_text(
        text,
        reply_markup=keyboard,
        disable_web_page_preview=True,
    )
    await cq.answer()


@router.callback_query(
    F.data == "adm:l:refresh",
    StaffRoleFilter({StaffRole.GLOBAL_ADMIN, StaffRole.CITY_ADMIN, StaffRole.LOGIST}),
)
async def cb_logs_refresh(cq: CallbackQuery, staff: StaffUser) -> None:
    """Обновить логи."""
    entries = live_log.snapshot(LOG_ENTRIES_LIMIT)
    text = _format_log_entries(entries)
    keyboard = logs_menu_keyboard(can_clear=staff.role is StaffRole.GLOBAL_ADMIN)
    await cq.message.edit_text(
        text,
        reply_markup=keyboard,
        disable_web_page_preview=True,
    )
    await cq.answer()


@router.callback_query(
    F.data == "adm:l:clear",
    StaffRoleFilter({StaffRole.GLOBAL_ADMIN}),
)
async def cb_logs_clear(cq: CallbackQuery, staff: StaffUser) -> None:
    """Очистить логи (только GLOBAL_ADMIN)."""
    live_log.clear()
    entries = live_log.snapshot(LOG_ENTRIES_LIMIT)
    text = _format_log_entries(entries)
    keyboard = logs_menu_keyboard(can_clear=True)
    await cq.message.edit_text(
        text,
        reply_markup=keyboard,
        disable_web_page_preview=True,
    )
    await cq.answer("Логи очищены")


__all__ = ["router"]
