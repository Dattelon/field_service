from __future__ import annotations

import html
from datetime import datetime, date
from typing import Iterable, Optional, Sequence
import inspect

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from field_service.db.models import OrderStatus
from field_service.services.guarantee_service import GuaranteeError

from .access import visible_city_ids_for
from .dto import (
    CityRef,
    MasterBrief,
    OrderAttachment,
    OrderCard,
    OrderCategory,
    OrderDetail,
    OrderListItem,
    OrderStatusHistoryItem,
    OrderType,
    StaffRole,
    StaffUser,
)
from .filters import StaffRoleFilter
from .keyboards import (
    assign_menu_keyboard,
    manual_candidates_keyboard,
    manual_confirm_keyboard,
    main_menu,
    order_card_keyboard,
    queue_cancel_keyboard,
    queue_list_keyboard,
)
from .states import QueueActionFSM, QueueFiltersFSM
from .texts import master_brief_line
from .utils import get_service
from .normalizers import normalize_category, normalize_status

queue_router = Router(name="admin_queue")

_ALLOWED_ROLES = {StaffRole.GLOBAL_ADMIN, StaffRole.CITY_ADMIN, StaffRole.LOGIST}

QUEUE_PAGE_SIZE = 10
MANUAL_PAGE_SIZE = 5
ORDER_CARD_HISTORY_LIMIT = 5


def _resolve_city_filter(staff: StaffUser, city_id: Optional[int]) -> Optional[list[int]]:
    allowed = visible_city_ids_for(staff)
    if allowed is None:
        if city_id:
            return [city_id]
        return None
    allowed_set = set(allowed)
    if city_id:
        return [city_id] if city_id in allowed_set else []
    return list(allowed)


async def _call_service(method, *args, city_ids=None, **kwargs):
    try:
        sig = inspect.signature(method)
        params = sig.parameters
        accepts_city = (
            "city_ids" in params
            or any(p.kind == p.VAR_KEYWORD for p in params.values())
        )
        if accepts_city and city_ids is not None:
            kwargs = dict(kwargs)
            kwargs["city_ids"] = city_ids
        return await method(*args, **kwargs)
    except TypeError:
        # Fallback: retry without city filter if the method rejects it
        return await method(*args, **kwargs)


def _format_order_line(order: OrderListItem) -> str:
    address_parts = [order.city_name] if order.city_name else []
    if order.district_name:
        address_parts.append(order.district_name)
    street_parts: list[str] = []
    if order.street_name:
        street_parts.append(order.street_name)
    if order.house:
        street_parts.append(str(order.house))
    if street_parts:
        address_parts.append(' '.join(street_parts))
    address = ', '.join(address_parts) if address_parts else '-'
    normalized_category = normalize_category(getattr(order, "category", None))
    if normalized_category is not None:
        category = CATEGORY_LABELS.get(normalized_category, normalized_category.value)
    else:
        category = str(getattr(order, "category", ""))
    status = order.status or '-'
    if order.order_type is OrderType.GUARANTEE:
        status = f"{status}  "
    slot = order.timeslot_local or '-'
    if order.master_name:
        master_label = order.master_name
    elif order.master_id:
        master_label = f" #{order.master_id}"
    else:
        master_label = ' '
    return (
        f"#{order.id} - {html.escape(address, quote=False)} | "
        f"{html.escape(category, quote=False)} | "
        f"{html.escape(status, quote=False)} | "
        f"{html.escape(slot, quote=False)} | "
        f"{html.escape(master_label, quote=False)}"
    )




def _manual_candidates_text(order: OrderCard, masters: Sequence[MasterBrief], page: int) -> str:
    address_parts: list[str] = []
    if order.city_name:
        address_parts.append(order.city_name)
    if order.district_name:
        address_parts.append(order.district_name)
    address_label = " / ".join(address_parts) if address_parts else "-"
    lines = [
        f" #{order.id}",
        f": {address_label}",
        f" {page}",
        "    :",
    ]
    if masters:
        lines.append("")
        lines.extend(master_brief_line(m) for m in masters)
    else:
        lines.append("")
        lines.append("   .")
    return "\n".join(lines)



CATEGORY_CHOICES: tuple[tuple[OrderCategory, str], ...] = (
    (OrderCategory.ELECTRICS, "Электрика"),
    (OrderCategory.PLUMBING, "Сантехника"),
    (OrderCategory.APPLIANCES, "Бытовая техника"),
    (OrderCategory.WINDOWS, "Окна и двери"),
    (OrderCategory.HANDYMAN, "Мастер на час"),
    (OrderCategory.ROADSIDE, "Автопомощь"),
)
CATEGORY_LABELS = {category: label for category, label in CATEGORY_CHOICES}
CATEGORY_LABELS_BY_VALUE = {category.value: label for category, label in CATEGORY_CHOICES}
CATEGORY_VALUE_MAP = {category.value: category for category, _ in CATEGORY_CHOICES}
CATEGORY_CHOICE_ENTRIES: tuple[tuple[str, str], ...] = tuple(
    (category.value, label) for category, label in CATEGORY_CHOICES
)
STATUS_CHOICES = tuple((status.value, status.value) for status in OrderStatus)
FILTER_DATA_KEY = "queue_filters"
FILTER_MSG_CHAT_KEY = "queue_filters_chat_id"
FILTER_MSG_ID_KEY = "queue_filters_message_id"
_MAX_CITIES = 120


CANCEL_ORDER_KEY = "queue_cancel_order_id"
CANCEL_CHAT_KEY = "queue_cancel_chat_id"
CANCEL_MESSAGE_KEY = "queue_cancel_message_id"
CANCEL_REASON_MIN = 3
CANCEL_REASON_MAX = 200


def _format_order_card_text(
    order: OrderDetail,
    history: Sequence[OrderStatusHistoryItem],
) -> str:
    """Build a human friendly card for an order detail view."""
    address_parts: list[str] = []
    if order.city_name:
        address_parts.append(order.city_name)
    if order.district_name:
        address_parts.append(order.district_name)
    street_segments: list[str] = []
    if order.street_name:
        street_segments.append(order.street_name)
    if order.house:
        street_segments.append(str(order.house))
    if street_segments:
        address_parts.append(" ".join(street_segments))
    address = ", ".join(address_parts) if address_parts else "-"

    client_bits: list[str] = []
    if order.client_name:
        client_bits.append(html.escape(order.client_name))
    if order.client_phone:
        client_bits.append(html.escape(order.client_phone))
    client_line = " / ".join(client_bits) if client_bits else "-"

    master_bits: list[str] = []
    if order.master_name:
        master_bits.append(html.escape(order.master_name))
    elif order.master_id:
        master_bits.append(f"#{order.master_id}")
    if order.master_phone:
        master_bits.append(html.escape(order.master_phone))
    master_line = " / ".join(master_bits).strip()

    description = order.description.strip() if order.description else ""
    description_line = html.escape(description) if description else "-"

    is_guarantee = order.order_type is OrderType.GUARANTEE
    type_label = order.type if not is_guarantee else f"{order.type} (гарантия)"
    normalized_category = normalize_category(getattr(order, "category", None))
    if normalized_category is not None:
        category_label = CATEGORY_LABELS.get(normalized_category, normalized_category.value)
    else:
        raw_cat = getattr(order, "category", "")
        category_label = str(raw_cat)

    lines_out = [
        f"<b>Заявка #{order.id}</b>",
        f"Статус: {html.escape(order.status)}",
        f"Тип: {html.escape(type_label)}",
        f"Категория: {html.escape(category_label)}",
        f"Слот: {html.escape(order.timeslot_local) if order.timeslot_local else '-'}",
        f"Адрес: {html.escape(address)}",
    ]
    if is_guarantee:
        lines_out.append("<b>Гарантия по предыдущему заказу</b>")

    lines_out.append(f"Вложения: {len(order.attachments)}")
    lines_out.append("")
    lines_out.append("<b>Клиент</b>")
    lines_out.append(f"Контакт: {client_line}")
    master_display = master_line if master_line else "пока не назначен"
    lines_out.append(f"Мастер: {master_display}")
    lines_out.append("")
    lines_out.append("<b>Описание</b>")
    lines_out.append(description_line)
    lines_out.append("")
    lines_out.append("<b>История статусов</b>")
    if history:
        for item in history:
            when = item.changed_at_local or "-"
            transition = item.to_status
            if item.from_status:
                transition = f"{item.from_status} -> {item.to_status}"
            actors: list[str] = []
            if item.changed_by_staff_id:
                actors.append(f"staff #{item.changed_by_staff_id}")
            if item.changed_by_master_id:
                actors.append(f"master #{item.changed_by_master_id}")
            actor_part = f" ({', '.join(actors)})" if actors else ""
            reason_part = f" - {item.reason}" if item.reason else ""
            lines_out.append(f"- {when}: {transition}{actor_part}{reason_part}")
    else:
        lines_out.append("История пуста")

    return "\n".join(lines_out)


def _order_card_markup(order: OrderDetail, *, show_guarantee: bool = False) -> InlineKeyboardMarkup:
    status = (order.status or '').upper()
    allow_return = status not in {'CANCELED', 'CLOSED'}
    allow_cancel = status not in {'CANCELED', 'CLOSED'}
    return order_card_keyboard(
        order.id,
        attachments=order.attachments,
        allow_return=allow_return,
        allow_cancel=allow_cancel,
        show_guarantee=show_guarantee,
    )


async def _should_show_guarantee_button(
    order: OrderDetail, orders_service, city_ids: Optional[Iterable[int]] = None
) -> bool:
    if (order.status or "").upper() != 'CLOSED':
        return False
    if order.order_type is OrderType.GUARANTEE:
        return False
    if not order.master_id:
        return False
    return not await _call_service(orders_service.has_active_guarantee, order.id, city_ids=city_ids)


async def _render_order_card(
    message: Message,
    order: OrderDetail,
    history: Sequence[OrderStatusHistoryItem],
    *,
    show_guarantee: bool = False,
) -> None:
    text = _format_order_card_text(order, history)
    markup = _order_card_markup(order, show_guarantee=show_guarantee)
    try:
        await message.edit_text(text, reply_markup=markup)
    except TelegramBadRequest as exc:
        if exc.message == "Message is not modified":
            return
        await message.answer(text, reply_markup=markup)


async def _clear_cancel_state(state: FSMContext) -> None:
    current_state = await state.get_state()
    if current_state == QueueActionFSM.cancel_reason.state:
        await state.set_state(None)
    data = await state.get_data()
    data.pop(CANCEL_ORDER_KEY, None)
    data.pop(CANCEL_CHAT_KEY, None)
    data.pop(CANCEL_MESSAGE_KEY, None)
    await state.set_data(data)


def _default_filters() -> dict[str, Optional[str | int]]:
    return {
        "city_id": None,
        "category": None,
        "status": None,
        "master_id": None,
        "date": None,
    }


def _parse_category_filter(value: Optional[str]) -> Optional[OrderCategory]:
    if not value:
        return None
    return normalize_category(value)


async def _load_filters(state: FSMContext) -> dict[str, Optional[str | int]]:
    data = await state.get_data()
    stored = data.get(FILTER_DATA_KEY)
    if not stored:
        filters = _default_filters()
        await state.update_data({FILTER_DATA_KEY: filters})
        return filters.copy()
    return dict(stored)


async def _save_filters(state: FSMContext, filters: dict[str, Optional[str | int]]) -> None:
    await state.update_data({FILTER_DATA_KEY: filters})


async def _store_filters_message(state: FSMContext, chat_id: int, message_id: int) -> None:
    await state.update_data({
        FILTER_MSG_CHAT_KEY: chat_id,
        FILTER_MSG_ID_KEY: message_id,
    })


async def _get_filters_message_ref(state: FSMContext) -> tuple[Optional[int], Optional[int]]:
    data = await state.get_data()
    return data.get(FILTER_MSG_CHAT_KEY), data.get(FILTER_MSG_ID_KEY)


async def _available_cities(staff: StaffUser, orders_service) -> list[CityRef]:
    if staff.role is StaffRole.GLOBAL_ADMIN or not staff.city_ids:
        return await orders_service.list_cities(limit=_MAX_CITIES)
    result: list[CityRef] = []
    for city_id in sorted(staff.city_ids):
        city = await orders_service.get_city(city_id)
        if city:
            result.append(city)
    return result


def _filters_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="", callback_data="adm:q:flt:city")
    builder.button(text="", callback_data="adm:q:flt:cat")
    builder.button(text="", callback_data="adm:q:flt:status")
    builder.button(text="", callback_data="adm:q:flt:master")
    builder.button(text="", callback_data="adm:q:flt:date")
    builder.button(text="", callback_data="adm:q:flt:apply")
    builder.button(text="", callback_data="adm:q:flt:reset")
    builder.button(text="", callback_data="adm:q")
    builder.adjust(2, 2, 2, 2)
    return builder.as_markup()


def _city_keyboard(cities: Iterable[CityRef], selected_id: Optional[int]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for city in cities:
        title = city.name
        if selected_id == city.id:
            title = f" {title}"
        builder.button(text=title, callback_data=f"adm:q:flt:c:{city.id}")
    builder.button(text=" ", callback_data="adm:q:flt:c:0")
    builder.button(text="", callback_data="adm:q:flt")
    builder.adjust(1)
    return builder.as_markup()


def _choice_keyboard(
    entries: Iterable[tuple[str, str]],
    *,
    prefix: str,
    selected: Optional[str],
    clear_suffix: str = "clr",
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for value, label in entries:
        text = label
        if selected == value:
            text = f" {label}"
        builder.button(text=text, callback_data=f"{prefix}:{value}")
    builder.button(text=" ", callback_data=f"{prefix}:{clear_suffix}")
    builder.button(text="", callback_data="adm:q:flt")
    builder.adjust(2)
    return builder.as_markup()


async def _format_filters_text(
    staff: StaffUser,
    filters: dict[str, Optional[str | int]],
    orders_service,
    *,
    include_header: bool = True,
) -> str:
    lines: list[str] = []
    if include_header:
        lines.append("<b> </b>")
    city_text = ""
    city_id = filters.get("city_id")
    if city_id:
        city = await orders_service.get_city(int(city_id))
        city_text = city.name if city else f"#{city_id}"
    category_filter = _parse_category_filter(filters.get("category"))
    if category_filter:
        category_text = CATEGORY_LABELS.get(category_filter, category_filter.value)
    else:
        category_text = ""
    status_filter = normalize_status(filters.get("status"))
    status_text = status_filter.value if status_filter else ""
    master_id = filters.get("master_id")
    master_text = f"#{master_id}" if master_id else ""
    date_value = filters.get("date") or ""
    lines.extend(
        [
            f": {city_text}",
            f": {category_text}",
            f": {status_text}",
            f": {master_text}",
            f": {date_value}",
        ]
    )
    return "\n".join(lines)


async def _edit_or_reply(message: Message, text: str, markup: InlineKeyboardMarkup, state: FSMContext) -> None:
    try:
        await message.edit_text(text, reply_markup=markup)
        await _store_filters_message(state, message.chat.id, message.message_id)
    except TelegramBadRequest as exc:
        if exc.message == "Message is not modified":
            return
        sent = await message.answer(text, reply_markup=markup)
        await _store_filters_message(state, sent.chat.id, sent.message_id)


async def _render_filters_menu(message: Message, staff: StaffUser, state: FSMContext) -> None:
    orders_service = get_service(message.bot, "orders_service")
    filters = await _load_filters(state)
    text = await _format_filters_text(staff, filters, orders_service)
    await _edit_or_reply(message, text, _filters_menu_keyboard(), state)


async def _render_filters_by_ref(bot, staff: StaffUser, state: FSMContext) -> None:
    chat_id, message_id = await _get_filters_message_ref(state)
    if not chat_id or not message_id:
        return
    orders_service = get_service(bot, "orders_service")
    filters = await _load_filters(state)
    text = await _format_filters_text(staff, filters, orders_service)
    markup = _filters_menu_keyboard()
    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=markup,
        )
    except TelegramBadRequest as exc:
        if exc.message != "Message is not modified":
            sent = await bot.send_message(chat_id, text, reply_markup=markup)
            await _store_filters_message(state, sent.chat.id, sent.message_id)
    else:
        await _store_filters_message(state, chat_id, message_id)


async def _render_city_selection(message: Message, staff: StaffUser, state: FSMContext) -> None:
    orders_service = get_service(message.bot, "orders_service")
    cities = await _available_cities(staff, orders_service)
    filters = await _load_filters(state)
    await _edit_or_reply(message, " ", _city_keyboard(cities, filters.get("city_id")), state)


async def _render_choice(
    message: Message,
    *,
    entries: Iterable[tuple[str, str]],
    prefix: str,
    selected: Optional[str],
    state: FSMContext,
    title: str,
) -> None:
    await _edit_or_reply(message, title, _choice_keyboard(entries, prefix=prefix, selected=selected), state)


async def _render_queue_list(message: Message, staff: StaffUser, state: FSMContext, page: int) -> None:
    """Render the main queue view for the admin bot."""
    orders_service = get_service(message.bot, "orders_service")
    filters = await _load_filters(state)
    page = max(page, 1)

    city_filter = _resolve_city_filter(staff, filters.get("city_id"))

    status_filter = normalize_status(filters.get("status"))
    category_filter = _parse_category_filter(filters.get("category"))
    master_filter = filters.get("master_id")
    timeslot_date: Optional[date] = None
    date_value = filters.get("date")
    if date_value:
        try:
            timeslot_date = date.fromisoformat(date_value)
        except ValueError:
            timeslot_date = None

    items: list[OrderListItem]
    has_next = False
    if city_filter == []:
        items = []
    else:
        items, has_next = await orders_service.list_queue(
            city_ids=city_filter,
            page=page,
            page_size=QUEUE_PAGE_SIZE,
            status_filter=status_filter,
            category=category_filter,
            master_id=master_filter,
            timeslot_date=timeslot_date,
        )

    filters_text = await _format_filters_text(
        staff, filters, orders_service, include_header=False
    )
    lines = ["<b>Очередь заявок</b>", filters_text]
    if items:
        lines.append("")
        lines.extend(_format_order_line(item) for item in items)
    else:
        lines.append("")
        lines.append("Список пуст")
    lines.append("")
    lines.append(f"Страница: {page}")
    text = "\n".join(lines)

    markup = queue_list_keyboard(items, page=page, has_next=has_next)
    await _edit_or_reply(message, text, markup, state)





@queue_router.callback_query(
    F.data == "adm:q",
    StaffRoleFilter(_ALLOWED_ROLES),
)
async def cb_queue_menu(cq: CallbackQuery, staff: StaffUser) -> None:
    builder = InlineKeyboardBuilder()
    builder.button(text="", callback_data="adm:q:flt")
    builder.button(text="", callback_data="adm:q:list:1")
    builder.button(text=" ", callback_data="adm:menu")
    builder.adjust(1)
    await cq.message.edit_text(":", reply_markup=builder.as_markup())
    await cq.answer()


@queue_router.callback_query(
    F.data == "adm:q:flt",
    StaffRoleFilter(_ALLOWED_ROLES),
)
async def cb_queue_filters_root(cq: CallbackQuery, staff: StaffUser, state: FSMContext) -> None:
    await _load_filters(state)
    await _render_filters_menu(cq.message, staff, state)
    await cq.answer()


@queue_router.callback_query(
    F.data == "adm:q:flt:city",
    StaffRoleFilter(_ALLOWED_ROLES),
)
async def cb_queue_filters_city(cq: CallbackQuery, staff: StaffUser, state: FSMContext) -> None:
    await _render_city_selection(cq.message, staff, state)
    await cq.answer()


@queue_router.callback_query(
    F.data.startswith("adm:q:flt:c:"),
    StaffRoleFilter(_ALLOWED_ROLES),
)
async def cb_queue_filters_city_pick(cq: CallbackQuery, staff: StaffUser, state: FSMContext) -> None:
    filters = await _load_filters(state)
    payload = cq.data.split(":")[-1]
    if payload == "0":
        filters["city_id"] = None
    else:
        try:
            filters["city_id"] = int(payload)
        except ValueError:
            await cq.answer(" ", show_alert=True)
            return
    await _save_filters(state, filters)
    await _render_filters_menu(cq.message, staff, state)
    await cq.answer()


@queue_router.callback_query(
    F.data == "adm:q:flt:cat",
    StaffRoleFilter(_ALLOWED_ROLES),
)
async def cb_queue_filters_category(cq: CallbackQuery, staff: StaffUser, state: FSMContext) -> None:
    filters = await _load_filters(state)
    await _render_choice(
        cq.message,
        entries=CATEGORY_CHOICE_ENTRIES,
        prefix="adm:q:flt:cat",
        selected=filters.get("category"),
        state=state,
        title=" ",
    )
    await cq.answer()


@queue_router.callback_query(
    F.data.startswith("adm:q:flt:cat:"),
    StaffRoleFilter(_ALLOWED_ROLES),
)
async def cb_queue_filters_category_pick(cq: CallbackQuery, staff: StaffUser, state: FSMContext) -> None:
    value = cq.data.split(":")[-1]
    filters = await _load_filters(state)
    if value == "clr":
        filters["category"] = None
    else:
        if value not in CATEGORY_VALUE_MAP:
            await cq.answer(" ", show_alert=True)
            return
        filters["category"] = value
    await _save_filters(state, filters)
    await _render_filters_menu(cq.message, staff, state)
    await cq.answer()


@queue_router.callback_query(
    F.data == "adm:q:flt:status",
    StaffRoleFilter(_ALLOWED_ROLES),
)
async def cb_queue_filters_status(cq: CallbackQuery, staff: StaffUser, state: FSMContext) -> None:
    filters = await _load_filters(state)
    await _render_choice(
        cq.message,
        entries=STATUS_CHOICES,
        prefix="adm:q:flt:st",
        selected=filters.get("status"),
        state=state,
        title=" ",
    )
    await cq.answer()


@queue_router.callback_query(
    F.data.startswith("adm:q:flt:st:"),
    StaffRoleFilter(_ALLOWED_ROLES),
)
async def cb_queue_filters_status_pick(cq: CallbackQuery, staff: StaffUser, state: FSMContext) -> None:
    value = cq.data.split(":")[-1]
    filters = await _load_filters(state)
    if value == "clr":
        filters["status"] = None
    else:
        status_enum = normalize_status(value)
        if not status_enum:
            await cq.answer(" ", show_alert=True)
            return
        filters["status"] = status_enum.value
    await _save_filters(state, filters)
    await _render_filters_menu(cq.message, staff, state)
    await cq.answer()


@queue_router.callback_query(
    F.data == "adm:q:flt:master",
    StaffRoleFilter(_ALLOWED_ROLES),
)
async def cb_queue_filters_master(cq: CallbackQuery, staff: StaffUser, state: FSMContext) -> None:
    await state.set_state(QueueFiltersFSM.master)
    await cq.answer(" ID  ", show_alert=True)


@queue_router.message(
    StateFilter(QueueFiltersFSM.master),
    StaffRoleFilter(_ALLOWED_ROLES),
)
async def cb_queue_filters_master_input(msg: Message, staff: StaffUser, state: FSMContext) -> None:
    text = msg.text.strip()
    filters = await _load_filters(state)
    if text == "-":
        filters["master_id"] = None
    else:
        if not text.isdigit():
            await msg.answer("ID       '-'  .")
            return
        filters["master_id"] = int(text)
    chat_id, message_id = await _get_filters_message_ref(state)
    await state.clear()
    await _save_filters(state, filters)
    if chat_id and message_id:
        await _store_filters_message(state, chat_id, message_id)
    await _render_filters_by_ref(msg.bot, staff, state)


@queue_router.callback_query(
    F.data == "adm:q:flt:date",
    StaffRoleFilter(_ALLOWED_ROLES),
)
async def cb_queue_filters_date(cq: CallbackQuery, staff: StaffUser, state: FSMContext) -> None:
    await state.set_state(QueueFiltersFSM.date)
    await cq.answer("  YYYY-MM-DD  '-'  ", show_alert=True)


@queue_router.message(
    StateFilter(QueueFiltersFSM.date),
    StaffRoleFilter(_ALLOWED_ROLES),
)
async def cb_queue_filters_date_input(msg: Message, staff: StaffUser, state: FSMContext) -> None:
    text = msg.text.strip()
    filters = await _load_filters(state)
    if text == "-":
        filters["date"] = None
    else:
        try:
            datetime.strptime(text, "%Y-%m-%d")
        except ValueError:
            await msg.answer("     YYYY-MM-DD  '-'  .")
            return
        filters["date"] = text
    chat_id, message_id = await _get_filters_message_ref(state)
    await state.clear()
    await _save_filters(state, filters)
    if chat_id and message_id:
        await _store_filters_message(state, chat_id, message_id)
    await _render_filters_by_ref(msg.bot, staff, state)


@queue_router.callback_query(
    F.data == "adm:q:flt:reset",
    StaffRoleFilter(_ALLOWED_ROLES),
)
async def cb_queue_filters_reset(cq: CallbackQuery, staff: StaffUser, state: FSMContext) -> None:
    filters = _default_filters()
    await _save_filters(state, filters)
    await _render_filters_menu(cq.message, staff, state)
    await cq.answer(" ")


@queue_router.callback_query(
    F.data == "adm:q:flt:apply",
    StaffRoleFilter(_ALLOWED_ROLES),
)
async def cb_queue_filters_apply(cq: CallbackQuery, staff: StaffUser, state: FSMContext) -> None:
    await _render_queue_list(cq.message, staff, state, page=1)
    await cq.answer()


@queue_router.callback_query(
    F.data.startswith("adm:q:list:"),
    StaffRoleFilter(_ALLOWED_ROLES),
)
async def cb_queue_list(cq: CallbackQuery, staff: StaffUser, state: FSMContext) -> None:
    try:
        page = int(cq.data.split(":")[3])
    except (IndexError, ValueError):
        await cq.answer(" ", show_alert=True)
        return
    await _render_queue_list(cq.message, staff, state, page=page)
    await cq.answer()


@queue_router.callback_query(
    F.data.startswith("adm:q:card:"),
    StaffRoleFilter(_ALLOWED_ROLES),
)
async def cb_queue_card(cq: CallbackQuery, staff: StaffUser, state: FSMContext) -> None:
    parts = cq.data.split(':')
    try:
        order_id = int(parts[3])
    except (IndexError, ValueError):
        await cq.answer('  ', show_alert=True)
        return
    orders_service = get_service(cq.message.bot, 'orders_service')
    order = await _call_service(orders_service.get_card, order_id, city_ids=visible_city_ids_for(staff))
    if not order:
        await cq.answer('  ', show_alert=True)
        return
    if staff.role is not StaffRole.GLOBAL_ADMIN and order.city_id not in staff.city_ids:
        await cq.answer('   ', show_alert=True)
        return
    history = await _call_service(orders_service.list_status_history, order_id, limit=ORDER_CARD_HISTORY_LIMIT, city_ids=visible_city_ids_for(staff))
    show_guarantee = await _should_show_guarantee_button(order, orders_service, visible_city_ids_for(staff))
    await _render_order_card(cq.message, order, history, show_guarantee=show_guarantee)
    await cq.answer()

@queue_router.callback_query(
    F.data.regexp(r'^adm:q:as:\d+$'),
    StaffRoleFilter(_ALLOWED_ROLES),
)
async def cb_queue_assign_menu(cq: CallbackQuery, staff: StaffUser) -> None:
    order_id = int(cq.data.split(':')[3])
    orders_service = get_service(cq.message.bot, 'orders_service')
    order = await _call_service(orders_service.get_card, order_id, city_ids=visible_city_ids_for(staff))
    if not order:
        await cq.answer('  ', show_alert=True)
        return
    if staff.role is not StaffRole.GLOBAL_ADMIN and order.city_id not in staff.city_ids:
        await cq.answer('   ', show_alert=True)
        return
    address_bits = [bit for bit in (order.city_name, order.district_name, order.street_name) if bit]
    if order.house:
        address_bits.append(str(order.house))
    address_label = ', '.join(address_bits) if address_bits else '-'
    text = (
        f" #{order.id}\n"
        f": {address_label}\n"
        "  ."
    )
    allow_auto = bool(order.district_id)
    markup = assign_menu_keyboard(order.id, allow_auto=allow_auto)
    try:
        await cq.message.edit_text(text, reply_markup=markup)
    except TelegramBadRequest as exc:
        if exc.message == 'Message is not modified':
            await cq.answer()
            return
        await cq.message.answer(text, reply_markup=markup)
    await cq.answer()








@queue_router.callback_query(
    F.data.startswith("adm:q:as:auto:"),
    StaffRoleFilter(_ALLOWED_ROLES),
)
async def cb_queue_assign_auto(cq: CallbackQuery, staff: StaffUser) -> None:
    parts = cq.data.split(":")
    try:
        order_id = int(parts[4])
    except (IndexError, ValueError):
        await cq.answer(" ", show_alert=True)
        return

    orders_service = get_service(cq.message.bot, "orders_service")
    distribution_service = get_service(cq.message.bot, "distribution_service")
    order = await _call_service(orders_service.get_card, order_id, city_ids=visible_city_ids_for(staff))
    if not order:
        await cq.answer("  ", show_alert=True)
        return
    if staff.role is not StaffRole.GLOBAL_ADMIN and order.city_id not in staff.city_ids:
        await cq.answer("   ", show_alert=True)
        return

    ok, result = await distribution_service.assign_auto(order_id, staff.id)

    lines: list[str] = [f" #{order.id}"]
    lines.append(" ." if ok else " .")
    lines.append("")
    lines.append(result.message)
    if not ok and result.code == "no_candidates":
        lines.append("")
        lines.append("  .    .")

    text_body = "\n".join(lines)

    builder = InlineKeyboardBuilder()
    builder.button(text=" ", callback_data=f"adm:q:card:{order_id}")
    builder.button(text=" ", callback_data=f"adm:q:as:{order_id}")
    builder.adjust(1)

    try:
        await cq.message.edit_text(text_body, reply_markup=builder.as_markup())
    except TelegramBadRequest as exc:
        if exc.message != "Message is not modified":
            await cq.message.answer(text_body, reply_markup=builder.as_markup())

    if ok:
        await cq.answer(" ", show_alert=False)
    else:
        alert_codes = {"no_district", "no_category", "forbidden", "not_found", "offer_conflict"}
        await cq.answer(result.message, show_alert=result.code in alert_codes)


@queue_router.callback_query(
    F.data.startswith("adm:q:as:man:"),
    StaffRoleFilter(_ALLOWED_ROLES),
)
async def cb_queue_assign_manual_list(
    cq: CallbackQuery,
    staff: StaffUser,
) -> None:
    parts = cq.data.split(":")
    try:
        order_id = int(parts[4])
        page = int(parts[5])
    except (IndexError, ValueError):
        await cq.answer(" ", show_alert=True)
        return

    orders_service = get_service(cq.message.bot, "orders_service")
    order = await _call_service(orders_service.get_card, order_id, city_ids=visible_city_ids_for(staff))
    if not order:
        await cq.answer("  ", show_alert=True)
        return
    if staff.role is not StaffRole.GLOBAL_ADMIN and order.city_id not in staff.city_ids:
        await cq.answer("   ", show_alert=True)
        return

    masters, has_next = await orders_service.manual_candidates(
        order_id,
        page=page,
        page_size=MANUAL_PAGE_SIZE,
        city_ids=visible_city_ids_for(staff),
    )
    text = _manual_candidates_text(order, masters, page)
    markup = manual_candidates_keyboard(order.id, masters, page=page, has_next=has_next)
    try:
        await cq.message.edit_text(
            text,
            reply_markup=markup,
            disable_web_page_preview=True,
        )
    except TelegramBadRequest as exc:
        if exc.message != "Message is not modified":
            await cq.message.answer(
                text,
                reply_markup=markup,
                disable_web_page_preview=True,
            )
    await cq.answer()


@queue_router.callback_query(
    F.data.startswith("adm:q:as:check:"),
    StaffRoleFilter(_ALLOWED_ROLES),
)
async def cb_queue_assign_manual_check(
    cq: CallbackQuery,
    staff: StaffUser,
) -> None:
    parts = cq.data.split(":")
    try:
        order_id = int(parts[4])
        page = int(parts[5])
        master_id = int(parts[6])
    except (IndexError, ValueError):
        await cq.answer(" ", show_alert=True)
        return

    orders_service = get_service(cq.message.bot, "orders_service")
    order = await _call_service(orders_service.get_card, order_id, city_ids=visible_city_ids_for(staff))
    if not order:
        await cq.answer("  ", show_alert=True)
        return
    if staff.role is not StaffRole.GLOBAL_ADMIN and order.city_id not in staff.city_ids:
        await cq.answer("   ", show_alert=True)
        return

    masters, _ = await orders_service.manual_candidates(
        order_id,
        page=page,
        page_size=MANUAL_PAGE_SIZE,
        city_ids=visible_city_ids_for(staff),
    )
    candidate = next((m for m in masters if m.id == master_id), None)
    if candidate is None:
        await cq.answer("    .  .", show_alert=True)
        return

    reasons: list[str] = []
    available = candidate.is_on_shift and not candidate.on_break
    if not candidate.is_on_shift:
        reasons.append("  ")
    elif candidate.on_break:
        reasons.append("  ")
    at_limit = (
        candidate.max_active_orders > 0
        and candidate.active_orders >= candidate.max_active_orders
    )
    if at_limit:
        reasons.append(
            f" {candidate.active_orders}/{candidate.max_active_orders}"
        )

    if available and not at_limit:
        distribution_service = get_service(cq.message.bot, "distribution_service")
        ok, message = await distribution_service.send_manual_offer(
            order_id,
            master_id,
            staff.id,
        )
        if not ok:
            await cq.answer(message, show_alert=True)
            return

        builder = InlineKeyboardBuilder()
        builder.button(text=" ", callback_data=f"adm:q:card:{order_id}")
        builder.button(
            text=" ",
            callback_data=f"adm:q:as:man:{order_id}:{page}",
        )
        builder.adjust(1)
        text_lines = [
            f" #{order.id}",
            master_brief_line(candidate),
            "",
            "  .",
        ]
        try:
            await cq.message.edit_text(
                "\n".join(text_lines),
                reply_markup=builder.as_markup(),
            )
        except TelegramBadRequest as exc:
            if exc.message != "Message is not modified":
                await cq.message.answer(
                    "\n".join(text_lines),
                    reply_markup=builder.as_markup(),
                )
        await cq.answer(" ")
        return

    text_lines = [
        f" #{order.id}",
        master_brief_line(candidate),
        "",
    ]
    if reasons:
        text_lines.append(" : " + "; ".join(reasons))
        text_lines.append("")
    text_lines.append("   ?")
    markup = manual_confirm_keyboard(order.id, master_id, page)
    try:
        await cq.message.edit_text(
            "\n".join(text_lines),
            reply_markup=markup,
            disable_web_page_preview=True,
        )
    except TelegramBadRequest as exc:
        if exc.message != "Message is not modified":
            await cq.message.answer(
                "\n".join(text_lines),
                reply_markup=markup,
                disable_web_page_preview=True,
            )
    await cq.answer()


@queue_router.callback_query(
    F.data.startswith("adm:q:as:pick:"),
    StaffRoleFilter(_ALLOWED_ROLES),
)
async def cb_queue_assign_manual_pick(
    cq: CallbackQuery,
    staff: StaffUser,
) -> None:
    parts = cq.data.split(":")
    try:
        order_id = int(parts[4])
        page = int(parts[5])
        master_id = int(parts[6])
    except (IndexError, ValueError):
        await cq.answer(" ", show_alert=True)
        return

    orders_service = get_service(cq.message.bot, "orders_service")
    order = await orders_service.get_card(order_id, city_ids=visible_city_ids_for(staff))
    if not order:
        await cq.answer("  ", show_alert=True)
        return
    if staff.role is not StaffRole.GLOBAL_ADMIN and order.city_id not in staff.city_ids:
        await cq.answer("   ", show_alert=True)
        return

    distribution_service = get_service(cq.message.bot, "distribution_service")
    ok, message = await distribution_service.send_manual_offer(
        order_id,
        master_id,
        staff.id,
    )
    if not ok:
        await cq.answer(message, show_alert=True)
        return

    masters, _ = await orders_service.manual_candidates(
        order_id,
        page=page,
        page_size=MANUAL_PAGE_SIZE,
        city_ids=visible_city_ids_for(staff),
    )
    candidate = next((m for m in masters if m.id == master_id), None)
    summary = master_brief_line(candidate) if candidate else f" #{master_id}"

    builder = InlineKeyboardBuilder()
    builder.button(text=" ", callback_data=f"adm:q:card:{order_id}")
    builder.button(
        text=" ",
        callback_data=f"adm:q:as:man:{order_id}:{page}",
    )
    builder.adjust(1)
    text_lines = [
        f" #{order.id}",
        summary,
        "",
        "  .",
    ]
    try:
        await cq.message.edit_text(
            "\n".join(text_lines),
            reply_markup=builder.as_markup(),
        )
    except TelegramBadRequest as exc:
        if exc.message != "Message is not modified":
            await cq.message.answer(
                "\n".join(text_lines),
                reply_markup=builder.as_markup(),
            )
    await cq.answer(" ")




@queue_router.callback_query(
    F.data.startswith("adm:q:gar:"),
    StaffRoleFilter(_ALLOWED_ROLES),
)
async def cb_queue_guarantee(cq: CallbackQuery, staff: StaffUser) -> None:
    parts = cq.data.split(":")
    try:
        order_id = int(parts[3])
    except (IndexError, ValueError):
        await cq.answer("  ", show_alert=True)
        return

    orders_service = get_service(cq.message.bot, "orders_service")
    order = await orders_service.get_card(order_id, city_ids=visible_city_ids_for(staff))
    if not order:
        await cq.answer("  ", show_alert=True)
        return
    if staff.role is not StaffRole.GLOBAL_ADMIN and order.city_id not in staff.city_ids:
        await cq.answer("   ", show_alert=True)
        return

    status = (order.status or "").upper()
    if status != "CLOSED":
        await cq.answer("      ", show_alert=True)
        return
    if order.order_type is OrderType.GUARANTEE:
        await cq.answer("   ", show_alert=True)
        return
    if not order.master_id:
        await cq.answer("    ", show_alert=True)
        return
    if await _call_service(orders_service.has_active_guarantee, order.id, city_ids=visible_city_ids_for(staff)):
        await cq.answer("   ", show_alert=True)
        return

    try:
        new_order_id = await orders_service.create_guarantee_order(order.id, staff.id)
    except GuaranteeError as exc:
        await cq.answer(str(exc), show_alert=True)
        return

    updated = await _call_service(orders_service.get_card, order_id, city_ids=visible_city_ids_for(staff))
    history = await _call_service(orders_service.list_status_history, order_id, limit=ORDER_CARD_HISTORY_LIMIT, city_ids=visible_city_ids_for(staff))
    await _render_order_card(cq.message, updated or order, history, show_guarantee=False)

    await cq.message.answer(
        f"  #{new_order_id}     ."
    )
    await cq.answer()


@queue_router.callback_query(
    F.data.startswith("adm:q:ret:"),
    StaffRoleFilter(_ALLOWED_ROLES),
)
async def cb_queue_return(cq: CallbackQuery, staff: StaffUser) -> None:
    parts = cq.data.split(":")
    try:
        order_id = int(parts[3])
    except (IndexError, ValueError):
        await cq.answer("  ", show_alert=True)
        return
    orders_service = get_service(cq.message.bot, "orders_service")
    order = await _call_service(orders_service.get_card, order_id, city_ids=visible_city_ids_for(staff))
    if not order:
        await cq.answer("  ", show_alert=True)
        return
    if staff.role is not StaffRole.GLOBAL_ADMIN and order.city_id not in staff.city_ids:
        await cq.answer("   ", show_alert=True)
        return
    ok = await orders_service.return_to_search(order_id, staff.id)
    if not ok:
        await cq.answer("     ", show_alert=True)
        return
    updated = await _call_service(orders_service.get_card, order_id, city_ids=visible_city_ids_for(staff))
    if not updated:
        await cq.answer("  ", show_alert=True)
        return
    history = await _call_service(orders_service.list_status_history, order_id, limit=ORDER_CARD_HISTORY_LIMIT, city_ids=visible_city_ids_for(staff))
    show_guarantee = await _should_show_guarantee_button(updated, orders_service, visible_city_ids_for(staff))
    await _render_order_card(cq.message, updated, history, show_guarantee=show_guarantee)
    await cq.answer("   ")


@queue_router.callback_query(
    F.data.startswith("adm:q:cnl:"),
    StaffRoleFilter(_ALLOWED_ROLES),
)
async def cb_queue_cancel_start(cq: CallbackQuery, staff: StaffUser, state: FSMContext) -> None:
    parts = cq.data.split(":")
    try:
        order_id = int(parts[3])
    except (IndexError, ValueError):
        await cq.answer("  ", show_alert=True)
        return
    orders_service = get_service(cq.message.bot, "orders_service")
    order = await _call_service(orders_service.get_card, order_id, city_ids=visible_city_ids_for(staff))
    if not order:
        await cq.answer("  ", show_alert=True)
        return
    if staff.role is not StaffRole.GLOBAL_ADMIN and order.city_id not in staff.city_ids:
        await cq.answer("   ", show_alert=True)
        return
    await state.set_state(QueueActionFSM.cancel_reason)
    await state.update_data(
        {
            CANCEL_ORDER_KEY: order_id,
            CANCEL_CHAT_KEY: cq.message.chat.id,
            CANCEL_MESSAGE_KEY: cq.message.message_id,
        }
    )
    await cq.message.edit_text(
        "   ( 3  200 ).  /cancel  .",
        reply_markup=queue_cancel_keyboard(order_id),
    )
    await cq.answer()


@queue_router.callback_query(
    F.data.startswith("adm:q:cnl:bk:"),
    StaffRoleFilter(_ALLOWED_ROLES),
)
async def cb_queue_cancel_back(cq: CallbackQuery, staff: StaffUser, state: FSMContext) -> None:
    parts = cq.data.split(":")
    try:
        order_id = int(parts[4])
    except (IndexError, ValueError):
        await cq.answer(" ", show_alert=True)
        return
    orders_service = get_service(cq.message.bot, "orders_service")
    order = await _call_service(orders_service.get_card, order_id, city_ids=visible_city_ids_for(staff))
    if not order:
        await _clear_cancel_state(state)
        await cq.answer("  ", show_alert=True)
        return
    if staff.role is not StaffRole.GLOBAL_ADMIN and order.city_id not in staff.city_ids:
        await _clear_cancel_state(state)
        await cq.answer("   ", show_alert=True)
        return
    history = await _call_service(orders_service.list_status_history, order_id, limit=ORDER_CARD_HISTORY_LIMIT, city_ids=visible_city_ids_for(staff))
    show_guarantee = await _should_show_guarantee_button(order, orders_service, visible_city_ids_for(staff))
    await _render_order_card(cq.message, order, history, show_guarantee=show_guarantee)
    await _clear_cancel_state(state)
    await cq.answer()


@queue_router.message(
    StateFilter(QueueActionFSM.cancel_reason),
    StaffRoleFilter(_ALLOWED_ROLES),
    F.text == "/cancel",
)
async def queue_cancel_abort(msg: Message, staff: StaffUser, state: FSMContext) -> None:
    data = await state.get_data()
    order_id = data.get(CANCEL_ORDER_KEY)
    chat_id = data.get(CANCEL_CHAT_KEY)
    message_id = data.get(CANCEL_MESSAGE_KEY)
    await _clear_cancel_state(state)
    await msg.answer(" .")
    if not order_id or not chat_id or not message_id:
        return
    orders_service = get_service(msg.bot, "orders_service")
    order = await _call_service(orders_service.get_card, int(order_id), city_ids=visible_city_ids_for(staff))
    if not order:
        return
    if staff.role is not StaffRole.GLOBAL_ADMIN and order.city_id not in staff.city_ids:
        return
    history = await _call_service(orders_service.list_status_history, int(order_id), limit=ORDER_CARD_HISTORY_LIMIT, city_ids=visible_city_ids_for(staff))
    text_body = _format_order_card_text(order, history)
    show_guarantee = await _should_show_guarantee_button(order, orders_service, visible_city_ids_for(staff))
    markup = _order_card_markup(order, show_guarantee=show_guarantee)
    try:
        await msg.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text_body,
            reply_markup=markup,
        )
    except TelegramBadRequest as exc:
        if exc.message != "Message is not modified":
            await msg.bot.send_message(chat_id, text_body, reply_markup=markup)


@queue_router.message(
    StateFilter(QueueActionFSM.cancel_reason),
    StaffRoleFilter(_ALLOWED_ROLES),
)
async def queue_cancel_reason(msg: Message, staff: StaffUser, state: FSMContext) -> None:
    # Business rule for cancel reason:
    # - empty or whitespace-only reason is allowed (operator skips typing)  proceed
    # - short non-empty (< 3) is rejected (e.g. 'ok')
    text_raw = msg.text or ""
    reason = text_raw
    if text_raw.strip() and len(text_raw.strip()) < CANCEL_REASON_MIN:
        await msg.answer(
            f"    {CANCEL_REASON_MIN}  {CANCEL_REASON_MAX} ."
        )
        return
    data = await state.get_data()
    order_id = data.get(CANCEL_ORDER_KEY)
    chat_id = data.get(CANCEL_CHAT_KEY)
    message_id = data.get(CANCEL_MESSAGE_KEY)
    if not order_id or not chat_id or not message_id:
        await _clear_cancel_state(state)
        await msg.answer("   .   .")
        return
    orders_service = get_service(msg.bot, "orders_service")
    order = await _call_service(orders_service.get_card, int(order_id), city_ids=visible_city_ids_for(staff))
    if not order:
        await _clear_cancel_state(state)
        await msg.answer("  .")
        return
    if staff.role is not StaffRole.GLOBAL_ADMIN and order.city_id not in staff.city_ids:
        await _clear_cancel_state(state)
        await msg.answer("   .")
        return
    ok = await orders_service.cancel(int(order_id), reason=reason, by_staff_id=staff.id)
    if ok:
        await msg.answer(" .")
    else:
        await msg.answer("   .")
    updated = await _call_service(orders_service.get_card, int(order_id), city_ids=visible_city_ids_for(staff))
    if updated:
        history = await _call_service(orders_service.list_status_history, int(order_id), limit=ORDER_CARD_HISTORY_LIMIT, city_ids=visible_city_ids_for(staff))
        text_body = _format_order_card_text(updated, history)
        markup = _order_card_markup(updated)
        try:
            await msg.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text_body,
                reply_markup=markup,
            )
        except TelegramBadRequest as exc:
            if exc.message != "Message is not modified":
                await msg.bot.send_message(chat_id, text_body, reply_markup=markup)
    await _clear_cancel_state(state)


@queue_router.callback_query(
    F.data.startswith('adm:q:att:'),
    StaffRoleFilter(_ALLOWED_ROLES),
)
async def cb_queue_attachment(cq: CallbackQuery, staff: StaffUser) -> None:
    parts = cq.data.split(':')
    try:
        order_id = int(parts[3])
        attachment_id = int(parts[4])
    except (IndexError, ValueError):
        await cq.answer(' ', show_alert=True)
        return
    orders_service = get_service(cq.message.bot, 'orders_service')
    order = await _call_service(orders_service.get_card, order_id, city_ids=visible_city_ids_for(staff))
    if not order:
        await cq.answer('  ', show_alert=True)
        return
    if staff.role is not StaffRole.GLOBAL_ADMIN and order.city_id not in staff.city_ids:
        await cq.answer('   ', show_alert=True)
        return
    attachment = await _call_service(orders_service.get_order_attachment, order_id, attachment_id, city_ids=visible_city_ids_for(staff))
    if not attachment:
        await cq.answer('  ', show_alert=True)
        return
    caption = attachment.caption or None
    file_type = (attachment.file_type or '').upper()
    try:
        if file_type.endswith('PHOTO'):
            await cq.message.answer_photo(attachment.file_id, caption=caption)
        else:
            await cq.message.answer_document(attachment.file_id, caption=caption)
    except TelegramBadRequest as exc:
        await cq.answer(f'   : {exc.message}', show_alert=True)
        return
    await cq.answer()

@queue_router.callback_query(
    F.data == "adm:q:bk",
    StaffRoleFilter(_ALLOWED_ROLES),
)
async def cb_queue_back(cq: CallbackQuery, staff: StaffUser, state: FSMContext) -> None:
    builder = InlineKeyboardBuilder()
    builder.button(text="", callback_data="adm:q:flt")
    builder.button(text="", callback_data="adm:q:list:1")
    builder.button(text="", callback_data="adm:menu")
    builder.adjust(1)
    await cq.message.edit_text(" ", reply_markup=builder.as_markup())
    await cq.answer()
