from __future__ import annotations

from datetime import timedelta
from typing import Any, Iterable, Optional, Sequence

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from field_service.bots.common import FSMTimeoutConfig, FSMTimeoutMiddleware

from .dto import CityRef, StaffAccessCode, StaffMember, StaffRole, StaffUser
from .filters import StaffRoleFilter
from .states import AccessCodeNewFSM, StaffCityEditFSM
from .utils import get_service

router = Router(name="admin_staff_handlers")
CITY_PAGE_SIZE = 12


async def _fsm_timeout_notice(state: FSMContext) -> None:
    chat_id = state.key.chat_id
    if chat_id is None:
        return
    try:
        await state.bot.send_message(
            chat_id,
            "Session timed out. Use /start to return to the menu.",
        )
    except Exception:
        pass


_STAFF_TIMEOUT = FSMTimeoutMiddleware(
    FSMTimeoutConfig(timeout=timedelta(minutes=10), callback=_fsm_timeout_notice)
)

router.message.middleware(_STAFF_TIMEOUT)
router.callback_query.middleware(_STAFF_TIMEOUT)



ROLE_LABELS = {
    StaffRole.GLOBAL_ADMIN: "Global admin",
    StaffRole.CITY_ADMIN: "City admin",
    StaffRole.LOGIST: "Logist",
}


def _staff_service(bot) -> Any:
    return get_service(bot, "staff_service")


def _orders_service(bot) -> Any:
    return get_service(bot, "orders_service")


def _role_label(role: StaffRole) -> str:
    return ROLE_LABELS.get(role, role.value)


async def _resolve_city_names(bot, city_ids: Sequence[int]) -> list[str]:
    if not city_ids:
        return []
    orders = _orders_service(bot)
    names: list[str] = []
    for city_id in city_ids:
        city = await orders.get_city(city_id)
        names.append(city.name if city else str(city_id))
    return names


def _format_city_line(names: Sequence[str]) -> str:
    return ", ".join(names) if names else "-"


def _build_staff_menu() -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.button(text="Generate code (global)", callback_data="adm:staff:new:GLOBAL_ADMIN")
    kb.button(text="Generate code (city)", callback_data="adm:staff:new:CITY_ADMIN")
    kb.button(text="Generate code (logist)", callback_data="adm:staff:new:LOGIST")
    kb.button(text="Global admins", callback_data="adm:staff:list:GLOBAL_ADMIN:1")
    kb.button(text="City admins", callback_data="adm:staff:list:CITY_ADMIN:1")
    kb.button(text="Logists", callback_data="adm:staff:list:LOGIST:1")
    kb.button(text="Back", callback_data="adm:menu")
    kb.adjust(1)
    return kb


async def _send_staff_menu(cq: CallbackQuery) -> None:
    kb = _build_staff_menu()
    await cq.message.edit_text(
        "Staff & Access",
        reply_markup=kb.as_markup(),
    )



async def _load_cities(bot) -> list[CityRef]:
    orders = _orders_service(bot)
    return await orders.list_cities(limit=200)


def _serialize_cities(cities: Sequence[CityRef]) -> list[dict[str, int | str]]:
    return [{"id": city.id, "name": city.name} for city in cities]


def _deserialize_cities(payload: Sequence[dict[str, int | str]]) -> list[CityRef]:
    return [CityRef(id=int(item["id"]), name=str(item["name"])) for item in payload]


def _build_city_keyboard(
    cities: Sequence[CityRef],
    selected: set[int],
    page: int,
    *,
    prefix: str,
    show_done: bool = True,
    allow_empty: bool = True,
) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    total = len(cities)
    start = max(page - 1, 0) * CITY_PAGE_SIZE
    chunk = cities[start : start + CITY_PAGE_SIZE]
    for city in chunk:
        marker = "[x]" if city.id in selected else "[ ]"
        kb.button(text=f"{marker} {city.name}", callback_data=f"{prefix}:pick:{city.id}")
    if chunk:
        kb.adjust(1)
    nav_buttons: list[tuple[str, str]] = []
    if start > 0:
        nav_buttons.append(("◀️ Назад", f"{prefix}:page:{page - 1}"))
    if start + CITY_PAGE_SIZE < total:
        nav_buttons.append(("▶️ Далее", f"{prefix}:page:{page + 1}"))
    if nav_buttons:
        nav = InlineKeyboardBuilder()
        for text_label, callback_data in nav_buttons:
            nav.button(text=text_label, callback_data=callback_data)
        nav.adjust(len(nav_buttons))
        kb.attach(nav)
    control_buttons: list[tuple[str, str]] = []
    if show_done:
        control_buttons.append(("✅ Готово", f"{prefix}:done"))
    if allow_empty:
        control_buttons.append(("✖️ Отмена", f"{prefix}:cancel"))
    if control_buttons:
        controls = InlineKeyboardBuilder()
        for text_label, callback_data in control_buttons:
            controls.button(text=text_label, callback_data=callback_data)
        controls.adjust(len(control_buttons))
        kb.attach(controls)
    return kb


async def _render_city_selector(
    cq: CallbackQuery,
    *,
    prefix: str,
    cities: Sequence[CityRef],
    selected: Iterable[int],
    page: int,
    title: str,
    show_done: bool = True,
    allow_empty: bool = True,
) -> None:
    keyboard = _build_city_keyboard(
        cities,
        set(selected),
        page,
        prefix=prefix,
        show_done=show_done,
        allow_empty=allow_empty,
    )
    if cq.message is not None:
        await cq.message.edit_text(title, reply_markup=keyboard.as_markup())


@router.callback_query(F.data == "adm:staff:menu", StaffRoleFilter({StaffRole.GLOBAL_ADMIN}))
async def staff_menu(cq: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await _send_staff_menu(cq)
    await cq.answer()


@router.callback_query(F.data.startswith("adm:staff:list:"), StaffRoleFilter({StaffRole.GLOBAL_ADMIN}))
async def staff_list(cq: CallbackQuery, state: FSMContext) -> None:
    parts = cq.data.split(":")
    try:
        role = StaffRole(parts[3])
    except (IndexError, ValueError):
        await cq.answer("Unknown role", show_alert=True)
        return
    try:
        page = max(1, int(parts[4]))
    except (IndexError, ValueError):
        page = 1

    service = _staff_service(cq.message.bot)
    members, has_next = await service.list_staff(role=role, page=page, page_size=10)
    await state.update_data(staff_list_role=role.value, staff_list_page=page)

    if not members:
        kb = InlineKeyboardBuilder()
        kb.button(text="Back", callback_data="adm:staff:menu")
        await cq.message.edit_text("No staff found.", reply_markup=kb.as_markup())
        await cq.answer()
        return

    city_map: dict[int, list[str]] = {}
    for member in members:
        if member.city_ids:
            city_map[member.id] = await _resolve_city_names(cq.message.bot, member.city_ids)

    lines = [f"<b>{_role_label(role)}</b>"]
    kb = InlineKeyboardBuilder()
    for member in members:
        status = "active" if member.is_active else "inactive"
        city_names = _format_city_line(city_map.get(member.id, []))
        name = member.full_name or "-"
        lines.append(f"#{member.id} {name}  {status} ({city_names})")
        kb.button(text=str(member.id), callback_data=f"adm:staff:edit:{member.id}")
    kb.adjust(3)

    nav = InlineKeyboardBuilder()
    if page > 1:
        nav.button(text="Prev", callback_data=f"adm:staff:list:{role.value}:{page - 1}")
    if has_next:
        nav.button(text="Next", callback_data=f"adm:staff:list:{role.value}:{page + 1}")
    nav.button(text="Menu", callback_data="adm:staff:menu")
    if nav.buttons:
        nav.adjust(len(nav.buttons))
        kb.attach(nav)

    await cq.message.edit_text(
        "\n".join(lines),
        reply_markup=kb.as_markup(),
    )
    await cq.answer()


async def _render_staff_card(cq: CallbackQuery, member: StaffMember, city_names: Sequence[str], state: FSMContext) -> None:
    status = "Active" if member.is_active else "Inactive"
    lines = [
        f"<b>#{member.id} {member.full_name or '-'} ({_role_label(member.role)})</b>",
        f"Phone: {member.phone or '-'}",
        f"Telegram ID: {member.tg_id or '-'}",
        f"Cities: {_format_city_line(city_names)}",
        f"Status: {status}",
    ]
    kb = InlineKeyboardBuilder()
    kb.button(
        text="Deactivate" if member.is_active else "Activate",
        callback_data=f"adm:staff:deact:{member.id}",
    )
    if member.role in (StaffRole.CITY_ADMIN, StaffRole.LOGIST):
        kb.button(text="Edit cities", callback_data=f"adm:staff:edit:cities:{member.id}")
    data = await state.get_data()
    role_token = data.get("staff_list_role", member.role.value)
    page = data.get("staff_list_page", 1)
    kb.button(text="Back", callback_data=f"adm:staff:list:{role_token}:{page}")
    kb.adjust(1)
    await cq.message.edit_text(
        "\n".join(lines),
        reply_markup=kb.as_markup(),
    )


@router.callback_query(F.data.startswith("adm:staff:edit:"), StaffRoleFilter({StaffRole.GLOBAL_ADMIN}))
async def staff_card(cq: CallbackQuery, state: FSMContext) -> None:
    staff_id = int(cq.data.split(":")[3])
    service = _staff_service(cq.message.bot)
    member = await service.get_staff_member(staff_id)
    if not member:
        await cq.answer("Not found", show_alert=True)
        return
    city_names = await _resolve_city_names(cq.message.bot, member.city_ids)
    await _render_staff_card(cq, member, city_names, state)
    await cq.answer()


@router.callback_query(
    F.data.startswith("adm:staff:deact:"),
    StaffRoleFilter({StaffRole.GLOBAL_ADMIN}),
)
async def staff_toggle_active(cq: CallbackQuery, state: FSMContext) -> None:
    staff_id = int(cq.data.split(":")[3])
    service = _staff_service(cq.message.bot)
    member = await service.get_staff_member(staff_id)
    if not member:
        await cq.answer("Not found", show_alert=True)
        return
    await service.set_staff_active(staff_id, is_active=not member.is_active)
    refreshed = await service.get_staff_member(staff_id)
    city_names = await _resolve_city_names(cq.message.bot, refreshed.city_ids if refreshed else [])
    await _render_staff_card(cq, refreshed, city_names, state)
    await cq.answer("Updated")


# :       ,     .
@router.callback_query(
    F.data.in_(
        {
            "adm:staff:new:GLOBAL_ADMIN",
            "adm:staff:new:CITY_ADMIN",
            "adm:staff:new:LOGIST",
        }
    ),
    StaffRoleFilter({StaffRole.GLOBAL_ADMIN}),
)
async def access_code_new_start(cq: CallbackQuery, state: FSMContext, staff: StaffUser) -> None:
    role_token = cq.data.split(":")[3]
    role = StaffRole(role_token)
    await state.clear()
    if role is StaffRole.GLOBAL_ADMIN:
        service = _staff_service(cq.message.bot)
        code = await service.create_access_code(
            role=role,
            city_ids=[],
            created_by_staff_id=staff.id,
            expires_at=None,
            comment=None,
        )
        await _show_code_card(cq, code)
        await cq.answer()
        return
    cities = await _load_cities(cq.message.bot)
    await state.set_state(AccessCodeNewFSM.city_select)
    await state.update_data(
        role=role.value,
        cities=_serialize_cities(cities),
        selected=[],
        page=1,
    )
    await _render_city_selector(
        cq,
        prefix="adm:staff:new:city",
        cities=cities,
        selected=[],
        page=1,
        title=f"Select cities for {_role_label(role)}",
        show_done=True,
        allow_empty=False,
    )
    await cq.answer()


async def _show_code_card(cq: CallbackQuery, code: StaffAccessCode) -> None:
    city_names = await _resolve_city_names(cq.message.bot, code.city_ids)
    lines = [
        "<b>Access code</b>",
        f"Role: {_role_label(code.role)}",
        f"Cities: {_format_city_line(city_names)}",
        f"Code: <code>{code.code}</code>",
    ]
    if code.expires_at:
        lines.append(code.expires_at.strftime("Valid until: %Y-%m-%d %H:%M"))
    status = "used" if code.used_at else ("revoked" if bool(code.revoked_at) else "active")
    lines.append(f"Status: {status}")
    kb = InlineKeyboardBuilder()
    if not code.used_at and not bool(code.revoked_at):
        kb.button(text="Revoke", callback_data=f"adm:staff:revoke:{code.id}")
    kb.button(text="Menu", callback_data="adm:staff:menu")
    kb.adjust(1)
    await cq.message.edit_text(
        "\n".join(lines),
        reply_markup=kb.as_markup(),
    )


@router.callback_query(
    F.data.startswith("adm:staff:new:city:"),
    StaffRoleFilter({StaffRole.GLOBAL_ADMIN}),
    StateFilter(AccessCodeNewFSM.city_select),
)
async def access_code_city_action(cq: CallbackQuery, state: FSMContext, staff: StaffUser) -> None:
    parts = cq.data.split(":")
    action = parts[4]
    data = await state.get_data()
    cities = _deserialize_cities(data.get("cities", []))
    selected = set(data.get("selected", []))
    page = int(data.get("page", 1))
    role = StaffRole(data.get("role", StaffRole.CITY_ADMIN.value))
    if action == "pick":
        city_id = int(parts[5])
        if city_id in selected:
            selected.remove(city_id)
        else:
            selected.add(city_id)
        await state.update_data(selected=list(selected))
        await _render_city_selector(
            cq,
            prefix="adm:staff:new:city",
            cities=cities,
            selected=selected,
            page=page,
            title=f"Select cities for {_role_label(role)}",
            show_done=True,
            allow_empty=False,
        )
        await cq.answer()
        return
    if action == "page":
        page = max(1, int(parts[5]))
        await state.update_data(page=page)
        await _render_city_selector(
            cq,
            prefix="adm:staff:new:city",
            cities=cities,
            selected=selected,
            page=page,
            title=f"Select cities for {_role_label(role)}",
            show_done=True,
            allow_empty=False,
        )
        await cq.answer()
        return
    if action == "cancel":
        await state.clear()
        await _send_staff_menu(cq)
        await cq.answer("Cancelled")
        return
    if action == "done":
        if not selected:
            await cq.answer("Select at least one city", show_alert=True)
            return
        service = _staff_service(cq.message.bot)
        code = await service.create_access_code(
            role=role,
            city_ids=selected,
            created_by_staff_id=staff.id,
            expires_at=None,
            comment=None,
        )
        await state.clear()
        await _show_code_card(cq, code)
        await cq.answer("Created")
        return
    await cq.answer()


@router.callback_query(
    F.data.startswith("adm:staff:code:"),
    StaffRoleFilter({StaffRole.GLOBAL_ADMIN}),
)
async def access_code_card(cq: CallbackQuery) -> None:
    code_id = int(cq.data.split(":")[3])
    service = _staff_service(cq.message.bot)
    code = await service.get_access_code(code_id)
    if not code:
        await cq.answer("Code not found", show_alert=True)
        return
    await _show_code_card(cq, code)
    await cq.answer()


@router.callback_query(
    F.data.startswith("adm:staff:revoke:"),
    StaffRoleFilter({StaffRole.GLOBAL_ADMIN}),
)
async def access_code_revoke(cq: CallbackQuery, staff: StaffUser) -> None:
    code_id = int(cq.data.split(":")[3])
    service = _staff_service(cq.message.bot)
    ok = await service.revoke_access_code(code_id, by_staff_id=staff.id)
    if not ok:
        await cq.answer("Cannot revoke", show_alert=True)
        return
    code = await service.get_access_code(code_id)
    if code:
        await _show_code_card(cq, code)
    await cq.answer("Revoked")


@router.callback_query(
    F.data.startswith("adm:staff:edit:cities:"),
    StaffRoleFilter({StaffRole.GLOBAL_ADMIN}),
)
async def staff_edit_cities(cq: CallbackQuery, state: FSMContext) -> None:
    parts = cq.data.split(":")
    staff_id = int(parts[4])
    action = parts[5] if len(parts) > 5 else "start"
    service = _staff_service(cq.message.bot)
    member = await service.get_staff_member(staff_id)
    if not member:
        await cq.answer("Not found", show_alert=True)
        return
    data = await state.get_data()
    cities = _deserialize_cities(data.get("edit_cities", []))
    if not cities:
        cities = await _load_cities(cq.message.bot)
    selected = set(data.get("edit_selected", member.city_ids))
    page = int(data.get("edit_page", 1))
    if action == "start":
        await state.set_state(StaffCityEditFSM.action)
        await state.update_data(edit_staff_id=staff_id, edit_cities=_serialize_cities(cities), edit_selected=list(selected), edit_page=page)
    elif action == "pick":
        city_id = int(parts[6])
        if city_id in selected:
            selected.remove(city_id)
        else:
            selected.add(city_id)
        await state.update_data(edit_selected=list(selected))
    elif action == "page":
        page = max(1, int(parts[6]))
        await state.update_data(edit_page=page)
    elif action == "cancel":
        await state.clear()
        city_names = await _resolve_city_names(cq.message.bot, member.city_ids)
        await _render_staff_card(cq, member, city_names, state)
        await cq.answer("Cancelled")
        return
    elif action == "done":
        await service.set_staff_cities(staff_id, selected)
        await state.clear()
        refreshed = await service.get_staff_member(staff_id)
        city_names = await _resolve_city_names(cq.message.bot, refreshed.city_ids if refreshed else [])
        await _render_staff_card(cq, refreshed, city_names, state)
        await cq.answer("Saved")
        return
    await _render_city_selector(
        cq,
        prefix=f"adm:staff:edit:cities:{staff_id}",
        cities=cities,
        selected=selected,
        page=page,
        title=f"Edit cities for {_role_label(member.role)} #{member.id}",
        show_done=True,
        allow_empty=True,
    )
    await cq.answer()

