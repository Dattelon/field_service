"""
   -.

 UI     
   access-.

:
-    Telegram ID  @username
-   (Global Admin, City Admin, Logist)
-   
-   
-   
- / 
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
#  
# ===========================================

async def safe_edit_text(
    message,
    text: str,
    reply_markup=None,
    **kwargs
) -> bool:
    """  ,   'message is not modified'."""
    try:
        await message.edit_text(text, reply_markup=reply_markup, **kwargs)
        return True
    except Exception:
        return False

# 
PAGE_SIZE = 10
ADMIN_ROLES = {StaffRole.GLOBAL_ADMIN}
MANAGE_ROLES = {StaffRole.GLOBAL_ADMIN, StaffRole.CITY_ADMIN}

#   UI
EMOJI = {
    "add": "",
    "list": "",
    "edit": "",
    "delete": "",
    "active": "",
    "inactive": "",
    "back": "",
    "confirm": "",
    "cancel": "",
    "global_admin": "",
    "city_admin": "",
    "logist": "",
}

# ============================================
#  
# ============================================

def _orders_service(bot) -> Any:
    return get_service(bot, "orders_service")


def _format_staff_info(member, city_names: list[str]) -> str:
    """   ."""
    lines = []
    
    #   
    role_emoji = {
        StaffRole.GLOBAL_ADMIN: EMOJI["global_admin"],
        StaffRole.CITY_ADMIN: EMOJI["city_admin"],
        StaffRole.LOGIST: EMOJI["logist"],
    }.get(member.role, "")
    
    role_label = STAFF_ROLE_LABELS.get(member.role, member.role.value)
    lines.append(f"<b>{role_emoji} {role_label}</b>")
    lines.append("")
    
    #  
    lines.append(f" ID: <code>{member.tg_id}</code>")
    if member.username:
        lines.append(f" @{member.username}")
    lines.append(f" {member.full_name or ' '}")
    if member.phone:
        lines.append(f" {member.phone}")
    
    # 
    if city_names:
        lines.append(f" : {', '.join(city_names)}")
    else:
        lines.append(" : ")
    
    # 
    status = f"{EMOJI['active']} " if member.is_active else f"{EMOJI['inactive']} "
    lines.append(f" : {status}")
    
    # 
    if member.created_at:
        created = member.created_at.strftime("%d.%m.%Y %H:%M")
        lines.append(f" : {created}")
    
    return "\n".join(lines)


async def _get_cities_list(bot) -> list[CityRef]:
    """   ."""
    orders_service = _orders_service(bot)
    cities = await orders_service.list_cities()
    return sorted(cities, key=lambda c: c.name)


def _build_city_keyboard(
    cities: Sequence[CityRef],
    selected: set[int],
    prefix: str,
    show_done: bool = True,
) -> InlineKeyboardBuilder:
    """   ."""
    kb = InlineKeyboardBuilder()
    
    for city in cities:
        is_selected = city.id in selected
        check = " " if is_selected else ""
        kb.button(
            text=f"{check}{city.name}",
            callback_data=f"{prefix}:toggle:{city.id}"
        )
    
    kb.adjust(2)
    
    #  
    controls = InlineKeyboardBuilder()
    
    if selected:
        controls.button(text="  ", callback_data=f"{prefix}:clear")
    else:
        controls.button(text="  ", callback_data=f"{prefix}:all")
    
    if show_done:
        controls.button(text=f"{EMOJI['confirm']} ", callback_data=f"{prefix}:done")
    
    controls.button(text=f"{EMOJI['back']} ", callback_data=f"{prefix}:cancel")
    controls.adjust(2)
    
    kb.attach(controls)
    return kb


def _build_role_keyboard(prefix: str) -> InlineKeyboardBuilder:
    """   ."""
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
        text=f"{EMOJI['back']} ",
        callback_data="adm:staff:menu"
    )
    
    kb.adjust(1)
    return kb


# ============================================
#    
# ============================================

@router.callback_query(
    F.data == "adm:staff:menu",
    StaffRoleFilter(ADMIN_ROLES)
)
async def staff_menu(cq: CallbackQuery, state: FSMContext) -> None:
    """   ."""
    await state.clear()
    
    kb = InlineKeyboardBuilder()
    kb.button(text=f"{EMOJI['add']}  ", callback_data="adm:staff:add:start")
    kb.button(text=f"{EMOJI['global_admin']} Global Admins", callback_data="adm:staff:list:GLOBAL_ADMIN:1")
    kb.button(text=f"{EMOJI['city_admin']} City Admins", callback_data="adm:staff:list:CITY_ADMIN:1")
    kb.button(text=f"{EMOJI['logist']} Logists", callback_data="adm:staff:list:LOGIST:1")
    kb.button(text=f"{EMOJI['back']}   ", callback_data="adm:menu")
    kb.adjust(1)
    
    text = (
        "<b>  </b>\n\n"
        " :"
    )
    
    await safe_edit_text(cq.message, text, reply_markup=kb.as_markup())
    await cq.answer()


# ============================================
#  
# ============================================

@router.callback_query(
    F.data == "adm:staff:add:start",
    StaffRoleFilter(ADMIN_ROLES)
)
async def staff_add_start(cq: CallbackQuery, state: FSMContext) -> None:
    """    -  ."""
    await state.clear()
    
    kb = _build_role_keyboard("adm:staff:add")
    
    text = (
        "<b>  </b>\n\n"
        "    :"
    )
    
    await safe_edit_text(cq.message, text, reply_markup=kb.as_markup())
    await cq.answer()


@router.callback_query(
    F.data.startswith("adm:staff:add:role:"),
    StaffRoleFilter(ADMIN_ROLES)
)
async def staff_add_role_selected(cq: CallbackQuery, state: FSMContext) -> None:
    """  ."""
    try:
        role_value = cq.data.split(":")[-1]
        role = StaffRole(role_value)
    except (ValueError, IndexError):
        await cq.answer(":  ", show_alert=True)
        return
    
    await state.update_data(role=role.value)
    await state.set_state(StaffAddFSM.user_input)
    
    role_label = STAFF_ROLE_LABELS.get(role, role.value)
    
    kb = InlineKeyboardBuilder()
    kb.button(text=f"{EMOJI['back']} ", callback_data="adm:staff:menu")
    
    text = (
        f"<b> : {role_label}</b>\n\n"
        " <b>Telegram ID</b>  <b>@username</b> :\n\n"
        ":\n"
        " <code>123456789</code> (Telegram ID)\n"
        " <code>@username</code> (username)\n\n"
        "   Telegram ID:\n"
        "1.     @userinfobot\n"
        "2.   @getmyid_bot\n"
    )
    
    await safe_edit_text(cq.message, text, reply_markup=kb.as_markup())
    await cq.answer()


@router.message(
    StateFilter(StaffAddFSM.user_input),
    StaffRoleFilter(ADMIN_ROLES)
)
async def staff_add_user_input(msg: Message, state: FSMContext, staff: StaffUser) -> None:
    """  Telegram ID  username."""
    if not msg.text:
        await msg.answer(",   .")
        return
    
    user_input = msg.text.strip()
    
    #  
    tg_id: Optional[int] = None
    username: Optional[str] = None
    
    if user_input.startswith("@"):
        username = user_input[1:].lower()
    elif user_input.isdigit():
        tg_id = int(user_input)
    else:
        await msg.answer(
            "  !\n\n"
            ":\n"
            " Telegram ID ( ): <code>123456789</code>\n"
            " Username ( @): <code>@username</code>"
        )
        return
    
    #  
    staff_service = _staff_service(msg.bot)
    
    if tg_id:
        existing = await staff_service.get_by_tg_id(tg_id)
        if existing:
            await msg.answer(
                f"   ID {tg_id}    !\n\n"
                f": {STAFF_ROLE_LABELS.get(existing.role, existing.role.value)}"
            )
            return
    
    #  
    await state.update_data(
        tg_id=tg_id,
        username=username,
        user_display=user_input
    )
    
    #    
    data = await state.get_data()
    role = StaffRole(data["role"])
    
    if role == StaffRole.GLOBAL_ADMIN:
        #      
        await state.set_state(StaffAddFSM.confirm)
        await _show_add_confirm(msg.bot, msg.chat.id, state)
    else:
        #     
        await state.set_state(StaffAddFSM.city_select)
        await state.update_data(selected_cities=[])
        
        cities = await _get_cities_list(msg.bot)
        kb = _build_city_keyboard(cities, set(), "adm:staff:add:city")
        
        role_label = STAFF_ROLE_LABELS.get(role, role.value)
        text = (
            f"<b> : {role_label}</b>\n"
            f" : {user_input}\n\n"
            "   :"
        )
        
        await msg.answer(text, reply_markup=kb.as_markup())


#   
@router.callback_query(
    F.data.startswith("adm:staff:add:city:toggle:"),
    StaffRoleFilter(ADMIN_ROLES)
)
async def staff_add_city_toggle(cq: CallbackQuery, state: FSMContext) -> None:
    """ ."""
    try:
        city_id = int(cq.data.split(":")[-1])
    except (ValueError, IndexError):
        await cq.answer("", show_alert=True)
        return
    
    data = await state.get_data()
    selected = set(data.get("selected_cities", []))
    
    if city_id in selected:
        selected.remove(city_id)
    else:
        selected.add(city_id)
    
    await state.update_data(selected_cities=list(selected))
    
    #  
    cities = await _get_cities_list(cq.bot)
    kb = _build_city_keyboard(cities, selected, "adm:staff:add:city")
    
    role = StaffRole(data["role"])
    role_label = STAFF_ROLE_LABELS.get(role, role.value)
    user_display = data.get("user_display", "")
    
    text = (
        f"<b> : {role_label}</b>\n"
        f" : {user_display}\n\n"
        "   :"
    )
    
    await cq.message.edit_text(text, reply_markup=kb.as_markup())
    await cq.answer()


@router.callback_query(
    F.data == "adm:staff:add:city:all",
    StaffRoleFilter(ADMIN_ROLES)
)
async def staff_add_city_all(cq: CallbackQuery, state: FSMContext) -> None:
    """  ."""
    cities = await _get_cities_list(cq.bot)
    selected = {city.id for city in cities}
    
    await state.update_data(selected_cities=list(selected))
    
    kb = _build_city_keyboard(cities, selected, "adm:staff:add:city")
    
    data = await state.get_data()
    role = StaffRole(data["role"])
    role_label = STAFF_ROLE_LABELS.get(role, role.value)
    user_display = data.get("user_display", "")
    
    text = (
        f"<b> : {role_label}</b>\n"
        f" : {user_display}\n\n"
        "   :"
    )
    
    await cq.message.edit_text(text, reply_markup=kb.as_markup())
    await cq.answer("  ")


@router.callback_query(
    F.data == "adm:staff:add:city:clear",
    StaffRoleFilter(ADMIN_ROLES)
)
async def staff_add_city_clear(cq: CallbackQuery, state: FSMContext) -> None:
    """  ."""
    await state.update_data(selected_cities=[])
    
    cities = await _get_cities_list(cq.bot)
    kb = _build_city_keyboard(cities, set(), "adm:staff:add:city")
    
    data = await state.get_data()
    role = StaffRole(data["role"])
    role_label = STAFF_ROLE_LABELS.get(role, role.value)
    user_display = data.get("user_display", "")
    
    text = (
        f"<b> : {role_label}</b>\n"
        f" : {user_display}\n\n"
        "   :"
    )
    
    await cq.message.edit_text(text, reply_markup=kb.as_markup())
    await cq.answer(" ")


@router.callback_query(
    F.data == "adm:staff:add:city:done",
    StaffRoleFilter(ADMIN_ROLES)
)
async def staff_add_city_done(cq: CallbackQuery, state: FSMContext) -> None:
    """  ."""
    data = await state.get_data()
    selected_cities = data.get("selected_cities", [])
    
    if not selected_cities:
        await cq.answer("    !", show_alert=True)
        return
    
    await state.set_state(StaffAddFSM.confirm)
    await _show_add_confirm(cq.bot, cq.message.chat.id, state)
    await cq.answer()


@router.callback_query(
    F.data == "adm:staff:add:city:cancel",
    StaffRoleFilter(ADMIN_ROLES)
)
async def staff_add_city_cancel(cq: CallbackQuery, state: FSMContext) -> None:
    """ ."""
    await state.clear()
    await staff_menu(cq, state)


async def _show_add_confirm(bot: Bot, chat_id: int, state: FSMContext) -> None:
    """  ."""
    data = await state.get_data()
    
    role = StaffRole(data["role"])
    role_label = STAFF_ROLE_LABELS.get(role, role.value)
    user_display = data.get("user_display", "")
    selected_cities = data.get("selected_cities", [])
    
    #   
    if selected_cities:
        city_names = await _resolve_city_names(bot, selected_cities)
        cities_text = ", ".join(city_names)
    else:
        cities_text = "  (Global Admin)"
    
    text = (
        "<b>  </b>\n\n"
        f" : {user_display}\n"
        f" : {role_label}\n"
        f" : {cities_text}\n\n"
        "  :"
    )
    
    kb = InlineKeyboardBuilder()
    kb.button(text=f"{EMOJI['confirm']} ", callback_data="adm:staff:add:confirm")
    kb.button(text=f"{EMOJI['cancel']} ", callback_data="adm:staff:menu")
    kb.adjust(1)
    
    await bot.send_message(chat_id, text, reply_markup=kb.as_markup())


@router.callback_query(
    F.data == "adm:staff:add:confirm",
    StateFilter(StaffAddFSM.confirm),
    StaffRoleFilter(ADMIN_ROLES)
)
async def staff_add_confirm(cq: CallbackQuery, state: FSMContext, staff: StaffUser) -> None:
    """   ."""
    data = await state.get_data()
    
    role = StaffRole(data["role"])
    tg_id = data.get("tg_id")
    username = data.get("username")
    selected_cities = data.get("selected_cities", [])
    
    staff_service = _staff_service(cq.bot)
    
    try:
        #  
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
            f" <b>  !</b>\n\n"
            f" ID: <code>{new_staff.tg_id}</code>\n"
            f" : {role_label}\n\n"
            f"   ,   /start ."
        )
        
        kb = InlineKeyboardBuilder()
        kb.button(text=f"{EMOJI['list']}   ", callback_data="adm:staff:menu")
        kb.button(text=f"{EMOJI['back']}   ", callback_data="adm:menu")
        kb.adjust(1)
        
        await safe_edit_text(cq.message, text, reply_markup=kb.as_markup())
        await cq.answer()
        
    except Exception as e:
        logger.error(f"Error adding staff: {e}")
        await cq.answer(f"  : {str(e)}", show_alert=True)


# ============================================
#   
# ============================================

@router.callback_query(
    F.data.startswith("adm:staff:list:"),
    StaffRoleFilter(ADMIN_ROLES)
)
async def staff_list(cq: CallbackQuery, state: FSMContext) -> None:
    """    ."""
    await state.clear()
    
    parts = cq.data.split(":")
    try:
        role = StaffRole(parts[3])
        page = int(parts[4]) if len(parts) > 4 else 1
    except (IndexError, ValueError):
        await cq.answer(" ", show_alert=True)
        return
    
    staff_service = _staff_service(cq.bot)
    members, has_next = await staff_service.list_staff(
        role=role,
        page=page,
        page_size=PAGE_SIZE
    )
    
    role_label = STAFF_ROLE_LABELS.get(role, role.value)
    
    if not members:
        text = f"<b>{role_label}</b>\n\n ."
        kb = InlineKeyboardBuilder()
        kb.button(text=f"{EMOJI['back']} ", callback_data="adm:staff:menu")
        
        await cq.message.edit_text(text, reply_markup=kb.as_markup())
        await cq.answer()
        return
    
    #  
    lines = [f"<b>{role_label}</b>", f" {page}", ""]
    
    for i, member in enumerate(members, start=1):
        status = EMOJI["active"] if member.is_active else EMOJI["inactive"]
        username_part = f"@{member.username}" if member.username else f"ID: {member.tg_id}"
        lines.append(f"{i}. {status} {username_part}")
    
    text = "\n".join(lines)
    
    # 
    kb = InlineKeyboardBuilder()
    
    #  
    for member in members:
        display = member.username or str(member.tg_id)
        kb.button(
            text=f" {display}",
            callback_data=f"adm:staff:view:{member.id}"
        )
    
    kb.adjust(2)
    
    # 
    nav = InlineKeyboardBuilder()
    if page > 1:
        nav.button(text=" ", callback_data=f"adm:staff:list:{role.value}:{page-1}")
    if has_next:
        nav.button(text=" ", callback_data=f"adm:staff:list:{role.value}:{page+1}")
    nav.adjust(2)
    
    kb.attach(nav)
    
    #  
    back = InlineKeyboardBuilder()
    back.button(text=f"{EMOJI['back']}   ", callback_data="adm:staff:menu")
    kb.attach(back)
    
    await cq.message.edit_text(text, reply_markup=kb.as_markup())
    await cq.answer()


# ============================================
#    
# ============================================

@router.callback_query(
    F.data.startswith("adm:staff:view:"),
    StaffRoleFilter(ADMIN_ROLES)
)
async def staff_view(cq: CallbackQuery, staff: StaffUser) -> None:
    """   ."""
    try:
        staff_id = int(cq.data.split(":")[-1])
    except (ValueError, IndexError):
        await cq.answer(" ID", show_alert=True)
        return
    
    staff_service = _staff_service(cq.bot)
    member = await staff_service.get_staff_member(staff_id)
    
    if not member:
        await cq.answer("  ", show_alert=True)
        return
    
    #   
    city_names = await _resolve_city_names(cq.bot, member.city_ids)
    
    text = _format_staff_info(member, city_names)
    
    #  
    kb = InlineKeyboardBuilder()
    
    # /
    if member.is_active:
        kb.button(
            text=f"{EMOJI['inactive']} ",
            callback_data=f"adm:staff:block:{staff_id}"
        )
    else:
        kb.button(
            text=f"{EMOJI['active']} ",
            callback_data=f"adm:staff:activate:{staff_id}"
        )
    
    #  (  -      )
    if staff.role == StaffRole.GLOBAL_ADMIN or member.role != StaffRole.GLOBAL_ADMIN:
        kb.button(
            text=f"{EMOJI['edit']}  ",
            callback_data=f"adm:staff:edit:role:{staff_id}"
        )
        
        if member.role in (StaffRole.CITY_ADMIN, StaffRole.LOGIST):
            kb.button(
                text=f"{EMOJI['edit']}  ",
                callback_data=f"adm:staff:edit:cities:{staff_id}"
            )
    
    kb.button(
        text=f"{EMOJI['back']}  ",
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
    """ ."""
    try:
        staff_id = int(cq.data.split(":")[-1])
    except (ValueError, IndexError):
        await cq.answer(" ID", show_alert=True)
        return
    
    staff_service = _staff_service(cq.bot)
    member = await staff_service.get_staff_member(staff_id)
    
    if not member:
        await cq.answer("  ", show_alert=True)
        return
    
    #         
    if member.id == staff.id:
        await cq.answer("   !", show_alert=True)
        return
    
    if member.role == StaffRole.GLOBAL_ADMIN and staff.role != StaffRole.GLOBAL_ADMIN:
        await cq.answer(" ", show_alert=True)
        return
    
    await staff_service.set_staff_active(staff_id, is_active=False)
    
    await cq.answer("  ")
    await staff_view(cq, staff)


@router.callback_query(
    F.data.startswith("adm:staff:activate:"),
    StaffRoleFilter(ADMIN_ROLES)
)
async def staff_activate(cq: CallbackQuery, staff: StaffUser) -> None:
    """ ."""
    try:
        staff_id = int(cq.data.split(":")[-1])
    except (ValueError, IndexError):
        await cq.answer(" ID", show_alert=True)
        return
    
    staff_service = _staff_service(cq.bot)
    await staff_service.set_staff_active(staff_id, is_active=True)
    
    await cq.answer("  ")
    await staff_view(cq, staff)


__all__ = ["router"]
