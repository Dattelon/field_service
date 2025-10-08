"""
Модуль управления персоналом админ-бота.

Современный UI для добавления и управления персоналом
без использования системы access-кодов.

Функционал:
- Добавление персонала по Telegram ID или @username
- Выбор роли (Global Admin, City Admin, Logist)
- Привязка к городам
- Просмотр списков персонала
- Редактирование прав доступа
- Блокировка/активация персонала
"""

from __future__ import annotations

import logging
from typing import Any, Optional, Sequence

from aiogram import Bot, F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from ...core.dto import CityRef, StaffRole, StaffUser
from ...core.filters import StaffRoleFilter
from ...core.states import StaffAddFSM, StaffEditFSM
from ...utils.helpers import get_service
from ..common.helpers import _staff_service, _resolve_city_names
from ..common.menu import STAFF_ROLE_LABELS

logger = logging.getLogger(__name__)

router = Router(name="staff_management")


# ===========================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ===========================================

async def safe_edit_text(
    message,
    text: str,
    reply_markup=None,
    **kwargs
) -> bool:
    """Безопасное редактирование сообщения, игнорирует ошибку 'message is not modified'."""
    try:
        await message.edit_text(text, reply_markup=reply_markup, **kwargs)
        return True
    except Exception:
        return False

# Константы
PAGE_SIZE = 10
ADMIN_ROLES = {StaffRole.GLOBAL_ADMIN}
MANAGE_ROLES = {StaffRole.GLOBAL_ADMIN, StaffRole.CITY_ADMIN}

# Эмодзи для UI
EMOJI = {
    "add": "➕",
    "list": "📋",
    "edit": "✏️",
    "delete": "🗑",
    "active": "✅",
    "inactive": "❌",
    "back": "⬅️",
    "confirm": "✔️",
    "cancel": "🚫",
    "global_admin": "👑",
    "city_admin": "🏛",
    "logist": "📦",
}

# ============================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================

def _orders_service(bot) -> Any:
    return get_service(bot, "orders_service")


def _format_staff_info(member, city_names: list[str]) -> str:
    """Форматирование информации о сотруднике."""
    lines = []
    
    # Роль с эмодзи
    role_emoji = {
        StaffRole.GLOBAL_ADMIN: EMOJI["global_admin"],
        StaffRole.CITY_ADMIN: EMOJI["city_admin"],
        StaffRole.LOGIST: EMOJI["logist"],
    }.get(member.role, "👤")
    
    role_label = STAFF_ROLE_LABELS.get(member.role, member.role.value)
    lines.append(f"<b>{role_emoji} {role_label}</b>")
    lines.append("")
    
    # Основная информация
    lines.append(f"🆔 ID: <code>{member.tg_id}</code>")
    if member.username:
        lines.append(f"📱 @{member.username}")
    lines.append(f"👤 {member.full_name or 'Не указано'}")
    if member.phone:
        lines.append(f"📞 {member.phone}")
    
    # Города
    if city_names:
        lines.append(f"🏙 Города: {', '.join(city_names)}")
    else:
        lines.append("🏙 Города: Все")
    
    # Статус
    status = f"{EMOJI['active']} Активен" if member.is_active else f"{EMOJI['inactive']} Заблокирован"
    lines.append(f"📊 Статус: {status}")
    
    # Даты
    if member.created_at:
        created = member.created_at.strftime("%d.%m.%Y %H:%M")
        lines.append(f"📅 Добавлен: {created}")
    
    return "\n".join(lines)


async def _get_cities_list(bot) -> list[CityRef]:
    """Получить список всех городов."""
    orders_service = _orders_service(bot)
    cities = await orders_service.list_cities()
    return sorted(cities, key=lambda c: c.name)


def _build_city_keyboard(
    cities: Sequence[CityRef],
    selected: set[int],
    prefix: str,
    show_done: bool = True,
) -> InlineKeyboardBuilder:
    """Построить клавиатуру выбора городов."""
    kb = InlineKeyboardBuilder()
    
    for city in cities:
        is_selected = city.id in selected
        check = "✅ " if is_selected else ""
        kb.button(
            text=f"{check}{city.name}",
            callback_data=f"{prefix}:toggle:{city.id}"
        )
    
    kb.adjust(2)
    
    # Кнопки управления
    controls = InlineKeyboardBuilder()
    
    if selected:
        controls.button(text="❌ Сбросить все", callback_data=f"{prefix}:clear")
    else:
        controls.button(text="✅ Выбрать все", callback_data=f"{prefix}:all")
    
    if show_done:
        controls.button(text=f"{EMOJI['confirm']} Готово", callback_data=f"{prefix}:done")
    
    controls.button(text=f"{EMOJI['back']} Назад", callback_data=f"{prefix}:cancel")
    controls.adjust(2)
    
    kb.attach(controls)
    return kb


def _build_role_keyboard(prefix: str) -> InlineKeyboardBuilder:
    """Построить клавиатуру выбора роли."""
    kb = InlineKeyboardBuilder()
    
    kb.button(
        text=f"{EMOJI['global_admin']} Global Admin",
        callback_data=f"{prefix}:role:GLOBAL_ADMIN"
    )
    kb.button(
        text=f"{EMOJI['city_admin']} City Admin",
        callback_data=f"{prefix}:role:CITY_ADMIN"
    )
    kb.button(
        text=f"{EMOJI['logist']} Logist",
        callback_data=f"{prefix}:role:LOGIST"
    )
    kb.button(
        text=f"{EMOJI['back']} Отмена",
        callback_data="adm:staff:menu"
    )
    
    kb.adjust(1)
    return kb


# ============================================
# ГЛАВНОЕ МЕНЮ УПРАВЛЕНИЯ ПЕРСОНАЛОМ
# ============================================

@router.callback_query(
    F.data == "adm:staff:menu",
    StaffRoleFilter(ADMIN_ROLES)
)
async def staff_menu(cq: CallbackQuery, state: FSMContext) -> None:
    """Главное меню управления персоналом."""
    await state.clear()
    
    kb = InlineKeyboardBuilder()
    kb.button(text=f"{EMOJI['add']} Добавить персонал", callback_data="adm:staff:add:start")
    kb.button(text=f"{EMOJI['global_admin']} Global Admins", callback_data="adm:staff:list:GLOBAL_ADMIN:1")
    kb.button(text=f"{EMOJI['city_admin']} City Admins", callback_data="adm:staff:list:CITY_ADMIN:1")
    kb.button(text=f"{EMOJI['logist']} Logists", callback_data="adm:staff:list:LOGIST:1")
    kb.button(text=f"{EMOJI['back']} В главное меню", callback_data="adm:menu")
    kb.adjust(1)
    
    text = (
        "<b>👥 Управление персоналом</b>\n\n"
        "Выберите действие:"
    )
    
    await safe_edit_text(cq.message, text, reply_markup=kb.as_markup())
    await cq.answer()


# ============================================
# ДОБАВЛЕНИЕ ПЕРСОНАЛА
# ============================================

@router.callback_query(
    F.data == "adm:staff:add:start",
    StaffRoleFilter(ADMIN_ROLES)
)
async def staff_add_start(cq: CallbackQuery, state: FSMContext) -> None:
    """Начало процесса добавления персонала - выбор роли."""
    await state.clear()
    
    kb = _build_role_keyboard("adm:staff:add")
    
    text = (
        "<b>➕ Добавление персонала</b>\n\n"
        "Выберите роль для нового сотрудника:"
    )
    
    await safe_edit_text(cq.message, text, reply_markup=kb.as_markup())
    await cq.answer()


@router.callback_query(
    F.data.startswith("adm:staff:add:role:"),
    StaffRoleFilter(ADMIN_ROLES)
)
async def staff_add_role_selected(cq: CallbackQuery, state: FSMContext) -> None:
    """Обработка выбора роли."""
    try:
        role_value = cq.data.split(":")[-1]
        role = StaffRole(role_value)
    except (ValueError, IndexError):
        await cq.answer("Ошибка: неверная роль", show_alert=True)
        return
    
    await state.update_data(role=role.value)
    await state.set_state(StaffAddFSM.user_input)
    
    role_label = STAFF_ROLE_LABELS.get(role, role.value)
    
    kb = InlineKeyboardBuilder()
    kb.button(text=f"{EMOJI['back']} Отмена", callback_data="adm:staff:menu")
    
    text = (
        f"<b>➕ Добавление: {role_label}</b>\n\n"
        "Отправьте <b>Telegram ID</b> или <b>@username</b> сотрудника:\n\n"
        "Примеры:\n"
        "• <code>123456789</code> (Telegram ID)\n"
        "• <code>@username</code> (username)\n\n"
        "💡 Чтобы узнать Telegram ID:\n"
        "1. Попросите сотрудника написать боту @userinfobot\n"
        "2. Или используйте @getmyid_bot\n"
    )
    
    await safe_edit_text(cq.message, text, reply_markup=kb.as_markup())
    await cq.answer()


@router.message(
    StateFilter(StaffAddFSM.user_input),
    StaffRoleFilter(ADMIN_ROLES)
)
async def staff_add_user_input(msg: Message, state: FSMContext, staff: StaffUser) -> None:
    """Обработка ввода Telegram ID или username."""
    if not msg.text:
        await msg.answer("Пожалуйста, отправьте текстовое сообщение.")
        return
    
    user_input = msg.text.strip()
    
    # Парсинг ввода
    tg_id: Optional[int] = None
    username: Optional[str] = None
    
    if user_input.startswith("@"):
        username = user_input[1:].lower()
    elif user_input.isdigit():
        tg_id = int(user_input)
    else:
        await msg.answer(
            "❌ Неверный формат!\n\n"
            "Используйте:\n"
            "• Telegram ID (только цифры): <code>123456789</code>\n"
            "• Username (с @): <code>@username</code>"
        )
        return
    
    # Проверка существования
    staff_service = _staff_service(msg.bot)
    
    if tg_id:
        existing = await staff_service.get_by_tg_id(tg_id)
        if existing:
            await msg.answer(
                f"❌ Пользователь с ID {tg_id} уже зарегистрирован в системе!\n\n"
                f"Роль: {STAFF_ROLE_LABELS.get(existing.role, existing.role.value)}"
            )
            return
    
    # Сохраняем данные
    await state.update_data(
        tg_id=tg_id,
        username=username,
        user_display=user_input
    )
    
    # Переход к выбору городов
    data = await state.get_data()
    role = StaffRole(data["role"])
    
    if role == StaffRole.GLOBAL_ADMIN:
        # Для глобальных админов города не нужны
        await state.set_state(StaffAddFSM.confirm)
        await _show_add_confirm(msg.bot, msg.chat.id, state)
    else:
        # Для остальных ролей выбираем города
        await state.set_state(StaffAddFSM.city_select)
        await state.update_data(selected_cities=[])
        
        cities = await _get_cities_list(msg.bot)
        kb = _build_city_keyboard(cities, set(), "adm:staff:add:city")
        
        role_label = STAFF_ROLE_LABELS.get(role, role.value)
        text = (
            f"<b>➕ Добавление: {role_label}</b>\n"
            f"👤 Пользователь: {user_input}\n\n"
            "Выберите города для доступа:"
        )
        
        await msg.answer(text, reply_markup=kb.as_markup())


# Обработчики выбора городов
@router.callback_query(
    F.data.startswith("adm:staff:add:city:toggle:"),
    StaffRoleFilter(ADMIN_ROLES)
)
async def staff_add_city_toggle(cq: CallbackQuery, state: FSMContext) -> None:
    """Переключение города."""
    try:
        city_id = int(cq.data.split(":")[-1])
    except (ValueError, IndexError):
        await cq.answer("Ошибка", show_alert=True)
        return
    
    data = await state.get_data()
    selected = set(data.get("selected_cities", []))
    
    if city_id in selected:
        selected.remove(city_id)
    else:
        selected.add(city_id)
    
    await state.update_data(selected_cities=list(selected))
    
    # Обновляем клавиатуру
    cities = await _get_cities_list(cq.bot)
    kb = _build_city_keyboard(cities, selected, "adm:staff:add:city")
    
    role = StaffRole(data["role"])
    role_label = STAFF_ROLE_LABELS.get(role, role.value)
    user_display = data.get("user_display", "")
    
    text = (
        f"<b>➕ Добавление: {role_label}</b>\n"
        f"👤 Пользователь: {user_display}\n\n"
        "Выберите города для доступа:"
    )
    
    await cq.message.edit_text(text, reply_markup=kb.as_markup())
    await cq.answer()


@router.callback_query(
    F.data == "adm:staff:add:city:all",
    StaffRoleFilter(ADMIN_ROLES)
)
async def staff_add_city_all(cq: CallbackQuery, state: FSMContext) -> None:
    """Выбрать все города."""
    cities = await _get_cities_list(cq.bot)
    selected = {city.id for city in cities}
    
    await state.update_data(selected_cities=list(selected))
    
    kb = _build_city_keyboard(cities, selected, "adm:staff:add:city")
    
    data = await state.get_data()
    role = StaffRole(data["role"])
    role_label = STAFF_ROLE_LABELS.get(role, role.value)
    user_display = data.get("user_display", "")
    
    text = (
        f"<b>➕ Добавление: {role_label}</b>\n"
        f"👤 Пользователь: {user_display}\n\n"
        "Выберите города для доступа:"
    )
    
    await cq.message.edit_text(text, reply_markup=kb.as_markup())
    await cq.answer("Все города выбраны")


@router.callback_query(
    F.data == "adm:staff:add:city:clear",
    StaffRoleFilter(ADMIN_ROLES)
)
async def staff_add_city_clear(cq: CallbackQuery, state: FSMContext) -> None:
    """Сбросить выбор городов."""
    await state.update_data(selected_cities=[])
    
    cities = await _get_cities_list(cq.bot)
    kb = _build_city_keyboard(cities, set(), "adm:staff:add:city")
    
    data = await state.get_data()
    role = StaffRole(data["role"])
    role_label = STAFF_ROLE_LABELS.get(role, role.value)
    user_display = data.get("user_display", "")
    
    text = (
        f"<b>➕ Добавление: {role_label}</b>\n"
        f"👤 Пользователь: {user_display}\n\n"
        "Выберите города для доступа:"
    )
    
    await cq.message.edit_text(text, reply_markup=kb.as_markup())
    await cq.answer("Выбор сброшен")


@router.callback_query(
    F.data == "adm:staff:add:city:done",
    StaffRoleFilter(ADMIN_ROLES)
)
async def staff_add_city_done(cq: CallbackQuery, state: FSMContext) -> None:
    """Завершение выбора городов."""
    data = await state.get_data()
    selected_cities = data.get("selected_cities", [])
    
    if not selected_cities:
        await cq.answer("Выберите хотя бы один город!", show_alert=True)
        return
    
    await state.set_state(StaffAddFSM.confirm)
    await _show_add_confirm(cq.bot, cq.message.chat.id, state)
    await cq.answer()


@router.callback_query(
    F.data == "adm:staff:add:city:cancel",
    StaffRoleFilter(ADMIN_ROLES)
)
async def staff_add_city_cancel(cq: CallbackQuery, state: FSMContext) -> None:
    """Отмена добавления."""
    await state.clear()
    await staff_menu(cq, state)


async def _show_add_confirm(bot: Bot, chat_id: int, state: FSMContext) -> None:
    """Показать подтверждение добавления."""
    data = await state.get_data()
    
    role = StaffRole(data["role"])
    role_label = STAFF_ROLE_LABELS.get(role, role.value)
    user_display = data.get("user_display", "")
    selected_cities = data.get("selected_cities", [])
    
    # Получаем названия городов
    if selected_cities:
        city_names = await _resolve_city_names(bot, selected_cities)
        cities_text = ", ".join(city_names)
    else:
        cities_text = "Все города (Global Admin)"
    
    text = (
        "<b>📋 Подтверждение добавления</b>\n\n"
        f"👤 Пользователь: {user_display}\n"
        f"🏛 Роль: {role_label}\n"
        f"🏙 Города: {cities_text}\n\n"
        "Подтвердите добавление сотрудника:"
    )
    
    kb = InlineKeyboardBuilder()
    kb.button(text=f"{EMOJI['confirm']} Подтвердить", callback_data="adm:staff:add:confirm")
    kb.button(text=f"{EMOJI['cancel']} Отмена", callback_data="adm:staff:menu")
    kb.adjust(1)
    
    await bot.send_message(chat_id, text, reply_markup=kb.as_markup())


@router.callback_query(
    F.data == "adm:staff:add:confirm",
    StateFilter(StaffAddFSM.confirm),
    StaffRoleFilter(ADMIN_ROLES)
)
async def staff_add_confirm(cq: CallbackQuery, state: FSMContext, staff: StaffUser) -> None:
    """Подтверждение и создание сотрудника."""
    data = await state.get_data()
    
    role = StaffRole(data["role"])
    tg_id = data.get("tg_id")
    username = data.get("username")
    selected_cities = data.get("selected_cities", [])
    
    staff_service = _staff_service(cq.bot)
    
    try:
        # Добавляем сотрудника
        new_staff = await staff_service.add_staff_direct(
            tg_id=tg_id,
            username=username,
            role=role,
            city_ids=selected_cities,
            created_by_staff_id=staff.id
        )
        
        await state.clear()
        
        role_label = STAFF_ROLE_LABELS.get(role, role.value)
        
        text = (
            f"✅ <b>Сотрудник успешно добавлен!</b>\n\n"
            f"🆔 ID: <code>{new_staff.tg_id}</code>\n"
            f"🏛 Роль: {role_label}\n\n"
            f"Сотрудник может начать работу, написав команду /start боту."
        )
        
        kb = InlineKeyboardBuilder()
        kb.button(text=f"{EMOJI['list']} К списку персонала", callback_data="adm:staff:menu")
        kb.button(text=f"{EMOJI['back']} В главное меню", callback_data="adm:menu")
        kb.adjust(1)
        
        await safe_edit_text(cq.message, text, reply_markup=kb.as_markup())
        await cq.answer()
        
    except Exception as e:
        logger.error(f"Error adding staff: {e}")
        await cq.answer(f"Ошибка при добавлении: {str(e)}", show_alert=True)


# ============================================
# ПРОСМОТР СПИСКОВ ПЕРСОНАЛА
# ============================================

@router.callback_query(
    F.data.startswith("adm:staff:list:"),
    StaffRoleFilter(ADMIN_ROLES)
)
async def staff_list(cq: CallbackQuery, state: FSMContext) -> None:
    """Просмотр списка персонала по роли."""
    await state.clear()
    
    parts = cq.data.split(":")
    try:
        role = StaffRole(parts[3])
        page = int(parts[4]) if len(parts) > 4 else 1
    except (IndexError, ValueError):
        await cq.answer("Ошибка параметров", show_alert=True)
        return
    
    staff_service = _staff_service(cq.bot)
    members, has_next = await staff_service.list_staff(
        role=role,
        page=page,
        page_size=PAGE_SIZE
    )
    
    role_label = STAFF_ROLE_LABELS.get(role, role.value)
    
    if not members:
        text = f"<b>{role_label}</b>\n\nСписок пуст."
        kb = InlineKeyboardBuilder()
        kb.button(text=f"{EMOJI['back']} Назад", callback_data="adm:staff:menu")
        
        await cq.message.edit_text(text, reply_markup=kb.as_markup())
        await cq.answer()
        return
    
    # Формируем список
    lines = [f"<b>{role_label}</b>", f"Страница {page}", ""]
    
    for i, member in enumerate(members, start=1):
        status = EMOJI["active"] if member.is_active else EMOJI["inactive"]
        username_part = f"@{member.username}" if member.username else f"ID: {member.tg_id}"
        lines.append(f"{i}. {status} {username_part}")
    
    text = "\n".join(lines)
    
    # Клавиатура
    kb = InlineKeyboardBuilder()
    
    # Кнопки персонала
    for member in members:
        display = member.username or str(member.tg_id)
        kb.button(
            text=f"👤 {display}",
            callback_data=f"adm:staff:view:{member.id}"
        )
    
    kb.adjust(2)
    
    # Навигация
    nav = InlineKeyboardBuilder()
    if page > 1:
        nav.button(text="◀️ Назад", callback_data=f"adm:staff:list:{role.value}:{page-1}")
    if has_next:
        nav.button(text="▶️ Далее", callback_data=f"adm:staff:list:{role.value}:{page+1}")
    nav.adjust(2)
    
    kb.attach(nav)
    
    # Кнопка возврата
    back = InlineKeyboardBuilder()
    back.button(text=f"{EMOJI['back']} В меню персонала", callback_data="adm:staff:menu")
    kb.attach(back)
    
    await cq.message.edit_text(text, reply_markup=kb.as_markup())
    await cq.answer()


# ============================================
# ПРОСМОТР И РЕДАКТИРОВАНИЕ СОТРУДНИКА
# ============================================

@router.callback_query(
    F.data.startswith("adm:staff:view:"),
    StaffRoleFilter(ADMIN_ROLES)
)
async def staff_view(cq: CallbackQuery, staff: StaffUser) -> None:
    """Просмотр информации о сотруднике."""
    try:
        staff_id = int(cq.data.split(":")[-1])
    except (ValueError, IndexError):
        await cq.answer("Ошибка ID", show_alert=True)
        return
    
    staff_service = _staff_service(cq.bot)
    member = await staff_service.get_staff_member(staff_id)
    
    if not member:
        await cq.answer("Сотрудник не найден", show_alert=True)
        return
    
    # Получаем названия городов
    city_names = await _resolve_city_names(cq.bot, member.city_ids)
    
    text = _format_staff_info(member, city_names)
    
    # Клавиатура действий
    kb = InlineKeyboardBuilder()
    
    # Блокировка/активация
    if member.is_active:
        kb.button(
            text=f"{EMOJI['inactive']} Заблокировать",
            callback_data=f"adm:staff:block:{staff_id}"
        )
    else:
        kb.button(
            text=f"{EMOJI['active']} Активировать",
            callback_data=f"adm:staff:activate:{staff_id}"
        )
    
    # Редактирование (только для не-глобальных админов или если мы глобальный админ)
    if staff.role == StaffRole.GLOBAL_ADMIN or member.role != StaffRole.GLOBAL_ADMIN:
        kb.button(
            text=f"{EMOJI['edit']} Изменить роль",
            callback_data=f"adm:staff:edit:role:{staff_id}"
        )
        
        if member.role in (StaffRole.CITY_ADMIN, StaffRole.LOGIST):
            kb.button(
                text=f"{EMOJI['edit']} Изменить города",
                callback_data=f"adm:staff:edit:cities:{staff_id}"
            )
    
    kb.button(
        text=f"{EMOJI['back']} К списку",
        callback_data=f"adm:staff:list:{member.role.value}:1"
    )
    
    kb.adjust(1)
    
    await cq.message.edit_text(text, reply_markup=kb.as_markup())
    await cq.answer()


@router.callback_query(
    F.data.startswith("adm:staff:block:"),
    StaffRoleFilter(ADMIN_ROLES)
)
async def staff_block(cq: CallbackQuery, staff: StaffUser) -> None:
    """Блокировка сотрудника."""
    try:
        staff_id = int(cq.data.split(":")[-1])
    except (ValueError, IndexError):
        await cq.answer("Ошибка ID", show_alert=True)
        return
    
    staff_service = _staff_service(cq.bot)
    member = await staff_service.get_staff_member(staff_id)
    
    if not member:
        await cq.answer("Сотрудник не найден", show_alert=True)
        return
    
    # Запрет на блокировку самого себя и других глобальных админов
    if member.id == staff.id:
        await cq.answer("Нельзя заблокировать самого себя!", show_alert=True)
        return
    
    if member.role == StaffRole.GLOBAL_ADMIN and staff.role != StaffRole.GLOBAL_ADMIN:
        await cq.answer("Недостаточно прав", show_alert=True)
        return
    
    await staff_service.set_staff_active(staff_id, is_active=False)
    
    await cq.answer("✅ Сотрудник заблокирован")
    await staff_view(cq, staff)


@router.callback_query(
    F.data.startswith("adm:staff:activate:"),
    StaffRoleFilter(ADMIN_ROLES)
)
async def staff_activate(cq: CallbackQuery, staff: StaffUser) -> None:
    """Активация сотрудника."""
    try:
        staff_id = int(cq.data.split(":")[-1])
    except (ValueError, IndexError):
        await cq.answer("Ошибка ID", show_alert=True)
        return
    
    staff_service = _staff_service(cq.bot)
    await staff_service.set_staff_active(staff_id, is_active=True)
    
    await cq.answer("✅ Сотрудник активирован")
    await staff_view(cq, staff)


__all__ = ["router"]
