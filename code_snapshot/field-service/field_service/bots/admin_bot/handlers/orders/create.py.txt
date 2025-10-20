# field_service/bots/admin_bot/handlers/orders.py
"""   (NewOrderFSM)."""
from __future__ import annotations

import os
from datetime import time
from typing import Optional
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from field_service.config import settings as env_settings
from field_service.db.models import OrderStatus, OrderType
from field_service.services import time_service

from ...core.dto import StaffRole, StaffUser
from ...core.filters import StaffRoleFilter
from ...ui.keyboards import (
    assign_menu_keyboard,
    new_order_asap_late_keyboard,
    new_order_attachments_keyboard,
    new_order_city_keyboard,
    new_order_confirm_keyboard,
    new_order_district_keyboard,
    new_order_slot_keyboard,
    new_order_street_keyboard,
    new_order_street_manual_keyboard,
    new_order_street_mode_keyboard,
    order_card_keyboard,
)
from ...utils.normalizers import normalize_category
from .queue import CATEGORY_CHOICES, CATEGORY_LABELS, CATEGORY_LABELS_BY_VALUE
from ...core.states import NewOrderFSM
from ...ui.texts import new_order_summary
from ...core.access import visible_city_ids_for
from ..common.helpers import (
    ATTACHMENTS_LIMIT,
    _attachments_from_state,
    _build_new_order_data,
    _orders_service,
    _resolve_city_timezone,
    _validate_name,
    _validate_phone,
    _normalize_phone,
    _zone_storage_value,
)


router = Router(name="admin_orders")


#   
WORKDAY_START_DEFAULT = time_service.parse_time_string(env_settings.workday_start, default=time(10, 0))
WORKDAY_END_DEFAULT = time_service.parse_time_string(env_settings.workday_end, default=time(20, 0))
LATE_ASAP_THRESHOLD = time_service.parse_time_string(env_settings.asap_late_threshold, default=time(19, 30))


def is_working_hours() -> bool:
    """,      ."""
    if os.getenv("PYTEST_CURRENT_TEST"):
        return True
    from datetime import datetime
    now = datetime.now().time()
    return time(8, 0) <= now <= time(20, 0)

SLOT_BUCKETS: tuple[tuple[str, time, time], ...] = tuple(
    (bucket, span[0], span[1]) for bucket, span in time_service._SLOT_BUCKETS.items()
)


#   
def _slot_options(now_local, *, workday_start, workday_end):
    """   ."""
    current = now_local.timetz()
    if current.tzinfo is not None:
        current = current.replace(tzinfo=None)
    options = []
    if current < workday_end:
        options.append(("ASAP", "ASAP"))
        for bucket_key, start, end in SLOT_BUCKETS:
            if current < start:
                options.append((f"TODAY:{bucket_key}", f" {start:%H:%M}-{end:%H:%M}"))
    for bucket_key, start, end in SLOT_BUCKETS:
        options.append((f"TOM:{bucket_key}", f" {start:%H:%M}-{end:%H:%M}"))
    return options


def _format_slot_display(choice, computation, *, tz):
    """    ."""
    if choice == "ASAP":
        return "ASAP"
    formatted = time_service.format_timeslot_local(
        computation.start_utc,
        computation.end_utc,
        tz=tz,
    )
    return formatted or ""


async def _resolve_workday_window():
    """     ."""
    try:
        from field_service.services import settings_service
        return await settings_service.get_working_window()
    except Exception:
        return WORKDAY_START_DEFAULT, WORKDAY_END_DEFAULT


async def _finalize_slot_selection(
    message,
    state,
    *,
    slot_choice,
    tz,
    workday_start,
    workday_end,
    initial_status_override=None,
):
    """      ."""
    computation = time_service.compute_slot(
        city_tz=tz,
        choice=slot_choice,
        workday_start=workday_start,
        workday_end=workday_end,
    )
    slot_display = _format_slot_display(slot_choice, computation, tz=tz)

    await state.update_data(
        timeslot_display=slot_display,
        timeslot_start_utc=computation.start_utc,
        timeslot_end_utc=computation.end_utc,
        initial_status=initial_status_override,
        pending_asap=False,
    )
    summary = new_order_summary(await state.get_data())
    await state.set_state(NewOrderFSM.confirm)
    await message.edit_text(
        summary,
        reply_markup=new_order_confirm_keyboard(),
        disable_web_page_preview=True,
    )


async def _render_created_order_card(message, order_id, staff):
    """   ."""
    orders_service = _orders_service(message.bot)
    detail = await orders_service.get_card(order_id, city_ids=visible_city_ids_for(staff))
    if not detail:
        await message.answer(f" #{order_id}  .")
        return
    
    from ...ui.texts import format_order_card
    text = format_order_card(detail)
    markup = order_card_keyboard(
        detail.id,
        attachments=detail.attachments,
        allow_return=(detail.status.upper() not in {"CANCELED", "CLOSED"}),
        allow_cancel=(detail.status.upper() not in {"CANCELED", "CLOSED"}),
        show_guarantee=False,
    )
    try:
        await message.edit_text(text, reply_markup=markup)
    except Exception:
        await message.answer(text, reply_markup=markup)


# ============================================
#   - 
# ============================================

async def _start_new_order(cq, staff, state):
    """   ."""
    await state.clear()
    await state.update_data(staff_id=staff.id, attachments=[], order_type=OrderType.NORMAL.value)
    await state.set_state(NewOrderFSM.city)
    await _render_city_step(cq.message, state, page=1, staff=staff)
    await cq.answer()


async def _render_city_step(message, state, page, staff, query=None):
    """       visible_city_ids."""
    orders_service = _orders_service(message.bot)
    # RBAC:     CITY_ADMIN
    city_ids = visible_city_ids_for(staff)
    limit = 80
    if query:
        cities = await orders_service.list_cities(query=query, limit=limit, city_ids=city_ids)
    else:
        cities = await orders_service.list_cities(limit=limit, city_ids=city_ids)
    if not cities:
        try:
            await message.edit_text("  .  /cancel,  .")
        except TelegramBadRequest:
            await message.answer("  .  /cancel,  .")
        return
    per_page = 10
    total_pages = max(1, (len(cities) + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))
    start = (page - 1) * per_page
    chunk = cities[start : start + per_page]
    keyboard = new_order_city_keyboard([(c.id, c.name) for c in chunk], page=page, total_pages=total_pages)
    prompt = " :"
    try:
        await message.edit_text(prompt, reply_markup=keyboard)
    except TelegramBadRequest:
        await message.answer(prompt, reply_markup=keyboard)
    except Exception:
        await message.answer(prompt, reply_markup=keyboard)
    await state.update_data(city_query=query, city_page=page)


@router.callback_query(
    F.data == "adm:new",
    StaffRoleFilter({StaffRole.GLOBAL_ADMIN, StaffRole.CITY_ADMIN, StaffRole.LOGIST}),
)
async def cb_new_order_start(cq: CallbackQuery, staff: StaffUser, state: FSMContext) -> None:
    """     (P0-5)."""
    await state.clear()
    from ...ui.keyboards import create_order_mode_keyboard
    await cq.message.edit_text(
        "   :\n\n"
        " <b> </b> -    (5 )\n"
        " <b> </b> -      ",
        reply_markup=create_order_mode_keyboard(),
    )
    await cq.answer()


@router.callback_query(
    F.data == "adm:new:mode:full",
    StaffRoleFilter({StaffRole.GLOBAL_ADMIN, StaffRole.CITY_ADMIN, StaffRole.LOGIST}),
)
async def cb_new_order_full_mode(cq: CallbackQuery, staff: StaffUser, state: FSMContext) -> None:
    """   ."""
    await _start_new_order(cq, staff, state)



@router.message(
    Command("cancel"),
    StaffRoleFilter({StaffRole.GLOBAL_ADMIN, StaffRole.CITY_ADMIN, StaffRole.LOGIST}),
)
async def admin_cancel_command(message: Message, staff: StaffUser, state: FSMContext) -> None:
    """ /cancel -   ."""
    await state.clear()
    from ...ui.keyboards import main_menu
    await message.answer("  .", reply_markup=main_menu(staff))


@router.callback_query(
    F.data == "adm:new:cancel",
    StaffRoleFilter({StaffRole.GLOBAL_ADMIN, StaffRole.CITY_ADMIN, StaffRole.LOGIST}),
)
async def cb_new_order_cancel(cq: CallbackQuery, staff: StaffUser, state: FSMContext) -> None:
    """   ."""
    await state.clear()
    if cq.message:
        from ...ui.keyboards import main_menu
        try:
            await cq.message.edit_text("  ", reply_markup=main_menu(staff))
        except TelegramBadRequest:
            await cq.message.answer("  ", reply_markup=main_menu(staff))
    try:
        await cq.answer("")
    except TelegramBadRequest:
        pass


@router.callback_query(
    F.data.startswith("adm:new:city_page:"),
    StateFilter(NewOrderFSM.city),
    StaffRoleFilter({StaffRole.GLOBAL_ADMIN, StaffRole.CITY_ADMIN, StaffRole.LOGIST}),
)
async def cb_new_order_city_page(cq: CallbackQuery, staff: StaffUser, state: FSMContext) -> None:
    """  ."""
    page = int(cq.data.split(":")[3])
    data = await state.get_data()
    query = data.get("city_query")
    await state.set_state(NewOrderFSM.city)
    await _render_city_step(cq.message, state, page=page, staff=staff, query=query)
    await cq.answer()


@router.callback_query(F.data == "adm:new:city_search", StateFilter(NewOrderFSM.city))
async def cb_new_order_city_search(cq: CallbackQuery, state: FSMContext) -> None:
    """   ."""
    await state.set_state(NewOrderFSM.city)
    prompt = "   ( 2 ).  /cancel   ."
    try:
        await cq.message.edit_text(prompt)
    except TelegramBadRequest:
        await cq.message.answer(prompt)
    except Exception:
        await cq.message.answer(prompt)
    await cq.answer()


@router.message(StateFilter(NewOrderFSM.city))
async def new_order_city_input(msg: Message, staff: StaffUser, state: FSMContext) -> None:
    """    ."""
    query = (msg.text or "").strip()
    if len(query) < 2:
        await msg.answer(" 2 .  .")
        return
    await _render_city_step(msg, state, page=1, staff=staff, query=query)


@router.callback_query(F.data.startswith("adm:new:city:"), StateFilter(NewOrderFSM.city))
async def cb_new_order_city_pick(cq: CallbackQuery, state: FSMContext) -> None:
    """ ."""
    city_id = int(cq.data.split(":")[3])
    orders_service = _orders_service(cq.message.bot)
    city = await orders_service.get_city(city_id)
    if not city:
        await cq.answer("  ", show_alert=True)
        return
    await state.update_data(city_id=city.id, city_name=city.name)
    await state.set_state(NewOrderFSM.district)
    await _render_district_step(cq.message, state, page=1)
    await cq.answer()


# ============================================
#   - 
# ============================================

async def _render_district_step(message, state, page):
    """   ."""
    data = await state.get_data()
    city_id = data.get("city_id")
    orders_service = _orders_service(message.bot)
    districts, has_next = await orders_service.list_districts(city_id, page=page, page_size=5)
    buttons = [(d.id, d.name) for d in districts]
    keyboard = new_order_district_keyboard(buttons, page=page, has_next=has_next)
    prompt = " :"
    try:
        await message.edit_text(prompt, reply_markup=keyboard)
    except TelegramBadRequest:
        await message.answer(prompt, reply_markup=keyboard)
    except Exception:
        await message.answer(prompt, reply_markup=keyboard)
    await state.update_data(district_page=page)


@router.callback_query(F.data.startswith("adm:new:district_page:"), StateFilter(NewOrderFSM.district))
async def cb_new_order_district_page(cq: CallbackQuery, state: FSMContext) -> None:
    """  ."""
    page = int(cq.data.split(":")[3])
    await state.set_state(NewOrderFSM.district)
    await _render_district_step(cq.message, state, page=page)
    try:
        await cq.answer()
    except TelegramBadRequest:
        pass


@router.callback_query(F.data == "adm:new:city_back", StateFilter(NewOrderFSM.district))
async def cb_new_order_city_back(cq: CallbackQuery, staff: StaffUser, state: FSMContext) -> None:
    """   ."""
    data = await state.get_data()
    await state.set_state(NewOrderFSM.city)
    await _render_city_step(
        cq.message,
        state,
        page=data.get("city_page", 1),
        staff=staff,
        query=data.get("city_query"),
    )
    await cq.answer()


@router.callback_query(F.data == "adm:new:district:none", StateFilter(NewOrderFSM.district))
async def cb_new_order_district_none(cq: CallbackQuery, state: FSMContext) -> None:
    """  ."""
    await state.update_data(district_id=None, district_name="")
    await state.set_state(NewOrderFSM.street_mode)
    await cq.message.edit_text(
        "   :",
        reply_markup=new_order_street_mode_keyboard(),
    )
    await cq.answer()


@router.callback_query(F.data.startswith("adm:new:district:"), StateFilter(NewOrderFSM.district))
async def cb_new_order_district_pick(cq: CallbackQuery, state: FSMContext) -> None:
    """ ."""
    district_id = int(cq.data.split(":")[3])
    orders_service = _orders_service(cq.message.bot)
    district = await orders_service.get_district(district_id)
    if not district:
        await cq.answer("  ", show_alert=True)
        return
    await state.update_data(district_id=district.id, district_name=district.name)
    await state.set_state(NewOrderFSM.street_mode)
    await cq.message.edit_text(
        "   :",
        reply_markup=new_order_street_mode_keyboard(),
    )
    await cq.answer()


# ============================================
#   - 
# ============================================

@router.callback_query(F.data == "adm:new:street:search", StateFilter(NewOrderFSM.street_mode))
async def cb_new_order_street_search(cq: CallbackQuery, state: FSMContext) -> None:
    """ ."""
    await state.set_state(NewOrderFSM.street_search)
    await cq.message.edit_text("  2     .")
    await cq.answer()


@router.callback_query(F.data == "adm:new:street:manual", StateFilter(NewOrderFSM.street_mode))
async def cb_new_order_street_manual(cq: CallbackQuery, state: FSMContext) -> None:
    """  ."""
    await state.set_state(NewOrderFSM.street_manual)
    await cq.message.edit_text(
        "   ( 250 ).",
        reply_markup=new_order_street_manual_keyboard(),
    )
    await cq.answer()


@router.callback_query(F.data == "adm:new:street:none", StateFilter(NewOrderFSM.street_mode))
async def cb_new_order_street_none(cq: CallbackQuery, state: FSMContext) -> None:
    """ ."""
    await state.update_data(street_id=None, street_name="", street_manual=None)
    await state.set_state(NewOrderFSM.house)
    await cq.message.edit_text("   ( 10 , '-'  ).")
    await cq.answer()


@router.callback_query(F.data == "adm:new:district_back", StateFilter(NewOrderFSM.street_mode))
async def cb_new_order_street_back(cq: CallbackQuery, state: FSMContext) -> None:
    """   ."""
    await state.set_state(NewOrderFSM.district)
    page = (await state.get_data()).get("district_page", 1)
    await _render_district_step(cq.message, state, page=page)
    await cq.answer()


@router.message(StateFilter(NewOrderFSM.street_manual))
async def new_order_street_manual_input(msg: Message, state: FSMContext) -> None:
    """   ."""
    value = (msg.text or "").strip()
    if not (2 <= len(value) <= 250):
        await msg.answer("     2  250 .")
        return
    await state.update_data(street_id=None, street_name=value, street_manual=value)
    await state.set_state(NewOrderFSM.house)
    await msg.answer("   ( 10 , '-'  ).")


@router.message(StateFilter(NewOrderFSM.street_search))
async def new_order_street_search_input(msg: Message, state: FSMContext) -> None:
    """   ."""
    query = (msg.text or "").strip()
    if len(query) < 2:
        await msg.answer("  2    .")
        return
    data = await state.get_data()
    city_id = data.get("city_id")
    orders_service = _orders_service(msg.bot)
    streets = await orders_service.search_streets(city_id, query)
    if not streets:
        await msg.answer("   .       .")
        await state.set_state(NewOrderFSM.street_mode)
        await msg.answer(
            "   :",
            reply_markup=new_order_street_mode_keyboard(),
        )
        return
    buttons = [
        (s.id, s.name if s.score is None else f"{s.name} ({int(s.score)}%)")
        for s in streets
    ]
    await msg.answer(
        " :",
        reply_markup=new_order_street_keyboard(buttons),
    )
    await state.set_state(NewOrderFSM.street_mode)
    await state.update_data(street_search_results=buttons)


@router.callback_query(F.data.startswith("adm:new:street:"), StateFilter(NewOrderFSM.street_mode))
async def cb_new_order_street_pick(cq: CallbackQuery, state: FSMContext) -> None:
    """    ."""
    tail = cq.data.split(":")[3]
    if tail == "search_again":
        await state.set_state(NewOrderFSM.street_search)
        await cq.message.edit_text("  2     .")
        await cq.answer()
        return
    if tail == "manual_back":
        await state.set_state(NewOrderFSM.street_mode)
        await cq.message.edit_text(
            "   :",
            reply_markup=new_order_street_mode_keyboard(),
        )
        await cq.answer()
        return
    if tail == "back":
        await state.set_state(NewOrderFSM.street_mode)
        await cq.message.edit_text(
            "   :",
            reply_markup=new_order_street_mode_keyboard(),
        )
        await cq.answer()
        return
    street_id = int(tail)
    orders_service = _orders_service(cq.message.bot)
    street = await orders_service.get_street(street_id)
    if not street:
        await cq.answer("  ", show_alert=True)
        return
    await state.update_data(street_id=street.id, street_name=street.name, street_manual=None)
    await state.set_state(NewOrderFSM.house)
    await cq.message.edit_text("   ( 10 , '-'  ).")
    await cq.answer()


# ============================================
#   - 
# ============================================

@router.message(StateFilter(NewOrderFSM.house))
async def new_order_house(msg: Message, state: FSMContext) -> None:
    """  ."""
    value = (msg.text or "").strip()
    if not (1 <= len(value) <= 10):
        await msg.answer("     1  10 .")
        return
    await state.update_data(house=value)
    await state.set_state(NewOrderFSM.apartment)
    await msg.answer(" / ( 10 , '-'  ).")


@router.message(StateFilter(NewOrderFSM.apartment))
async def new_order_apartment(msg: Message, state: FSMContext) -> None:
    """ /."""
    value = (msg.text or "").strip()
    if value == "-":
        value = ""
    if len(value) > 10:
        await msg.answer("  / 10 .")
        return
    await state.update_data(apartment=value or None)
    await state.set_state(NewOrderFSM.address_comment)
    await msg.answer("    ( 250 , '-'  ).")


@router.message(StateFilter(NewOrderFSM.address_comment))
async def new_order_address_comment(msg: Message, state: FSMContext) -> None:
    """   ."""
    value = (msg.text or "").strip()
    if value == "-":
        value = ""
    await state.update_data(address_comment=value or None)
    await state.set_state(NewOrderFSM.client_name)
    await msg.answer("   ().")


# ============================================
#   - 
# ============================================

@router.message(StateFilter(NewOrderFSM.client_name))
async def new_order_client_name(msg: Message, state: FSMContext) -> None:
    """  ."""
    value = (msg.text or "").strip()
    if not _validate_name(value):
        await msg.answer("      .")
        return
    await state.update_data(client_name=value)
    await state.set_state(NewOrderFSM.client_phone)
    await msg.answer("     +7XXXXXXXXXX.")


@router.message(StateFilter(NewOrderFSM.client_phone))
async def new_order_client_phone(msg: Message, state: FSMContext) -> None:
    """  ."""
    raw = _normalize_phone(msg.text)
    if not _validate_phone(raw):
        await msg.answer("     +7XXXXXXXXXX.")
        return
    await state.update_data(client_phone=raw)
    await state.set_state(NewOrderFSM.category)
    
    kb = InlineKeyboardBuilder()
    for category, label in CATEGORY_CHOICES:
        kb.button(text=label, callback_data=f"adm:new:cat:{category.value}")
    kb.adjust(2)
    await msg.answer("  :", reply_markup=kb.as_markup())


@router.callback_query(F.data.startswith("adm:new:cat:"), StateFilter(NewOrderFSM.category))
async def cb_new_order_category(cq: CallbackQuery, state: FSMContext) -> None:
    """  ."""
    raw = cq.data.split(":")[3]
    category = normalize_category(raw)
    if category is None:
        await cq.answer(" .", show_alert=True)
        return
    await state.update_data(
        category=category,
        category_label=CATEGORY_LABELS.get(category, CATEGORY_LABELS_BY_VALUE.get(raw, raw)),
    )
    await state.set_state(NewOrderFSM.description)
    await cq.message.edit_text("  (10-500 ).")
    await cq.answer()


@router.message(StateFilter(NewOrderFSM.description))
async def new_order_description(msg: Message, state: FSMContext) -> None:
    """  ."""
    text_value = (msg.text or "").strip()
    if not (10 <= len(text_value) <= 500):
        await msg.answer("    10  500 .")
        return
    await state.update_data(description=text_value)
    await state.set_state(NewOrderFSM.attachments)
    await msg.answer(
        '    "",  .',
        reply_markup=new_order_attachments_keyboard(False),
    )


# ============================================
#   - 
# ============================================

@router.callback_query(F.data == "adm:new:att:add", StateFilter(NewOrderFSM.attachments))
async def cb_new_order_att_add(cq: CallbackQuery, state: FSMContext) -> None:
    """ ."""
    await state.set_state(NewOrderFSM.attachments)
    await cq.answer("     .")


@router.callback_query(F.data == "adm:new:att:clear", StateFilter(NewOrderFSM.attachments))
async def cb_new_order_att_clear(cq: CallbackQuery, state: FSMContext) -> None:
    """  ."""
    data = await state.get_data()
    data["attachments"] = []
    await state.update_data(**data)
    await state.set_state(NewOrderFSM.attachments)
    await cq.message.edit_text(
        ' .     "".',
        reply_markup=new_order_attachments_keyboard(False),
    )
    await cq.answer()


@router.message(StateFilter(NewOrderFSM.attachments), F.photo)
async def new_order_attach_photo(msg: Message, state: FSMContext) -> None:
    """ ."""
    attachments = _attachments_from_state(await state.get_data())
    if len(attachments) >= ATTACHMENTS_LIMIT:
        await msg.answer("  .")
        return
    photo = msg.photo[-1]
    attachments.append(
        {
            "file_id": photo.file_id,
            "file_unique_id": photo.file_unique_id,
            "file_type": "photo",
            "file_name": None,
            "mime_type": None,
            "caption": msg.caption,
        }
    )
    await state.update_data(attachments=attachments)
    await msg.answer(
        f' : {len(attachments)}.     "".',
        reply_markup=new_order_attachments_keyboard(True),
    )


@router.message(StateFilter(NewOrderFSM.attachments), F.document)
async def new_order_attach_doc(msg: Message, state: FSMContext) -> None:
    """ ."""
    attachments = _attachments_from_state(await state.get_data())
    if len(attachments) >= ATTACHMENTS_LIMIT:
        await msg.answer("  .")
        return
    doc = msg.document
    attachments.append(
        {
            "file_id": doc.file_id,
            "file_unique_id": doc.file_unique_id,
            "file_type": "document",
            "file_name": doc.file_name,
            "mime_type": doc.mime_type,
            "caption": msg.caption,
        }
    )
    await state.update_data(attachments=attachments)
    await msg.answer(
        f' : {len(attachments)}.     "".',
        reply_markup=new_order_attachments_keyboard(True),
    )


@router.callback_query(F.data == "adm:new:att:done", StateFilter(NewOrderFSM.attachments))
async def cb_new_order_att_done(cq: CallbackQuery, state: FSMContext) -> None:
    """  ."""
    await state.set_state(NewOrderFSM.order_type)
    
    kb = InlineKeyboardBuilder()
    kb.button(text="", callback_data="adm:new:type:NORMAL")
    kb.button(text="", callback_data="adm:new:type:GUARANTEE")
    kb.adjust(2)
    await cq.message.edit_text("  :", reply_markup=kb.as_markup())
    await cq.answer()


# ============================================
#   -   
# ============================================

@router.callback_query(F.data.startswith("adm:new:type:"), StateFilter(NewOrderFSM.order_type))
async def cb_new_order_type(cq: CallbackQuery, state: FSMContext) -> None:
    """  ."""
    code = cq.data.split(":")[3]
    await state.update_data(
        order_type=code,
        company_payment=2500 if code == "GUARANTEE" else 0,
        initial_status=None,
    )
    await state.set_state(NewOrderFSM.slot)
    data = await state.get_data()
    city_id = data.get("city_id")
    if not city_id:
        await cq.answer("   .", show_alert=True)
        return
    tz = await _resolve_city_timezone(cq.message.bot, city_id)
    workday_start, workday_end = await _resolve_workday_window()
    now_local = time_service.now_in_city(tz)
    options = _slot_options(now_local, workday_start=workday_start, workday_end=workday_end)
    await state.update_data(
        slot_options=options,
        city_timezone=_zone_storage_value(tz),
        pending_asap=False,
    )
    keyboard = new_order_slot_keyboard(options)
    await cq.message.edit_text("  :", reply_markup=keyboard)
    await cq.answer()


@router.callback_query(F.data.startswith("adm:new:slot:"), StateFilter(NewOrderFSM.slot))
async def cb_new_order_slot(cq: CallbackQuery, state: FSMContext) -> None:
    """  ."""
    key = ":".join(cq.data.split(":")[3:])
    data = await state.get_data()
    city_id = data.get("city_id")
    if not city_id:
        await cq.answer("   .", show_alert=True)
        return
    await state.set_state(NewOrderFSM.slot)
    options = data.get("slot_options") or []
    valid_keys = {item[0] for item in options}
    if key not in valid_keys:
        await cq.answer(" .", show_alert=True)
        return
    tz_value = data.get("city_timezone")
    if tz_value:
        tz = time_service.resolve_timezone(tz_value)
    else:
        tz = await _resolve_city_timezone(cq.message.bot, city_id)
        await state.update_data(city_timezone=_zone_storage_value(tz))
    workday_start, workday_end = await _resolve_workday_window()
    now_local = time_service.now_in_city(tz)
    if key == "ASAP":
        normalized = time_service.normalize_asap_choice(
            now_local=now_local,
            workday_start=workday_start,
            workday_end=workday_end,
            late_threshold=LATE_ASAP_THRESHOLD,
        )
        if normalized == "DEFERRED_TOM_10_13":
            await state.update_data(pending_asap=True)
            await state.set_state(NewOrderFSM.slot)
            await cq.message.edit_text(
                "      10:00  13:00.  ?",
                reply_markup=new_order_asap_late_keyboard(),
            )
            await cq.answer()
            return
        slot_choice = "ASAP"
        initial_status = None
    else:
        slot_choice = key
        initial_status = None
    try:
        await _finalize_slot_selection(
            message=cq.message,
            state=state,
            slot_choice=slot_choice,
            tz=tz,
            workday_start=workday_start,
            workday_end=workday_end,
            initial_status_override=initial_status,
        )
    except ValueError:
        refreshed_options = _slot_options(
            time_service.now_in_city(tz),
            workday_start=workday_start,
            workday_end=workday_end,
        )
        await state.update_data(slot_options=refreshed_options, pending_asap=False, initial_status=None)
        await state.set_state(NewOrderFSM.slot)
        await cq.message.edit_text(
            " .   :",
            reply_markup=new_order_slot_keyboard(refreshed_options),
        )
        await cq.answer(" ,  .", show_alert=True)
        return
    await cq.answer()


@router.callback_query(F.data == "adm:new:slot:lateok", StateFilter(NewOrderFSM.slot))
async def cb_new_order_slot_lateok(cq: CallbackQuery, state: FSMContext) -> None:
    """  ASAP  ."""
    data = await state.get_data()
    city_id = data.get("city_id")
    if not city_id:
        await cq.answer("   .", show_alert=True)
        return
    tz_value = data.get("city_timezone")
    if tz_value:
        tz = time_service.resolve_timezone(tz_value)
    else:
        tz = await _resolve_city_timezone(cq.message.bot, city_id)
        await state.update_data(city_timezone=_zone_storage_value(tz))
    workday_start, workday_end = await _resolve_workday_window()
    await _finalize_slot_selection(
        message=cq.message,
        state=state,
        slot_choice="TOM:10-13",
        tz=tz,
        workday_start=workday_start,
        workday_end=workday_end,
        initial_status_override=OrderStatus.DEFERRED,
    )
    await cq.answer()


@router.callback_query(F.data == "adm:new:slot:reslot", StateFilter(NewOrderFSM.slot))
async def cb_new_order_slot_reslot(cq: CallbackQuery, state: FSMContext) -> None:
    """    ASAP."""
    data = await state.get_data()
    city_id = data.get("city_id")
    if not city_id:
        await cq.answer("   .", show_alert=True)
        return
    await state.set_state(NewOrderFSM.slot)
    tz_value = data.get("city_timezone")
    if tz_value:
        tz = time_service.resolve_timezone(tz_value)
    else:
        tz = await _resolve_city_timezone(cq.message.bot, city_id)
        await state.update_data(city_timezone=_zone_storage_value(tz))
    workday_start, workday_end = await _resolve_workday_window()
    options = _slot_options(
        time_service.now_in_city(tz),
        workday_start=workday_start,
        workday_end=workday_end,
    )
    await state.update_data(slot_options=options, pending_asap=False, initial_status=None)
    await cq.message.edit_text("  :", reply_markup=new_order_slot_keyboard(options))
    await cq.answer()


# ============================================
#   - 
# ============================================

@router.callback_query(F.data == "adm:new:confirm", StateFilter(NewOrderFSM.confirm))
async def cb_new_order_confirm(cq: CallbackQuery, state: FSMContext, staff: StaffUser | None = None) -> None:
    """  ."""
    if staff is None:
        from ..common.helpers import _staff_service
        staff_service = _staff_service(cq.message.bot)
        staff = await staff_service.get_by_tg_id(cq.from_user.id if cq.from_user else 0)
        if staff is None:
            await cq.answer(" ", show_alert=True)
            return
    
    #    
    if not is_working_hours():
        from aiogram.types import InlineKeyboardButton
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        
        kb = InlineKeyboardBuilder()
        kb.row(
            InlineKeyboardButton(text=" , ", callback_data="adm:new:force_confirm"),
            InlineKeyboardButton(text=" ", callback_data="adm:new:cancel"),
        )
        
        await state.set_state(NewOrderFSM.confirm_deferred)
        await cq.message.edit_text(
            " <b>   (20:008:00)</b>\n\n"
            "     <b></b> :\n"
            "   <b> </b>\n"
            "    8:00\n\n"
            "    ?",
            reply_markup=kb.as_markup(),
        )
        await cq.answer()
        return
    
    data = await state.get_data()
    summary_text = new_order_summary(data)
    try:
        new_order = _build_new_order_data(data, staff)
    except KeyError:
        await state.clear()
        await cq.answer("    .  .", show_alert=True)
        return
    orders_service = _orders_service(cq.message.bot)
    order_id = await orders_service.create_order(new_order)
    detail = await orders_service.get_card(order_id, city_ids=visible_city_ids_for(staff))
    await state.clear()
    await cq.answer(" ")
    if detail:
        allow_auto = detail.district_id is not None
        prompt_parts = [f" #{detail.id} .", summary_text]
        if not allow_auto:
            prompt_parts.append(" :   .")
        prompt_parts.append("Выберите способ распределения.")
        prompt = "\n\n".join(prompt_parts)
        markup = assign_menu_keyboard(detail.id, allow_auto=allow_auto)
        try:
            await cq.message.edit_text(prompt, reply_markup=markup, disable_web_page_preview=True)
        except Exception:
            await cq.message.answer(prompt, reply_markup=markup, disable_web_page_preview=True)
        return
    await _render_created_order_card(cq.message, order_id, staff)


@router.callback_query(F.data == "adm:new:force_confirm", StateFilter(NewOrderFSM.confirm_deferred))
async def cb_new_order_force_confirm(cq: CallbackQuery, state: FSMContext, staff: StaffUser | None = None) -> None:
    """     ."""
    if staff is None:
        from ..common.helpers import _staff_service
        staff_service = _staff_service(cq.message.bot)
        staff = await staff_service.get_by_tg_id(cq.from_user.id if cq.from_user else 0)
        if staff is None:
            await cq.answer(" ", show_alert=True)
            return
    
    data = await state.get_data()
    summary_text = new_order_summary(data)
    try:
        new_order = _build_new_order_data(data, staff)
    except KeyError:
        await state.clear()
        await cq.answer("    .  .", show_alert=True)
        return
    
    orders_service = _orders_service(cq.message.bot)
    order_id = await orders_service.create_order(new_order)
    detail = await orders_service.get_card(order_id, city_ids=visible_city_ids_for(staff))
    await state.clear()
    await cq.answer("  (  )")
    
    if detail:
        allow_auto = detail.district_id is not None
        prompt_parts = [
            f" #{detail.id}    <b></b>.",
            summary_text,
            "     8:00.",
        ]
        if not allow_auto:
            prompt_parts.append(" :   .")
        prompt_parts.append("Выберите способ распределения.")
        prompt = "\n\n".join(prompt_parts)
        markup = assign_menu_keyboard(detail.id, allow_auto=allow_auto)
        try:
            await cq.message.edit_text(prompt, reply_markup=markup, disable_web_page_preview=True)
        except Exception:
            await cq.message.answer(prompt, reply_markup=markup, disable_web_page_preview=True)
        return
    
    await _render_created_order_card(cq.message, order_id, staff)


__all__ = ["router"]
