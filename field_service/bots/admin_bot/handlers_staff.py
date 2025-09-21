from __future__ import annotations

from typing import Iterable, Optional

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from .dto import StaffAccessCode, StaffMember, StaffRole, StaffUser
from .filters import StaffRoleFilter
from .states import AccessCodeNewFSM, StaffCityEditFSM
from .utils import get_service

router = Router(name="admin_staff_handlers")


def _staff_service(bot):
    return get_service(bot, "staff_service")


def _orders_service(bot):
    return get_service(bot, "orders_service")


# ------------------------------- access codes ------------------------------


@router.callback_query(F.data == "adm:codes", StaffRoleFilter({StaffRole.GLOBAL_ADMIN}))
async def codes_root(cq: CallbackQuery) -> None:
    kb = InlineKeyboardBuilder()
    kb.button(text="New code (GLOBAL)", callback_data="adm:codes:new:GLOBAL_ADMIN")
    kb.button(text="New code (CITY)", callback_data="adm:codes:new:CITY_ADMIN")
    kb.button(text="New code (LOGIST)", callback_data="adm:codes:new:LOGIST")
    kb.button(text="Active", callback_data="adm:codes:list:active:1")
    kb.button(text="Used", callback_data="adm:codes:list:used:1")
    kb.button(text="Revoked", callback_data="adm:codes:list:revoked:1")
    kb.button(text="Back", callback_data="adm:menu")
    kb.adjust(1)
    await cq.message.edit_text("Access codes:", reply_markup=kb.as_markup())
    await cq.answer()


@router.callback_query(F.data.startswith("adm:codes:list:"), StaffRoleFilter({StaffRole.GLOBAL_ADMIN}))
async def codes_list(cq: CallbackQuery) -> None:
    _, _, _, kind, page_str = cq.data.split(":")
    page = max(1, int(page_str))
    service = _staff_service(cq.message.bot)
    codes, has_next = await service.list_access_codes(state=kind, page=page, page_size=10)
    if not codes:
        kb = InlineKeyboardBuilder()
        kb.button(text="Back", callback_data="adm:codes")
        await cq.message.edit_text("No codes found.", reply_markup=kb.as_markup())
        await cq.answer()
        return
    lines = [f"<b>Codes: {kind}</b>", ""]
    kb = InlineKeyboardBuilder()
    for code in codes:
        lines.append(f"- {code.code} · {code.role.value} · cities {len(code.city_ids)}")
        kb.button(text=code.code, callback_data=f"adm:codes:card:{code.id}")
    kb.adjust(2)
    nav = InlineKeyboardBuilder()
    if page > 1:
        nav.button(text="Prev", callback_data=f"adm:codes:list:{kind}:{page - 1}")
    if has_next:
        nav.button(text="Next", callback_data=f"adm:codes:list:{kind}:{page + 1}")
    nav.button(text="Back", callback_data="adm:codes")
    kb.attach(nav)
    await cq.message.edit_text("\n".join(lines), reply_markup=kb.as_markup())
    await cq.answer()


@router.callback_query(F.data.startswith("adm:codes:card:"), StaffRoleFilter({StaffRole.GLOBAL_ADMIN}))
async def codes_card(cq: CallbackQuery) -> None:
    code_id = int(cq.data.split(":")[3])
    service = _staff_service(cq.message.bot)
    code: Optional[StaffAccessCode] = await service.get_access_code(code_id)
    if not code:
        await cq.answer("Code not found", show_alert=True)
        return
    lines = [
        f"<b>{code.code}</b>",
        f"Role: {code.role.value}",
        f"Cities: {', '.join(map(str, code.city_ids)) or '—'}",
        f"Created at: {code.created_at:%Y-%m-%d %H:%M}",
        f"Used at: {code.used_at:%Y-%m-%d %H:%M if code.used_at else '—'}",
        f"Status: {'revoked' if code.is_revoked else ('used' if code.used_at else 'active')}",
    ]
    kb = InlineKeyboardBuilder()
    if not code.is_revoked and not code.used_at:
        kb.button(text="Revoke", callback_data=f"adm:codes:revoke:{code.id}")
    kb.button(text="Back", callback_data="adm:codes")
    await cq.message.edit_text("\n".join(lines), reply_markup=kb.as_markup())
    await cq.answer()


@router.callback_query(F.data.startswith("adm:codes:revoke:"), StaffRoleFilter({StaffRole.GLOBAL_ADMIN}))
async def codes_revoke(cq: CallbackQuery) -> None:
    code_id = int(cq.data.split(":")[3])
    service = _staff_service(cq.message.bot)
    ok = await service.revoke_access_code(code_id)
    await cq.answer("Revoked" if ok else "Cannot revoke", show_alert=not ok)
    await codes_root(cq)


@router.callback_query(F.data.startswith("adm:codes:new:"), StaffRoleFilter({StaffRole.GLOBAL_ADMIN}))
async def codes_new_start(cq: CallbackQuery, state: FSMContext) -> None:
    role_token = cq.data.split(":")[3]
    await state.set_state(AccessCodeNewFSM.city_select)
    await state.update_data(role=role_token)
    orders_service = _orders_service(cq.message.bot)
    cities = await orders_service.list_cities(limit=80)
    info = "\n".join(f"{city.id}: {city.name}" for city in cities)
    text = (
        f"Role: {role_token}\n"
        "Send city IDs separated by commas (or '-' for none).\n"
        "Available cities:\n" + info
    )
    await cq.message.edit_text(text)
    await cq.answer()


@router.message(StateFilter(AccessCodeNewFSM.city_select), StaffRoleFilter({StaffRole.GLOBAL_ADMIN}))
async def codes_new_cities(msg: Message, state: FSMContext, staff: StaffUser) -> None:
    raw = msg.text.replace(" ", "")
    if not raw or raw == "-":
        city_ids: Iterable[int] = []
    else:
        try:
            city_ids = [int(part) for part in raw.split(",") if part]
        except ValueError:
            await msg.answer("Cannot parse list. Use comma separated numbers or '-'.")
            return
    data = await state.get_data()
    role_token = data.get("role")
    try:
        role = StaffRole(role_token)
    except ValueError:
        await state.clear()
        await msg.answer("Unknown role, try again from the menu.")
        return
    service = _staff_service(msg.bot)
    code = await service.create_access_code(
        role=role,
        city_ids=city_ids,
        issued_by_staff_id=staff.id,
        expires_at=None,
        comment=None,
    )
    await state.clear()
    await msg.answer(f"Generated code: {code.code}")


# ------------------------------- staff list -------------------------------


@router.callback_query(F.data == "adm:staff:menu", StaffRoleFilter({StaffRole.GLOBAL_ADMIN}))
async def staff_menu(cq: CallbackQuery) -> None:
    kb = InlineKeyboardBuilder()
    kb.button(text="Global", callback_data="adm:staff:list:GLOBAL_ADMIN:1")
    kb.button(text="City admins", callback_data="adm:staff:list:CITY_ADMIN:1")
    kb.button(text="Logists", callback_data="adm:staff:list:LOGIST:1")
    kb.button(text="Back", callback_data="adm:menu")
    kb.adjust(1)
    await cq.message.edit_text("Staff members:", reply_markup=kb.as_markup())
    await cq.answer()


@router.callback_query(F.data.startswith("adm:staff:list:"), StaffRoleFilter({StaffRole.GLOBAL_ADMIN}))
async def staff_list(cq: CallbackQuery) -> None:
    _, _, _, role_token, page_str = cq.data.split(":")
    page = max(1, int(page_str))
    try:
        role = StaffRole(role_token)
    except ValueError:
        await cq.answer("Unknown role", show_alert=True)
        return
    service = _staff_service(cq.message.bot)
    members, has_next = await service.list_staff(role=role, page=page, page_size=10)
    if not members:
        kb = InlineKeyboardBuilder()
        kb.button(text="Back", callback_data="adm:staff:menu")
        await cq.message.edit_text("No staff found.", reply_markup=kb.as_markup())
        await cq.answer()
        return
    lines = [f"<b>{role.value}</b>", ""]
    kb = InlineKeyboardBuilder()
    for member in members:
        status = "active" if member.is_active else "inactive"
        lines.append(f"- #{member.id} {member.full_name} · {status}")
        kb.button(text=str(member.id), callback_data=f"adm:staff:card:{member.id}")
    kb.adjust(3)
    nav = InlineKeyboardBuilder()
    if page > 1:
        nav.button(text="Prev", callback_data=f"adm:staff:list:{role_token}:{page - 1}")
    if has_next:
        nav.button(text="Next", callback_data=f"adm:staff:list:{role_token}:{page + 1}")
    nav.button(text="Back", callback_data="adm:staff:menu")
    kb.attach(nav)
    await cq.message.edit_text("\n".join(lines), reply_markup=kb.as_markup())
    await cq.answer()


@router.callback_query(F.data.startswith("adm:staff:card:"), StaffRoleFilter({StaffRole.GLOBAL_ADMIN}))
async def staff_card(cq: CallbackQuery) -> None:
    staff_id = int(cq.data.split(":")[3])
    service = _staff_service(cq.message.bot)
    member: Optional[StaffMember] = await service.get_staff_member(staff_id)
    if not member:
        await cq.answer("Staff member not found", show_alert=True)
        return
    cities = ", ".join(map(str, member.city_ids)) or "—"
    status = "active" if member.is_active else "inactive"
    lines = [
        f"<b>#{member.id} {member.full_name}</b>",
        f"Role: {member.role.value}",
        f"Phone: {member.phone or '—'}",
        f"Telegram ID: {member.tg_id or '—'}",
        f"Status: {status}",
        f"Cities: {cities}",
    ]
    kb = InlineKeyboardBuilder()
    kb.button(text="Toggle active", callback_data=f"adm:staff:toggle:{member.id}")
    kb.button(text="Edit cities", callback_data=f"adm:staff:cities:{member.id}")
    kb.button(text="Back", callback_data="adm:staff:menu")
    await cq.message.edit_text("\n".join(lines), reply_markup=kb.as_markup())
    await cq.answer()


@router.callback_query(F.data.startswith("adm:staff:toggle:"), StaffRoleFilter({StaffRole.GLOBAL_ADMIN}))
async def staff_toggle(cq: CallbackQuery) -> None:
    staff_id = int(cq.data.split(":")[3])
    service = _staff_service(cq.message.bot)
    member = await service.get_staff_member(staff_id)
    if not member:
        await cq.answer("Staff member not found", show_alert=True)
        return
    await service.set_staff_active(staff_id, is_active=not member.is_active)
    await cq.answer("Updated")
    await staff_card(cq)


@router.callback_query(F.data.startswith("adm:staff:cities:"), StaffRoleFilter({StaffRole.GLOBAL_ADMIN}))
async def staff_edit_cities(cq: CallbackQuery, state: FSMContext) -> None:
    staff_id = int(cq.data.split(":")[3])
    await state.set_state(StaffCityEditFSM.action)
    await state.update_data(edit_staff_id=staff_id)
    await cq.message.edit_text("Send city IDs separated by commas (or '-' to clear).")
    await cq.answer()


@router.message(StateFilter(StaffCityEditFSM.action), StaffRoleFilter({StaffRole.GLOBAL_ADMIN}))
async def staff_edit_cities_input(msg: Message, state: FSMContext) -> None:
    raw = msg.text.replace(" ", "")
    if not raw or raw == "-":
        city_ids: Iterable[int] = []
    else:
        try:
            city_ids = [int(part) for part in raw.split(",") if part]
        except ValueError:
            await msg.answer("Cannot parse list. Use comma separated numbers or '-'.")
            return
    data = await state.get_data()
    staff_id = data.get("edit_staff_id")
    if staff_id is None:
        await state.clear()
        await msg.answer("State lost. Try again from the menu.")
        return
    service = _staff_service(msg.bot)
    await service.set_staff_cities(int(staff_id), city_ids)
    await state.clear()
    await msg.answer("Cities updated.")


