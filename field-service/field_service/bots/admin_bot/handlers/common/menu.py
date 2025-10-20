# field_service/bots/admin_bot/handlers/menu.py
"""Обработчики главного меню и базовой навигации."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.exceptions import TelegramBadRequest

from field_service.bots.common import safe_delete_and_send
from ...core.dto import StaffRole, StaffUser
from ...core.filters import StaffRoleFilter
from ...ui.keyboards import main_menu, finance_menu
from .helpers import _staff_service, _resolve_city_names


router = Router(name="admin_menu")


async def safe_answer(cq: CallbackQuery, text: str | None = None, show_alert: bool = False) -> None:
    """Safely answer callback query, ignoring 'query is too old' errors."""
    try:
        await cq.answer(text=text, show_alert=show_alert)
    except TelegramBadRequest as exc:
        if "query is too old" not in str(exc).lower():
            raise  # Re-raise if it's a different error


# Константы для отображения ролей
STAFF_ROLE_LABELS = {
    StaffRole.GLOBAL_ADMIN: "Глобальный администратор",
    StaffRole.CITY_ADMIN: "Администратор города",
    StaffRole.LOGIST: "Логист",
}


@router.message(CommandStart(), StaffRoleFilter({StaffRole.GLOBAL_ADMIN, StaffRole.CITY_ADMIN, StaffRole.LOGIST}))
async def admin_start(message: Message, staff: StaffUser) -> None:
    """Стартовое сообщение для авторизованных админов."""
    await message.answer("Добро пожаловать в Field Service. Выберите раздел:", reply_markup=main_menu(staff))


@router.message(CommandStart())
async def not_allowed_start(message: Message, state: FSMContext) -> None:
    """Стартовое сообщение для неавторизованных пользователей."""
    await state.clear()
    
    user = message.from_user
    if not user:
        await message.answer("❌ Не удалось получить информацию о пользователе.")
        return
    
    staff_service = _staff_service(message.bot)
    
    # Пытаемся найти по tg_id или username
    staff = await staff_service.get_by_tg_id_or_username(
        tg_id=user.id,
        username=user.username,
        update_tg_id=True
    )
    
    if staff and staff.is_active:
        # Доступ есть - показываем меню
        await message.answer(
            "✅ Добро пожаловать в Field Service.\n\nВыберите раздел:",
            reply_markup=main_menu(staff)
        )
        return
    
    # Доступа нет
    await message.answer(
        "❌ У вас нет доступа к этому боту.\n\n"
        "Обратитесь к администратору для получения доступа."
    )


@router.callback_query(
    F.data == "adm:menu",
    StaffRoleFilter({StaffRole.GLOBAL_ADMIN, StaffRole.CITY_ADMIN, StaffRole.LOGIST}),
)
async def cb_menu(cq: CallbackQuery, staff: StaffUser, state: FSMContext) -> None:
    """Вернуться в главное меню - удаляет старое сообщение и показывает новое."""
    await state.clear()
    await safe_delete_and_send(cq, "Главное меню:", reply_markup=main_menu(staff))
    await safe_answer(cq)


@router.callback_query(
    F.data == "adm:staff:menu",
    StaffRoleFilter({StaffRole.CITY_ADMIN, StaffRole.LOGIST}),
)
async def cb_staff_menu_denied(cq: CallbackQuery, staff: StaffUser) -> None:
    """Отказ в доступе к меню персонала для не-глобальных админов."""
    if cq.message is not None:
        await cq.message.edit_text(
            "Недостаточно прав. Вернитесь в главное меню:",
            reply_markup=main_menu(staff),
        )
    await safe_answer(cq, "Недостаточно прав", show_alert=True)


@router.callback_query(
    F.data == "adm:f",
    StaffRoleFilter({StaffRole.GLOBAL_ADMIN, StaffRole.CITY_ADMIN}),
)
async def cb_finance_root(cq: CallbackQuery, staff: StaffUser, state: FSMContext) -> None:
    """Открыть меню финансов."""
    await state.clear()
    await cq.message.edit_text("Финансы:", reply_markup=finance_menu(staff))
    await safe_answer(cq)


__all__ = [
    "router",
    "STAFF_ROLE_LABELS",
]
