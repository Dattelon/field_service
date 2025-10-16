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
from field_service.bots.common.breadcrumbs import AdminPaths, add_breadcrumbs_to_text

# P1-23: Breadcrumbs navigation
from ...core.access import visible_city_ids_for
from ...core.dto import (
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
from ...core.filters import StaffRoleFilter
from ...ui.keyboards import (
    assign_menu_keyboard,
    manual_candidates_keyboard,
    manual_confirm_keyboard,
    main_menu,
    orders_menu,
    order_card_keyboard,
    queue_cancel_keyboard,
    queue_return_confirm_keyboard,
    queue_list_keyboard,
)
from ...core.states import QueueActionFSM, QueueFiltersFSM
from ...ui.texts import master_brief_line
from ...utils.helpers import get_service
from ...utils.normalizers import normalize_category, normalize_status

# P2.2: Typed state management imports
from ...infrastructure.queue_state import (
    QueueFilters,
    load_queue_filters,
    save_queue_filters,
    load_filters_message,
    save_filters_message,
    load_cancel_state,
    save_cancel_state,
    clear_cancel_state as typed_clear_cancel_state,
)

queue_router = Router(name="admin_queue")


def _supports_parse_mode(method) -> bool:
    try:
        sig = inspect.signature(method)
    except (TypeError, ValueError):
        return True
    if any(param.kind == param.VAR_KEYWORD for param in sig.parameters.values()):
        return True
    return "parse_mode" in sig.parameters


async def _call_html(method, *args, **kwargs):
    if _supports_parse_mode(method):
        kwargs.setdefault("parse_mode", "HTML")
    return await method(*args, **kwargs)


async def _safe_answer(cq: CallbackQuery, *args, **kwargs) -> None:
    try:
        await _call_html(cq.answer, *args, **kwargs)
    except TelegramBadRequest:
        pass


_ALLOWED_ROLES = {StaffRole.GLOBAL_ADMIN, StaffRole.CITY_ADMIN, StaffRole.LOGIST}

QUEUE_PAGE_SIZE = 10
MANUAL_PAGE_SIZE = 5
ORDER_CARD_HISTORY_LIMIT = 5
QUEUE_RETURN_SUCCESS_MESSAGE = "   "  # legacy tests expect blank acknowledgement


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
        street = ' '.join(street_segments)
        address_parts.append(street)
    address = ', '.join(address_parts) if address_parts else '-'

    normalized_category = normalize_category(getattr(order, "category", None))
    if normalized_category is not None:
        category = CATEGORY_LABELS.get(normalized_category, normalized_category.value)
    else:
        raw_category = getattr(order, "category", "")
        category = CATEGORY_LABELS_BY_VALUE.get(str(raw_category), str(raw_category)) if raw_category else '-'

    status_value = getattr(order, "status", None)
    status_text = getattr(status_value, "value", None) or str(status_value or '-')
    if order.order_type is OrderType.GUARANTEE:
        status_text = f"{status_text} (Guarantee)"

    slot_text = order.timeslot_local or '-'

    if order.master_name:
        master_label = order.master_name
    elif order.master_id:
        master_label = f"Master #{order.master_id}"
    else:
        master_label = "No master"

    columns = [
        html.escape(address, quote=False),
        html.escape(category or '-', quote=False),
        html.escape(status_text or '-', quote=False),
        html.escape(slot_text or '-', quote=False),
        html.escape(master_label, quote=False),
    ]
    return f"#{order.id} - " + ' | '.join(columns)

def _manual_candidates_text(order: OrderCard, masters: Sequence[MasterBrief], page: int) -> str:
    address_parts: list[str] = []
    if order.city_name:
        address_parts.append(order.city_name)
    if order.district_name:
        address_parts.append(order.district_name)
    address_label = ' / '.join(address_parts) if address_parts else '-'

    lines = [
        f"Order #{order.id}",
        f"Address: {address_label}",
        f"Page: {page}",
        "Available masters:",
    ]
    if masters:
        lines.extend(master_brief_line(master) for master in masters)
    else:
        lines.append("No available masters.")
    return "\n".join(lines)

CATEGORY_CHOICES: tuple[tuple[OrderCategory, str], ...] = (
    (OrderCategory.ELECTRICS, ""),
    (OrderCategory.PLUMBING, ""),
    (OrderCategory.APPLIANCES, " "),
    (OrderCategory.WINDOWS, "  "),
    (OrderCategory.HANDYMAN, " "),
    (OrderCategory.ROADSIDE, ""),
)
CATEGORY_LABELS = {category: label for category, label in CATEGORY_CHOICES}
CATEGORY_LABELS_BY_VALUE = {category.value: label for category, label in CATEGORY_CHOICES}
CATEGORY_VALUE_MAP = {category.value: category for category, _ in CATEGORY_CHOICES}
CATEGORY_CHOICE_ENTRIES: tuple[tuple[str, str], ...] = tuple(
    (category.value, label) for category, label in CATEGORY_CHOICES
)
STATUS_CHOICES = tuple((status.value, status.value) for status in OrderStatus)
_MAX_CITIES = 120
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
    type_label = order.type if not is_guarantee else f"{order.type} ()"
    normalized_category = normalize_category(getattr(order, "category", None))
    if normalized_category is not None:
        category_label = CATEGORY_LABELS.get(normalized_category, normalized_category.value)
    else:
        raw_cat = getattr(order, "category", "")
        category_label = str(raw_cat)

    lines_out = [
        f"<b>Заказ #{order.id}</b>",
        f"Статус: {html.escape(order.status)}",
        f"Тип: {html.escape(type_label)}",
        f"Категория: {html.escape(category_label)}",
        f"Слот: {html.escape(order.timeslot_local) if order.timeslot_local else '-'}",
        f"Адрес: {html.escape(address)}",
    ]
    if is_guarantee:
        lines_out.append("<b>   </b>")

    lines_out.append(f"Вложения: {len(order.attachments)}")
    lines_out.append("")
    lines_out.append(f"Клиент: {client_line}")
    master_display = master_line if master_line else "пока не назначен"
    lines_out.append(f"Мастер: {master_display}")
    lines_out.append("")
    lines_out.append("<b>Описание заявки</b>")
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
        lines_out.append(" ")

    return "\n".join(lines_out)


def _order_card_markup(order: OrderDetail, *, show_guarantee: bool = False, page: int = 1) -> InlineKeyboardMarkup:
    status = (order.status or '').upper()
    allow_return = status not in {'CANCELED', 'CLOSED'}
    allow_cancel = status not in {'CANCELED', 'CLOSED'}
    is_deferred = status == 'DEFERRED'  #   
    #  BUGFIX:   
    has_master = bool(order.master_id)
    return order_card_keyboard(
        order.id,
        attachments=order.attachments,
        allow_return=allow_return,
        allow_cancel=allow_cancel,
        show_guarantee=show_guarantee,
        is_deferred=is_deferred,
        page=page,  # P0-6:  page  
        has_master=has_master,  #  BUGFIX:    
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
    page: int = 1,  # P0-6:   
) -> None:
    text = _format_order_card_text(order, history)
    # P0-6:  page   
    markup = _order_card_markup(order, show_guarantee=show_guarantee, page=page)
    try:
        await _call_html(message.edit_text, text, reply_markup=markup)
    except TelegramBadRequest as exc:
        if exc.message == "Message is not modified":
            return
        await _call_html(message.answer, text, reply_markup=markup)



async def _return_order_to_search(
    cq: CallbackQuery, staff: StaffUser, order_id: int
) -> bool:
    """Shared routine to return order to search and refresh UI."""
    orders_service = get_service(cq.message.bot, "orders_service")
    visible_cities = visible_city_ids_for(staff)

    order = await _call_service(
        orders_service.get_card, order_id, city_ids=visible_cities
    )
    if not order:
        await _safe_answer(cq, QUEUE_RETURN_SUCCESS_MESSAGE, show_alert=True)
        return False
    if (
        staff.role is not StaffRole.GLOBAL_ADMIN
        and order.city_id not in staff.city_ids
    ):
        await _safe_answer(cq, QUEUE_RETURN_SUCCESS_MESSAGE, show_alert=True)
        return False

    ok = await orders_service.return_to_search(order_id, staff.id)
    if not ok:
        await _safe_answer(
            cq, QUEUE_RETURN_SUCCESS_MESSAGE, show_alert=True
        )
        return False

    updated = await _call_service(
        orders_service.get_card, order_id, city_ids=visible_cities
    )
    if not updated:
        await _safe_answer(cq, QUEUE_RETURN_SUCCESS_MESSAGE, show_alert=True)
        return False

    history = await _call_service(
        orders_service.list_status_history,
        order_id,
        limit=ORDER_CARD_HISTORY_LIMIT,
        city_ids=visible_cities,
    )
    show_guarantee = await _should_show_guarantee_button(
        updated, orders_service, visible_cities
    )
    await _render_order_card(
        cq.message, updated, history, show_guarantee=show_guarantee
    )
    await _safe_answer(cq, QUEUE_RETURN_SUCCESS_MESSAGE)
    return True


async def _clear_cancel_state(state: FSMContext) -> None:
    """Wrapper around typed clear_cancel_state for compatibility."""
    await typed_clear_cancel_state(state)


def _parse_category_filter(value: Optional[OrderCategory]) -> Optional[OrderCategory]:
    """Parse category filter (now already typed)."""
    return value


async def _available_cities(staff: StaffUser, orders_service) -> list[CityRef]:
    if staff.role is StaffRole.GLOBAL_ADMIN or not staff.city_ids:
        return await orders_service.list_cities(limit=_MAX_CITIES)
    result: list[CityRef] = []
    for city_id in sorted(staff.city_ids):
        city = await orders_service.get_city(city_id)
        if city:
            result.append(city)
    return result


def _filters_menu_keyboard(filters: Optional[QueueFilters] = None) -> InlineKeyboardMarkup:
    """P1:      order_id."""
    builder = InlineKeyboardBuilder()
    builder.button(text=" ", callback_data="adm:q:flt:city")
    builder.button(text=" ", callback_data="adm:q:flt:cat")
    builder.button(text=" ", callback_data="adm:q:flt:status")
    builder.button(text=" ", callback_data="adm:q:flt:master")
    builder.button(text=" ", callback_data="adm:q:flt:date")
    
    # P1:     ID (   order_id )
    if filters and filters.order_id:
        builder.button(text="  ID", callback_data="adm:q:flt:clear_id")
    
    builder.button(text=" ", callback_data="adm:q:flt:apply")
    builder.button(text=" ", callback_data="adm:q:flt:reset")
    builder.button(text=" ", callback_data="adm:q")
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
    filters: QueueFilters,
    orders_service,
    *,
    include_header: bool = True,
) -> str:
    lines: list[str] = []
    if include_header:
        lines.append("<b>Текущие фильтры</b>")
    
    city_text = ""
    if filters.city_id:
        city = await orders_service.get_city(filters.city_id)
        city_text = city.name if city else f"#{filters.city_id}"
    
    category_text = ""
    if filters.category:
        category_text = CATEGORY_LABELS.get(filters.category, filters.category.value)
    
    status_text = filters.status.value if filters.status else ""
    master_text = f"#{filters.master_id}" if filters.master_id else ""
    date_value = filters.date.isoformat() if filters.date else ""
    order_id_text = f"#{filters.order_id}" if filters.order_id else ""  # P1:   ID
    
    lines.extend([
        f"Город: {city_text or ''}",
        f"Категория: {category_text or ''}",
        f"Статус: {status_text or ''}",
        f"Мастер: {master_text or ''}",
        f"Дата: {date_value or ''}",
        f"ID заявки: {order_id_text or ''}",  # P1:   ID
    ])
    return "\n".join(lines)


async def _edit_or_reply(message: Message, text: str, markup: InlineKeyboardMarkup, state: FSMContext) -> None:
    try:
        await _call_html(message.edit_text, text, reply_markup=markup)
        await save_filters_message(state, message.chat.id, message.message_id)
    except TelegramBadRequest as exc:
        if exc.message == "Message is not modified":
            return
        sent = await _call_html(message.answer, text, reply_markup=markup)
        await save_filters_message(state, sent.chat.id, sent.message_id)


async def _render_filters_menu(message: Message, staff: StaffUser, state: FSMContext) -> None:
    orders_service = get_service(message.bot, "orders_service")
    filters = await load_queue_filters(state)
    text = await _format_filters_text(staff, filters, orders_service)
    await _edit_or_reply(message, text, _filters_menu_keyboard(filters), state)  # P1:  filters


async def _render_filters_by_ref(bot, staff: StaffUser, state: FSMContext) -> None:
    msg_ref = await load_filters_message(state)
    if not msg_ref:
        return
    
    orders_service = get_service(bot, "orders_service")
    filters = await load_queue_filters(state)
    text = await _format_filters_text(staff, filters, orders_service)
    markup = _filters_menu_keyboard(filters)  # P1:  filters
    
    try:
        await _call_html(bot.edit_message_text, 
            chat_id=msg_ref.chat_id,
            message_id=msg_ref.message_id,
            text=text,
            reply_markup=markup,
        )
    except TelegramBadRequest as exc:
        if exc.message != "Message is not modified":
            sent = await _call_html(bot.send_message, 
                msg_ref.chat_id,
                text,
                reply_markup=markup,
            )
            await save_filters_message(state, sent.chat.id, sent.message_id)
    else:
        await save_filters_message(state, msg_ref.chat_id, msg_ref.message_id)


async def _render_city_selection(message: Message, staff: StaffUser, state: FSMContext) -> None:
    orders_service = get_service(message.bot, "orders_service")
    cities = await _available_cities(staff, orders_service)
    filters = await load_queue_filters(state)
    await _edit_or_reply(
        message,
        "  :",
        _city_keyboard(cities, filters.city_id),
        state
    )


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
    filters = await load_queue_filters(state)
    page = max(page, 1)

    # Resolve city filter with RBAC
    city_filter = _resolve_city_filter(staff, filters.city_id)

    # Build query parameters
    timeslot_date = filters.date

    items: list[OrderListItem]
    has_next = False
    if city_filter == []:
        items = []
    else:
        list_queue = orders_service.list_queue
        params = inspect.signature(list_queue).parameters
        accepts_order_id = (
            "order_id" in params
            or any(p.kind == p.VAR_KEYWORD for p in params.values())
        )
        kwargs = {
            "city_ids": city_filter,
            "page": page,
            "page_size": QUEUE_PAGE_SIZE,
            "status_filter": filters.status,
            "category": filters.category,
            "master_id": filters.master_id,
            "timeslot_date": timeslot_date,
        }
        if accepts_order_id and filters.order_id is not None:
            kwargs["order_id"] = filters.order_id  # P1: legacy order id filter
        items, has_next = await list_queue(**kwargs)


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
    lines.append(f" : {page}")
    
    # P1-23: Add breadcrumbs navigation
    text_without_breadcrumbs = "\n".join(lines)
    text = add_breadcrumbs_to_text(text_without_breadcrumbs, AdminPaths.ORDERS_QUEUE)

    markup = queue_list_keyboard(items, page=page, has_next=has_next)
    await _edit_or_reply(message, text, markup, state)





# P1-11:    
def _queue_menu_markup() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="  ", callback_data="adm:q:search")  # P1-11:  
    builder.button(text=" ", callback_data="adm:q:flt")
    builder.button(text="  ", callback_data="adm:orders:queue:1")
    builder.button(text="  ", callback_data="adm:menu")
    builder.adjust(1)
    return builder.as_markup()


@queue_router.callback_query(
    F.data == "adm:orders_menu",
    StaffRoleFilter(_ALLOWED_ROLES),
)
async def cb_orders_menu(cq: CallbackQuery, staff: StaffUser) -> None:
    """Render main menu for orders sections."""
    orders_service = get_service(cq.message.bot, "orders_service")
    city_ids = visible_city_ids_for(staff)
    counts = await orders_service.count_orders_by_sections(city_ids)

    text = (
        "📋 <b>Управление заказами</b>\n\n"
        "Выберите раздел для работы с заказами."
    )

    markup = orders_menu(staff, counts)
    try:
        await _call_html(cq.message.edit_text, text, reply_markup=markup)
    except TelegramBadRequest as exc:
        if exc.message != "Message is not modified":
            await _call_html(cq.message.answer, text, reply_markup=markup)
    await _safe_answer(cq)


@queue_router.callback_query(
    F.data.startswith("adm:orders:queue:"),
    StaffRoleFilter(_ALLOWED_ROLES),
)
async def cb_orders_queue_list(cq: CallbackQuery, staff: StaffUser, state: FSMContext) -> None:
    """Display queue list via the orders menu entry."""
    try:
        page = int(cq.data.split(":")[3])
    except (IndexError, ValueError):
        await _safe_answer(cq, " ", show_alert=True)
        return

    await _render_queue_list(cq.message, staff, state, page)
    await _safe_answer(cq)


@queue_router.callback_query(
    F.data.startswith("adm:orders:warranty:"),
    StaffRoleFilter(_ALLOWED_ROLES),
)
async def cb_orders_warranty_list(cq: CallbackQuery, staff: StaffUser) -> None:
    """List orders that are within warranty period."""
    try:
        page = int(cq.data.split(":")[3])
    except (IndexError, ValueError):
        await _safe_answer(cq, " ", show_alert=True)
        return

    orders_service = get_service(cq.message.bot, "orders_service")
    city_filter = visible_city_ids_for(staff)

    items, has_next = await orders_service.list_warranty_orders(
        city_ids=city_filter,
        page=page,
        page_size=QUEUE_PAGE_SIZE,
    )

    lines = ["<b>   </b>"]
    if items:
        lines.append("")
        lines.extend(_format_order_line(item) for item in items)
    else:
        lines.append("")
        lines.append("  ")
    lines.append("")
    lines.append(f" : {page}")

    text = "\n".join(lines)

    kb = InlineKeyboardBuilder()
    for order in items:
        kb.button(text=f"#{order.id}", callback_data=f"adm:q:card:{order.id}")
    if items:
        kb.adjust(1)

    nav = InlineKeyboardBuilder()
    nav_count = 0
    if page > 1:
        nav.button(text=" ", callback_data=f"adm:orders:warranty:{page - 1}")
        nav_count += 1
    if has_next:
        nav.button(text=" ", callback_data=f"adm:orders:warranty:{page + 1}")
        nav_count += 1
    if nav_count:
        nav.adjust(nav_count)
        kb.attach(nav)

    kb.button(text=" ", callback_data="adm:orders_menu")
    markup = kb.as_markup()

    try:
        await _call_html(cq.message.edit_text, text, reply_markup=markup)
    except TelegramBadRequest as exc:
        if exc.message != "Message is not modified":
            await _call_html(cq.message.answer, text, reply_markup=markup)

    await _safe_answer(cq)


@queue_router.callback_query(
    F.data.startswith("adm:orders:closed:"),
    StaffRoleFilter(_ALLOWED_ROLES),
)
async def cb_orders_closed_list(cq: CallbackQuery, staff: StaffUser) -> None:
    """List orders whose warranty period has finished."""
    try:
        page = int(cq.data.split(":")[3])
    except (IndexError, ValueError):
        await _safe_answer(cq, " ", show_alert=True)
        return

    orders_service = get_service(cq.message.bot, "orders_service")
    city_filter = visible_city_ids_for(staff)

    items, has_next = await orders_service.list_closed_orders(
        city_ids=city_filter,
        page=page,
        page_size=QUEUE_PAGE_SIZE,
    )

    lines = ["<b>  </b>"]
    if items:
        lines.append("")
        lines.extend(_format_order_line(item) for item in items)
    else:
        lines.append("")
        lines.append("  ")
    lines.append("")
    lines.append(f" : {page}")

    text = "\n".join(lines)

    kb = InlineKeyboardBuilder()
    for order in items:
        kb.button(text=f"#{order.id}", callback_data=f"adm:q:card:{order.id}")
    if items:
        kb.adjust(1)

    nav = InlineKeyboardBuilder()
    nav_count = 0
    if page > 1:
        nav.button(text=" ", callback_data=f"adm:orders:closed:{page - 1}")
        nav_count += 1
    if has_next:
        nav.button(text=" ", callback_data=f"adm:orders:closed:{page + 1}")
        nav_count += 1
    if nav_count:
        nav.adjust(nav_count)
        kb.attach(nav)

    kb.button(text=" ", callback_data="adm:orders_menu")
    markup = kb.as_markup()

    try:
        await _call_html(cq.message.edit_text, text, reply_markup=markup)
    except TelegramBadRequest as exc:
        if exc.message != "Message is not modified":
            await _call_html(cq.message.answer, text, reply_markup=markup)

    await _safe_answer(cq)


@queue_router.callback_query(
    F.data == "adm:q",
    StaffRoleFilter(_ALLOWED_ROLES),
)
async def cb_queue_menu(cq: CallbackQuery, staff: StaffUser) -> None:
    await _call_html(cq.message.edit_text, "📋 <b>Меню очереди</b>", reply_markup=_queue_menu_markup())
    await _safe_answer(cq)


@queue_router.callback_query(
    F.data == "adm:q:flt",
    StaffRoleFilter(_ALLOWED_ROLES),
)
async def cb_queue_filters_root(cq: CallbackQuery, staff: StaffUser, state: FSMContext) -> None:
    await load_queue_filters(state)
    await _render_filters_menu(cq.message, staff, state)
    await _safe_answer(cq)


@queue_router.callback_query(
    F.data == "adm:q:flt:city",
    StaffRoleFilter(_ALLOWED_ROLES),
)
async def cb_queue_filters_city(cq: CallbackQuery, staff: StaffUser, state: FSMContext) -> None:
    await _render_city_selection(cq.message, staff, state)
    await _safe_answer(cq)


@queue_router.callback_query(
    F.data.startswith("adm:q:flt:c:"),
    StaffRoleFilter(_ALLOWED_ROLES),
)
async def cb_queue_filters_city_pick(cq: CallbackQuery, staff: StaffUser, state: FSMContext) -> None:
    filters = await load_queue_filters(state)
    payload = cq.data.split(":")[-1]
    
    if payload == "0":
        filters.city_id = None
    else:
        try:
            filters.city_id = int(payload)
        except ValueError:
            await _safe_answer(cq, "  ID ", show_alert=True)
            return
    
    await save_queue_filters(state, filters)
    await _render_filters_menu(cq.message, staff, state)
    await _safe_answer(cq)


@queue_router.callback_query(
    F.data == "adm:q:flt:cat",
    StaffRoleFilter(_ALLOWED_ROLES),
)
async def cb_queue_filters_category(cq: CallbackQuery, staff: StaffUser, state: FSMContext) -> None:
    filters = await load_queue_filters(state)
    selected_value = filters.category.value if filters.category else None
    await _render_choice(
        cq.message,
        entries=CATEGORY_CHOICE_ENTRIES,
        prefix="adm:q:flt:cat",
        selected=selected_value,
        state=state,
        title="  :",
    )
    await _safe_answer(cq)


@queue_router.callback_query(
    F.data.startswith("adm:q:flt:cat:"),
    StaffRoleFilter(_ALLOWED_ROLES),
)
async def cb_queue_filters_category_pick(cq: CallbackQuery, staff: StaffUser, state: FSMContext) -> None:
    value = cq.data.split(":")[-1]
    filters = await load_queue_filters(state)
    
    if value == "clr":
        filters.category = None
    else:
        if value not in CATEGORY_VALUE_MAP:
            await _safe_answer(cq, "  ", show_alert=True)
            return
        filters.category = CATEGORY_VALUE_MAP[value]
    
    await save_queue_filters(state, filters)
    await _render_filters_menu(cq.message, staff, state)
    await _safe_answer(cq)


@queue_router.callback_query(
    F.data == "adm:q:flt:status",
    StaffRoleFilter(_ALLOWED_ROLES),
)
async def cb_queue_filters_status(cq: CallbackQuery, staff: StaffUser, state: FSMContext) -> None:
    filters = await load_queue_filters(state)
    selected_value = filters.status.value if filters.status else None
    await _render_choice(
        cq.message,
        entries=STATUS_CHOICES,
        prefix="adm:q:flt:st",
        selected=selected_value,
        state=state,
        title="  :",
    )
    await _safe_answer(cq)


@queue_router.callback_query(
    F.data.startswith("adm:q:flt:st:"),
    StaffRoleFilter(_ALLOWED_ROLES),
)
async def cb_queue_filters_status_pick(cq: CallbackQuery, staff: StaffUser, state: FSMContext) -> None:
    value = cq.data.split(":")[-1]
    filters = await load_queue_filters(state)
    
    if value == "clr":
        filters.status = None
    else:
        status_enum = normalize_status(value)
        if not status_enum:
            await _safe_answer(cq, "  ", show_alert=True)
            return
        filters.status = status_enum
    
    await save_queue_filters(state, filters)
    await _render_filters_menu(cq.message, staff, state)
    await _safe_answer(cq)


@queue_router.callback_query(
    F.data == "adm:q:flt:master",
    StaffRoleFilter(_ALLOWED_ROLES),
)
async def cb_queue_filters_master(cq: CallbackQuery, staff: StaffUser, state: FSMContext) -> None:
    await state.set_state(QueueFiltersFSM.master)
    await _safe_answer(cq, " ID  ", show_alert=True)


@queue_router.message(
    StateFilter(QueueFiltersFSM.master),
    StaffRoleFilter(_ALLOWED_ROLES),
)
async def cb_queue_filters_master_input(msg: Message, staff: StaffUser, state: FSMContext) -> None:
    text = msg.text.strip()
    filters = await load_queue_filters(state)
    
    if text == "-":
        filters.master_id = None
    else:
        if not text.isdigit():
            await _call_html(msg.answer, " ID    .    '-'  .")
            return
        filters.master_id = int(text)
    
    # Save message ref before clearing state
    msg_ref = await load_filters_message(state)
    
    await state.clear()
    await save_queue_filters(state, filters)
    
    # Restore message ref
    if msg_ref:
        await save_filters_message(state, msg_ref.chat_id, msg_ref.message_id)
    
    await _render_filters_by_ref(msg.bot, staff, state)


@queue_router.callback_query(
    F.data == "adm:q:flt:date",
    StaffRoleFilter(_ALLOWED_ROLES),
)
async def cb_queue_filters_date(cq: CallbackQuery, staff: StaffUser, state: FSMContext) -> None:
    await state.set_state(QueueFiltersFSM.date)
    await _safe_answer(cq, "  YYYY-MM-DD  '-'  ", show_alert=True)


@queue_router.message(
    StateFilter(QueueFiltersFSM.date),
    StaffRoleFilter(_ALLOWED_ROLES),
)
async def cb_queue_filters_date_input(msg: Message, staff: StaffUser, state: FSMContext) -> None:
    text = msg.text.strip()
    filters = await load_queue_filters(state)
    
    if text == "-":
        filters.date = None
    else:
        try:
            filters.date = date.fromisoformat(text)
        except ValueError:
            await _call_html(msg.answer, "   .  YYYY-MM-DD  '-'  .")
            return
    
    # Save message ref before clearing state
    msg_ref = await load_filters_message(state)
    
    await state.clear()
    await save_queue_filters(state, filters)
    
    # Restore message ref
    if msg_ref:
        await save_filters_message(state, msg_ref.chat_id, msg_ref.message_id)
    
    await _render_filters_by_ref(msg.bot, staff, state)


@queue_router.callback_query(
    F.data == "adm:q:flt:reset",
    StaffRoleFilter(_ALLOWED_ROLES),
)
async def cb_queue_filters_reset(cq: CallbackQuery, staff: StaffUser, state: FSMContext) -> None:
    filters = QueueFilters()  # Create default filters
    await save_queue_filters(state, filters)
    await _render_filters_menu(cq.message, staff, state)
    await _safe_answer(cq, "  ")


@queue_router.callback_query(
    F.data == "adm:q:flt:apply",
    StaffRoleFilter(_ALLOWED_ROLES),
)
async def cb_queue_filters_apply(cq: CallbackQuery, staff: StaffUser, state: FSMContext) -> None:
    await _render_queue_list(cq.message, staff, state, page=1)
    await _safe_answer(cq)


@queue_router.callback_query(
    F.data.startswith("adm:q:list:"),
    StaffRoleFilter(_ALLOWED_ROLES),
)
async def cb_queue_list(cq: CallbackQuery, staff: StaffUser, state: FSMContext) -> None:
    try:
        page = int(cq.data.split(":")[3])
    except (IndexError, ValueError):
        await _safe_answer(cq, " ", show_alert=True)
        return
    await _render_queue_list(cq.message, staff, state, page=page)
    await _safe_answer(cq)


@queue_router.callback_query(
    F.data.startswith("adm:q:card:"),
    StaffRoleFilter(_ALLOWED_ROLES),
)
async def cb_queue_card(cq: CallbackQuery, staff: StaffUser, state: FSMContext) -> None:
    parts = cq.data.split(':')
    try:
        order_id = int(parts[3])
        # P0-6:    (  1)
        page = int(parts[4]) if len(parts) > 4 else 1
    except (IndexError, ValueError):
        await _safe_answer(cq, '  ', show_alert=True)
        return
    orders_service = get_service(cq.message.bot, 'orders_service')
    order = await _call_service(orders_service.get_card, order_id, city_ids=visible_city_ids_for(staff))
    if not order:
        await _safe_answer(cq, '  ', show_alert=True)
        return
    if staff.role is not StaffRole.GLOBAL_ADMIN and order.city_id not in staff.city_ids:
        await _safe_answer(cq, '   ', show_alert=True)
        return
    history = await _call_service(orders_service.list_status_history, order_id, limit=ORDER_CARD_HISTORY_LIMIT, city_ids=visible_city_ids_for(staff))
    show_guarantee = await _should_show_guarantee_button(order, orders_service, visible_city_ids_for(staff))
    # P0-6:  page    
    await _render_order_card(cq.message, order, history, show_guarantee=show_guarantee, page=page)
    await _safe_answer(cq)

@queue_router.callback_query(
    F.data.regexp(r'^adm:q:as:\d+$'),
    StaffRoleFilter(_ALLOWED_ROLES),
)
async def cb_queue_assign_menu(cq: CallbackQuery, staff: StaffUser) -> None:
    order_id = int(cq.data.split(':')[3])
    orders_service = get_service(cq.message.bot, 'orders_service')
    order = await _call_service(orders_service.get_card, order_id, city_ids=visible_city_ids_for(staff))
    if not order:
        await _safe_answer(cq, '  ', show_alert=True)
        return
    if staff.role is not StaffRole.GLOBAL_ADMIN and order.city_id not in staff.city_ids:
        await _safe_answer(cq, '   ', show_alert=True)
        return
    address_bits = [bit for bit in (order.city_name, order.district_name, order.street_name) if bit]
    if order.house:
        address_bits.append(str(order.house))
    address_label = ', '.join(address_bits) if address_bits else '-'
    text = (
        f" #{order.id}\n"
        f": {address_label}\n\n"
        "Выберите способ распределения."
    )
    allow_auto = bool(order.district_id)
    markup = assign_menu_keyboard(order.id, allow_auto=allow_auto)
    try:
        await _call_html(cq.message.edit_text, text, reply_markup=markup)
    except TelegramBadRequest as exc:
        if exc.message == 'Message is not modified':
            await _safe_answer(cq)
            return
        await _call_html(cq.message.answer, text, reply_markup=markup)
    await _safe_answer(cq)








@queue_router.callback_query(
    F.data.startswith("adm:q:as:auto:") & ~F.data.contains(":force:"),
    StaffRoleFilter(_ALLOWED_ROLES),
)
async def cb_queue_assign_auto(cq: CallbackQuery, staff: StaffUser) -> None:
    parts = cq.data.split(":")
    try:
        order_id = int(parts[4])
    except (IndexError, ValueError):
        await _safe_answer(cq, " ", show_alert=True)
        return

    orders_service = get_service(cq.message.bot, "orders_service")
    distribution_service = get_service(cq.message.bot, "distribution_service")
    order = await _call_service(orders_service.get_card, order_id, city_ids=visible_city_ids_for(staff))
    if not order:
        await _safe_answer(cq, "  ", show_alert=True)
        return
    if staff.role is not StaffRole.GLOBAL_ADMIN and order.city_id not in staff.city_ids:
        await _safe_answer(cq, "    ", show_alert=True)
        return

    #    DEFERRED
    if (order.status or "").upper() == "DEFERRED":
        builder = InlineKeyboardBuilder()
        builder.button(text=" , ", callback_data=f"adm:q:as:auto:force:{order_id}")
        builder.button(text=" ", callback_data=f"adm:q:card:{order_id}")
        builder.adjust(2)
        
        try:
            await _call_html(cq.message.edit_text, 
                f" <b> #{order.id}   </b>\n\n"
                "  .     .\n\n"
                "  ?",
                reply_markup=builder.as_markup(),
            )
        except TelegramBadRequest:
            await _call_html(cq.message.answer, 
                f" <b> #{order.id}   </b>\n\n"
                "  .     .\n\n"
                "  ?",
                reply_markup=builder.as_markup(),
            )
        await _safe_answer(cq)
        return

    # P0-8:    
    await _safe_answer(cq, "  ...", show_alert=False)
    
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
    builder.button(text="  ", callback_data=f"adm:q:card:{order_id}")
    builder.button(text=" ", callback_data=f"adm:q:as:{order_id}")
    builder.adjust(1)

    try:
        await _call_html(cq.message.edit_text, text_body, reply_markup=builder.as_markup())
    except TelegramBadRequest as exc:
        if exc.message != "Message is not modified":
            await _call_html(cq.message.answer, text_body, reply_markup=builder.as_markup())

    if ok:
        await _safe_answer(cq, " ", show_alert=False)
    else:
        alert_codes = {"no_district", "no_category", "forbidden", "not_found", "offer_conflict"}
        await _safe_answer(cq, result.message, show_alert=result.code in alert_codes)


@queue_router.callback_query(
    F.data.startswith("adm:q:as:auto:force:"),
    StaffRoleFilter(_ALLOWED_ROLES),
)
async def cb_queue_assign_auto_force(cq: CallbackQuery, staff: StaffUser) -> None:
    """   DEFERRED ."""
    parts = cq.data.split(":")
    try:
        order_id = int(parts[5])
    except (IndexError, ValueError):
        await _safe_answer(cq, " ", show_alert=True)
        return

    orders_service = get_service(cq.message.bot, "orders_service")
    distribution_service = get_service(cq.message.bot, "distribution_service")
    order = await _call_service(orders_service.get_card, order_id, city_ids=visible_city_ids_for(staff))
    if not order:
        await _safe_answer(cq, "  ", show_alert=True)
        return
    if staff.role is not StaffRole.GLOBAL_ADMIN and order.city_id not in staff.city_ids:
        await _safe_answer(cq, "    ", show_alert=True)
        return

    # P0-8:     
    await _safe_answer(cq, "  ...", show_alert=False)
    
    ok, result = await distribution_service.assign_auto(order_id, staff.id)

    lines: list[str] = [f" #{order.id}"]
    lines.append(" ." if ok else "   .")
    lines.append("")
    lines.append(result.message)
    if not ok and result.code == "no_candidates":
        lines.append("")
        lines.append("  .   .")

    text_body = "\n".join(lines)

    builder = InlineKeyboardBuilder()
    builder.button(text=" ", callback_data=f"adm:q:card:{order_id}")
    builder.button(text="", callback_data=f"adm:q:as:{order_id}")
    builder.adjust(1)

    try:
        await _call_html(cq.message.edit_text, text_body, reply_markup=builder.as_markup())
    except TelegramBadRequest as exc:
        if exc.message != "Message is not modified":
            await _call_html(cq.message.answer, text_body, reply_markup=builder.as_markup())

    if ok:
        await _safe_answer(cq, " ", show_alert=False)
    else:
        alert_codes = {"no_district", "no_category", "forbidden", "not_found", "offer_conflict"}
        await _safe_answer(cq, result.message, show_alert=result.code in alert_codes)


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
        await _safe_answer(cq, " ", show_alert=True)
        return

    orders_service = get_service(cq.message.bot, "orders_service")
    order = await _call_service(orders_service.get_card, order_id, city_ids=visible_city_ids_for(staff))
    if not order:
        await _safe_answer(cq, "  ", show_alert=True)
        return
    if staff.role is not StaffRole.GLOBAL_ADMIN and order.city_id not in staff.city_ids:
        await _safe_answer(cq, "    ", show_alert=True)
        return

    #    DEFERRED
    warning_prefix = ""
    if (order.status or "").upper() == "DEFERRED":
        warning_prefix = " <b>   ( )</b>\n\n"

    # P0-8:      
    await _safe_answer(cq, "   ...", show_alert=False)
    
    masters, has_next = await orders_service.manual_candidates(
        order_id,
        page=page,
        page_size=MANUAL_PAGE_SIZE,
        city_ids=visible_city_ids_for(staff),
    )
    text = warning_prefix + _manual_candidates_text(order, masters, page)
    markup = manual_candidates_keyboard(order.id, masters, page=page, has_next=has_next)
    try:
        await _call_html(cq.message.edit_text, 
            text,
            reply_markup=markup,
            disable_web_page_preview=True,
        )
    except TelegramBadRequest as exc:
        if exc.message != "Message is not modified":
            await _call_html(cq.message.answer, 
                text,
                reply_markup=markup,
                disable_web_page_preview=True,
            )
    await _safe_answer(cq)


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
        await _safe_answer(cq, " ", show_alert=True)
        return

    orders_service = get_service(cq.message.bot, "orders_service")
    order = await _call_service(orders_service.get_card, order_id, city_ids=visible_city_ids_for(staff))
    if not order:
        await _safe_answer(cq, "  ", show_alert=True)
        return
    if staff.role is not StaffRole.GLOBAL_ADMIN and order.city_id not in staff.city_ids:
        await _safe_answer(cq, "   ", show_alert=True)
        return

    masters, _ = await orders_service.manual_candidates(
        order_id,
        page=page,
        page_size=MANUAL_PAGE_SIZE,
        city_ids=visible_city_ids_for(staff),
    )
    candidate = next((m for m in masters if m.id == master_id), None)
    if candidate is None:
        await _safe_answer(cq, "    .  .", show_alert=True)
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
        # P0-8:     
        await _safe_answer(cq, "   ...", show_alert=False)
        
        distribution_service = get_service(cq.message.bot, "distribution_service")
        ok, message = await distribution_service.send_manual_offer(
            order_id,
            master_id,
            staff.id,
        )
        if not ok:
            await _safe_answer(cq, message, show_alert=True)
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
            await _call_html(cq.message.edit_text, 
                "\n".join(text_lines),
                reply_markup=builder.as_markup(),
            )
        except TelegramBadRequest as exc:
            if exc.message != "Message is not modified":
                await _call_html(cq.message.answer, 
                    "\n".join(text_lines),
                    reply_markup=builder.as_markup(),
                )
        await _safe_answer(cq, " ")
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
        await _call_html(cq.message.edit_text, 
            "\n".join(text_lines),
            reply_markup=markup,
            disable_web_page_preview=True,
        )
    except TelegramBadRequest as exc:
        if exc.message != "Message is not modified":
            await _call_html(cq.message.answer, 
                "\n".join(text_lines),
                reply_markup=markup,
                disable_web_page_preview=True,
            )
    await _safe_answer(cq)


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
        await _safe_answer(cq, " ", show_alert=True)
        return

    orders_service = get_service(cq.message.bot, "orders_service")
    order = await orders_service.get_card(order_id, city_ids=visible_city_ids_for(staff))
    if not order:
        await _safe_answer(cq, "  ", show_alert=True)
        return
    if staff.role is not StaffRole.GLOBAL_ADMIN and order.city_id not in staff.city_ids:
        await _safe_answer(cq, "   ", show_alert=True)
        return

    distribution_service = get_service(cq.message.bot, "distribution_service")
    ok, message = await distribution_service.send_manual_offer(
        order_id,
        master_id,
        staff.id,
    )
    if not ok:
        await _safe_answer(cq, message, show_alert=True)
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
        await _call_html(cq.message.edit_text, 
            "\n".join(text_lines),
            reply_markup=builder.as_markup(),
        )
    except TelegramBadRequest as exc:
        if exc.message != "Message is not modified":
            await _call_html(cq.message.answer, 
                "\n".join(text_lines),
                reply_markup=builder.as_markup(),
            )
    await _safe_answer(cq, " ")




@queue_router.callback_query(
    F.data.startswith("adm:q:activate:"),
    StaffRoleFilter(_ALLOWED_ROLES),
)
async def cb_queue_activate_deferred(cq: CallbackQuery, staff: StaffUser) -> None:
    """ DEFERRED  (  PENDING)."""
    parts = cq.data.split(":")
    try:
        order_id = int(parts[3])
    except (IndexError, ValueError):
        await _safe_answer(cq, " ", show_alert=True)
        return

    orders_service = get_service(cq.message.bot, "orders_service")
    order = await _call_service(orders_service.get_card, order_id, city_ids=visible_city_ids_for(staff))
    if not order:
        await _safe_answer(cq, "  ", show_alert=True)
        return
    if staff.role is not StaffRole.GLOBAL_ADMIN and order.city_id not in staff.city_ids:
        await _safe_answer(cq, "    ", show_alert=True)
        return

    #  DEFERRED  PENDING
    ok = await orders_service.activate_deferred_order(order_id, staff.id)
    
    if not ok:
        await _safe_answer(cq, "   ", show_alert=True)
        return
    
    #  
    updated = await _call_service(orders_service.get_card, order_id, city_ids=visible_city_ids_for(staff))
    if not updated:
        await _safe_answer(cq, "  ", show_alert=True)
        return
    
    history = await _call_service(
        orders_service.list_status_history,
        order_id,
        limit=ORDER_CARD_HISTORY_LIMIT,
        city_ids=visible_city_ids_for(staff)
    )
    
    show_guarantee = await _should_show_guarantee_button(updated, orders_service, visible_city_ids_for(staff))
    await _render_order_card(cq.message, updated, history, show_guarantee=show_guarantee)
    await _safe_answer(cq, "     ")


@queue_router.callback_query(
    F.data.startswith("adm:q:gar:"),
    StaffRoleFilter(_ALLOWED_ROLES),
)
async def cb_queue_guarantee(cq: CallbackQuery, staff: StaffUser) -> None:
    parts = cq.data.split(":")
    try:
        order_id = int(parts[3])
    except (IndexError, ValueError):
        await _safe_answer(cq, "  ", show_alert=True)
        return

    orders_service = get_service(cq.message.bot, "orders_service")
    order = await orders_service.get_card(order_id, city_ids=visible_city_ids_for(staff))
    if not order:
        await _safe_answer(cq, "  ", show_alert=True)
        return
    if staff.role is not StaffRole.GLOBAL_ADMIN and order.city_id not in staff.city_ids:
        await _safe_answer(cq, "   ", show_alert=True)
        return

    status = (order.status or "").upper()
    if status != "CLOSED":
        await _safe_answer(cq, "      ", show_alert=True)
        return
    if order.order_type is OrderType.GUARANTEE:
        await _safe_answer(cq, "   ", show_alert=True)
        return
    if not order.master_id:
        await _safe_answer(cq, "    ", show_alert=True)
        return
    if await _call_service(orders_service.has_active_guarantee, order.id, city_ids=visible_city_ids_for(staff)):
        await _safe_answer(cq, "   ", show_alert=True)
        return

    try:
        new_order_id = await orders_service.create_guarantee_order(order.id, staff.id)
    except GuaranteeError as exc:
        await _safe_answer(cq, str(exc), show_alert=True)
        return

    updated = await _call_service(orders_service.get_card, order_id, city_ids=visible_city_ids_for(staff))
    history = await _call_service(orders_service.list_status_history, order_id, limit=ORDER_CARD_HISTORY_LIMIT, city_ids=visible_city_ids_for(staff))
    await _render_order_card(cq.message, updated or order, history, show_guarantee=False)

    await _call_html(cq.message.answer, 
        f"  #{new_order_id}     ."
    )
    await _safe_answer(cq)


@queue_router.callback_query(
    F.data.startswith("adm:q:ret:"),
    StaffRoleFilter(_ALLOWED_ROLES),
)
async def cb_queue_return(cq: CallbackQuery, staff: StaffUser) -> None:
    """P0-3:       ."""
    parts = cq.data.split(":")
    try:
        order_id = int(parts[3])
        # P0-6:  page  
        page = int(parts[4]) if len(parts) > 4 else 1
    except (IndexError, ValueError):
        await _safe_answer(cq, "  ID ", show_alert=True)
        return
    
    await _return_order_to_search(cq, staff, order_id)


@queue_router.callback_query(
    F.data.startswith("adm:q:ret:confirm:"),
    StaffRoleFilter(_ALLOWED_ROLES),
)
async def cb_queue_return_confirm(cq: CallbackQuery, staff: StaffUser) -> None:
    """P0-3:       ."""
    parts = cq.data.split(":")
    try:
        order_id = int(parts[4])
    except (IndexError, ValueError):
        await _safe_answer(cq, "  ID ", show_alert=True)
        return
    
    await _return_order_to_search(cq, staff, order_id)


@queue_router.callback_query(
    F.data.startswith("adm:q:cnl:"),
    StaffRoleFilter(_ALLOWED_ROLES),
)
async def cb_queue_cancel_start(cq: CallbackQuery, staff: StaffUser, state: FSMContext) -> None:
    parts = cq.data.split(":")
    try:
        order_id = int(parts[3])
    except (IndexError, ValueError):
        await _safe_answer(cq, "  ID ", show_alert=True)
        return
    
    orders_service = get_service(cq.message.bot, "orders_service")
    order = await _call_service(
        orders_service.get_card,
        order_id,
        city_ids=visible_city_ids_for(staff)
    )
    
    if not order:
        await _safe_answer(cq, QUEUE_RETURN_SUCCESS_MESSAGE, show_alert=True)
        return
    
    if staff.role is not StaffRole.GLOBAL_ADMIN and order.city_id not in staff.city_ids:
        await _safe_answer(cq, QUEUE_RETURN_SUCCESS_MESSAGE, show_alert=True)
        return
    
    await state.set_state(QueueActionFSM.cancel_reason)
    await save_cancel_state(state, order_id, cq.message.chat.id, cq.message.message_id)
    
    await _call_html(cq.message.edit_text, 
        f"     #{order_id}\n\n"
        f" {CANCEL_REASON_MIN}  (    ).\n"
        f"   /cancel",
        reply_markup=queue_cancel_keyboard(order_id),
    )
    await _safe_answer(cq)


@queue_router.callback_query(
    F.data.startswith("adm:q:cnl:bk:"),
    StaffRoleFilter(_ALLOWED_ROLES),
)
async def cb_queue_cancel_back(cq: CallbackQuery, staff: StaffUser, state: FSMContext) -> None:
    parts = cq.data.split(":")
    try:
        order_id = int(parts[4])
    except (IndexError, ValueError):
        await _safe_answer(cq, " ", show_alert=True)
        return
    orders_service = get_service(cq.message.bot, "orders_service")
    order = await _call_service(orders_service.get_card, order_id, city_ids=visible_city_ids_for(staff))
    if not order:
        await _clear_cancel_state(state)
        await _safe_answer(cq, "  ", show_alert=True)
        return
    if staff.role is not StaffRole.GLOBAL_ADMIN and order.city_id not in staff.city_ids:
        await _clear_cancel_state(state)
        await _safe_answer(cq, "   ", show_alert=True)
        return
    history = await _call_service(orders_service.list_status_history, order_id, limit=ORDER_CARD_HISTORY_LIMIT, city_ids=visible_city_ids_for(staff))
    show_guarantee = await _should_show_guarantee_button(order, orders_service, visible_city_ids_for(staff))
    await _render_order_card(cq.message, order, history, show_guarantee=show_guarantee)
    await _clear_cancel_state(state)
    await _safe_answer(cq)


@queue_router.message(
    StateFilter(QueueActionFSM.cancel_reason),
    StaffRoleFilter(_ALLOWED_ROLES),
    F.text == "/cancel",
)
async def queue_cancel_abort(msg: Message, staff: StaffUser, state: FSMContext) -> None:
    cancel_state = await load_cancel_state(state)
    await _clear_cancel_state(state)
    
    await _call_html(msg.answer, " .")
    
    if not cancel_state:
        return
    
    orders_service = get_service(msg.bot, "orders_service")
    order = await _call_service(
        orders_service.get_card,
        cancel_state.order_id,
        city_ids=visible_city_ids_for(staff)
    )
    
    if not order:
        return
    
    if staff.role is not StaffRole.GLOBAL_ADMIN and order.city_id not in staff.city_ids:
        return
    
    history = await _call_service(
        orders_service.list_status_history,
        cancel_state.order_id,
        limit=ORDER_CARD_HISTORY_LIMIT,
        city_ids=visible_city_ids_for(staff)
    )
    
    text_body = _format_order_card_text(order, history)
    show_guarantee = await _should_show_guarantee_button(
        order,
        orders_service,
        visible_city_ids_for(staff)
    )
    markup = _order_card_markup(order, show_guarantee=show_guarantee)
    
    try:
        await _call_html(msg.bot.edit_message_text, 
            chat_id=cancel_state.chat_id,
            message_id=cancel_state.message_id,
            text=text_body,
            reply_markup=markup,
        )
    except TelegramBadRequest as exc:
        if exc.message != "Message is not modified":
            await _call_html(msg.bot.send_message, 
                cancel_state.chat_id,
                text_body,
                reply_markup=markup,
            )


@queue_router.message(
    StateFilter(QueueActionFSM.cancel_reason),
    StaffRoleFilter(_ALLOWED_ROLES),
)
async def queue_cancel_reason(msg: Message, staff: StaffUser, state: FSMContext) -> None:
    text_raw = msg.text or ""
    reason = text_raw
    
    # Validate reason length
    if text_raw.strip() and len(text_raw.strip()) < CANCEL_REASON_MIN:
        await _call_html(
            msg.answer,
            f"       {CANCEL_REASON_MIN}  "
            f"( {CANCEL_REASON_MAX})."
        )
        return
    
    cancel_state = await load_cancel_state(state)
    
    if not cancel_state:
        await _clear_cancel_state(state)
        await _call_html(msg.answer, " :    .  .")
        return
    orders_service = get_service(msg.bot, "orders_service")
    order = await _call_service(
        orders_service.get_card,
        cancel_state.order_id,
        city_ids=visible_city_ids_for(staff)
    )
    
    if not order:
        await _clear_cancel_state(state)
        await _call_html(msg.answer, "   .")
        return
    
    if staff.role is not StaffRole.GLOBAL_ADMIN and order.city_id not in staff.city_ids:
        await _clear_cancel_state(state)
        await _call_html(msg.answer, "     .")
        return
    
    ok = await orders_service.cancel(
        cancel_state.order_id,
        reason=reason,
        by_staff_id=staff.id
    )
    
    if ok:
        await _call_html(msg.answer, " .")
    else:
        await _call_html(msg.answer, "   .")
    
    updated = await _call_service(
        orders_service.get_card,
        cancel_state.order_id,
        city_ids=visible_city_ids_for(staff)
    )
    
    if updated:
        history = await _call_service(
            orders_service.list_status_history,
            cancel_state.order_id,
            limit=ORDER_CARD_HISTORY_LIMIT,
            city_ids=visible_city_ids_for(staff)
        )
        text_body = _format_order_card_text(updated, history)
        markup = _order_card_markup(updated)
        
        try:
            await _call_html(msg.bot.edit_message_text, 
                chat_id=cancel_state.chat_id,
                message_id=cancel_state.message_id,
                text=text_body,
                reply_markup=markup,
            )
        except TelegramBadRequest as exc:
            if exc.message != "Message is not modified":
                await _call_html(msg.bot.send_message, 
                    cancel_state.chat_id,
                    text_body,
                    reply_markup=markup,
                )
    
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
        await _safe_answer(cq, ' ', show_alert=True)
        return
    orders_service = get_service(cq.message.bot, 'orders_service')
    order = await _call_service(orders_service.get_card, order_id, city_ids=visible_city_ids_for(staff))
    if not order:
        await _safe_answer(cq, '  ', show_alert=True)
        return
    if staff.role is not StaffRole.GLOBAL_ADMIN and order.city_id not in staff.city_ids:
        await _safe_answer(cq, '   ', show_alert=True)
        return
    attachment = await _call_service(orders_service.get_order_attachment, order_id, attachment_id, city_ids=visible_city_ids_for(staff))
    if not attachment:
        await _safe_answer(cq, '  ', show_alert=True)
        return
    caption = attachment.caption or None
    file_type = (attachment.file_type or '').upper()
    try:
        if file_type.endswith('PHOTO'):
            await cq.message.answer_photo(attachment.file_id, caption=caption)
        else:
            await cq.message.answer_document(attachment.file_id, caption=caption)
    except TelegramBadRequest as exc:
        await _safe_answer(cq, f'   : {exc.message}', show_alert=True)
        return
    await _safe_answer(cq)

# P1-11:   
@queue_router.callback_query(
    F.data == "adm:q:search",
    StaffRoleFilter(_ALLOWED_ROLES),
)
async def cb_queue_search_start(cq: CallbackQuery, staff: StaffUser, state: FSMContext) -> None:
    """P1-11:    -   ."""
    builder = InlineKeyboardBuilder()
    builder.button(text="  ID ", callback_data="adm:q:search:type:id")
    builder.button(text="   ", callback_data="adm:q:search:type:phone")
    builder.button(text="  ", callback_data="adm:q:search:type:master")
    builder.button(text=" ", callback_data="adm:q:bk")
    builder.adjust(1)
    
    await _call_html(cq.message.edit_text, 
        " <b> </b>\n\n"
        "  :",
        reply_markup=builder.as_markup(),
    )
    await _safe_answer(cq)


@queue_router.message(
    StateFilter(QueueActionFSM.search_by_id),
    StaffRoleFilter(_ALLOWED_ROLES),
    F.text == "-",
)
async def queue_search_cancel(msg: Message, staff: StaffUser, state: FSMContext) -> None:
    """P1-9:  ."""
    await state.set_state(None)
    await _call_html(msg.answer, "  .")


@queue_router.message(
    StateFilter(QueueActionFSM.search_by_id),
    StaffRoleFilter(_ALLOWED_ROLES),
)
async def queue_search_by_id(msg: Message, staff: StaffUser, state: FSMContext) -> None:
    """P1-9:    ID."""
    text = (msg.text or "").strip()
    
    #  ID
    if not text.isdigit():
        await _call_html(msg.answer, 
            " ID    .\n"
            "     '-'  ."
        )
        return
    
    order_id = int(text)
    await state.set_state(None)
    
    #  
    orders_service = get_service(msg.bot, "orders_service")
    order = await _call_service(
        orders_service.get_card,
        order_id,
        city_ids=visible_city_ids_for(staff)
    )
    
    if not order:
        builder = InlineKeyboardBuilder()
        builder.button(text="  ", callback_data="adm:q:search")
        builder.button(text="  ", callback_data="adm:menu")
        builder.adjust(1)
        await _call_html(msg.answer, 
            f"  #{order_id}          .",
            reply_markup=builder.as_markup()
        )
        return
    
    #   ( )
    if staff.role is not StaffRole.GLOBAL_ADMIN and order.city_id not in staff.city_ids:
        builder = InlineKeyboardBuilder()
        builder.button(text="  ", callback_data="adm:q:search")
        builder.button(text="  ", callback_data="adm:menu")
        builder.adjust(1)
        await _call_html(msg.answer, 
            f"  #{order_id}   ,      .",
            reply_markup=builder.as_markup()
        )
        return
    
    #     
    history = await _call_service(
        orders_service.list_status_history,
        order_id,
        limit=ORDER_CARD_HISTORY_LIMIT,
        city_ids=visible_city_ids_for(staff)
    )
    
    show_guarantee = await _should_show_guarantee_button(
        order,
        orders_service,
        visible_city_ids_for(staff)
    )
    
    #  
    text_body = _format_order_card_text(order, history)
    markup = _order_card_markup(order, show_guarantee=show_guarantee)
    
    await _call_html(msg.answer, text_body, reply_markup=markup)
    
    # P1:  order_id     
    filters = await load_queue_filters(state)
    filters.order_id = order_id
    await save_queue_filters(state, filters)
    
    #   
    builder = InlineKeyboardBuilder()
    builder.button(text="  ", callback_data="adm:q:search")
    builder.button(text="   ", callback_data="adm:orders:queue:1")  # P1:  
    builder.button(text="  ", callback_data="adm:menu")
    builder.adjust(2, 1)
    await _call_html(msg.answer, 
        f"   #{order_id}\n\n"
        f"   .      .",
        reply_markup=builder.as_markup()
    )


@queue_router.callback_query(
    F.data == "adm:q:bk",
    StaffRoleFilter(_ALLOWED_ROLES),
)
async def cb_queue_back(cq: CallbackQuery, staff: StaffUser, state: FSMContext) -> None:
    await _call_html(cq.message.edit_text, " <b> </b>", reply_markup=_queue_menu_markup())
    await _safe_answer(cq)



# P1: Handler   order_id  
@queue_router.callback_query(
    F.data == "adm:q:flt:clear_id",
    StaffRoleFilter(_ALLOWED_ROLES),
)
async def cb_filters_clear_order_id(cq: CallbackQuery, staff: StaffUser, state: FSMContext) -> None:
    """P1:   order_id."""
    filters = await load_queue_filters(state)
    filters.order_id = None  #  order_id
    await save_queue_filters(state, filters)
    
    #   
    await _render_filters_by_ref(cq.message.bot, staff, state)
    await _safe_answer(cq, "   ID ")

# P1-11: HANDLERS   

@queue_router.callback_query(
    F.data == "adm:q:search:type:id",
    StaffRoleFilter(_ALLOWED_ROLES),
)
async def cb_queue_search_by_id_start(cq: CallbackQuery, staff: StaffUser, state: FSMContext) -> None:
    """P1-11:    ID ."""
    await state.set_state(QueueActionFSM.search_by_id)
    await _call_html(cq.message.edit_text, 
        " <b>   ID</b>\n\n"
        "   (, 12345)  '-'  .",
    )
    await _safe_answer(cq, " ID ")


@queue_router.callback_query(
    F.data == "adm:q:search:type:phone",
    StaffRoleFilter(_ALLOWED_ROLES),
)
async def cb_queue_search_by_phone_start(cq: CallbackQuery, staff: StaffUser, state: FSMContext) -> None:
    """P1-11:     ."""
    await state.set_state(QueueActionFSM.search_by_phone)
    await _call_html(cq.message.edit_text, 
        " <b>    </b>\n\n"
        "   (, +79991234567  9991234567)\n"
        " '-'  .",
    )
    await _safe_answer(cq, " ")


@queue_router.callback_query(
    F.data == "adm:q:search:type:master",
    StaffRoleFilter(_ALLOWED_ROLES),
)
async def cb_queue_search_by_master_start(cq: CallbackQuery, staff: StaffUser, state: FSMContext) -> None:
    """P1-11:    ."""
    await state.set_state(QueueActionFSM.search_by_master)
    await _call_html(cq.message.edit_text, 
        " <b>   </b>\n\n"
        " ID ,   \n"
        "(: 123, ,  +79991234567)\n\n"
        " '-'  .",
    )
    await _safe_answer(cq, "  ")


# P1-11:     
@queue_router.message(
    StateFilter(QueueActionFSM.search_by_phone, QueueActionFSM.search_by_master),
    StaffRoleFilter(_ALLOWED_ROLES),
    F.text == "-",
)
async def queue_search_cancel_all(msg: Message, staff: StaffUser, state: FSMContext) -> None:
    """P1-11:  ."""
    await state.set_state(None)
    await _call_html(msg.answer, "  .", reply_markup=_queue_menu_markup())


# P1-11:    
@queue_router.message(
    StateFilter(QueueActionFSM.search_by_phone),
    StaffRoleFilter(_ALLOWED_ROLES),
)
async def queue_search_by_phone(msg: Message, staff: StaffUser, state: FSMContext) -> None:
    """P1-11:     ."""
    text = (msg.text or "").strip()
    
    #   -    
    phone_digits = ''.join(c for c in text if c.isdigit())
    
    # 
    if len(phone_digits) < 10:
        await _call_html(msg.answer, 
            "     10 .\n"
            "     '-'  ."
        )
        return
    
    await state.set_state(None)
    
    #    
    from sqlalchemy import select, or_, func
    from field_service.db import models as m
    
    session_factory = msg.bot.get("session_factory")
    if not session_factory:
        await _call_html(msg.answer, "  .  .")
        return
    
    async with session_factory() as session:
        #    client_phone   
        #  LIKE   
        stmt = (
            select(
                m.orders.id,
                m.orders.client_phone,
                m.orders.client_name,
                m.orders.status,
                m.orders.created_at,
                m.cities.name.label("city_name"),
                m.districts.name.label("district_name"),
            )
            .join(m.cities, m.cities.id == m.orders.city_id)
            .outerjoin(m.districts, m.districts.id == m.orders.district_id)
            .where(
                or_(
                    m.orders.client_phone.like(f"%{phone_digits}%"),
                    m.orders.client_phone.like(f"%{phone_digits[-10:]}%"),  #  10 
                )
            )
            .order_by(m.orders.created_at.desc())
            .limit(20)  #  
        )
        
        #     
        city_ids = visible_city_ids_for(staff)
        if city_ids is not None:
            stmt = stmt.where(m.orders.city_id.in_(city_ids))
        
        result = await session.execute(stmt)
        orders = result.all()
    
    if not orders:
        builder = InlineKeyboardBuilder()
        builder.button(text="  ", callback_data="adm:q:search")
        builder.button(text="  ", callback_data="adm:menu")
        builder.adjust(1)
        await _call_html(msg.answer, 
            f"    '{text}'  .",
            reply_markup=builder.as_markup()
        )
        return
    
    #  
    lines = [f" <b> : {len(orders)}</b>\n"]
    for order in orders[:10]:  #   10
        status_emoji = "" if order.status == m.OrderStatus.ASSIGNED else ""
        lines.append(
            f"{status_emoji} #{order.id}  {order.city_name or '?'}"
            f"{f', {order.district_name}' if order.district_name else ''}\n"
            f"    {order.client_name or ''} ({order.client_phone or ''})\n"
            f"    {order.status.value if hasattr(order.status, 'value') else order.status}"
        )
    
    if len(orders) > 10:
        lines.append(f"\n...   {len(orders) - 10} ")
    
    text_response = "\n".join(lines)
    
    #   
    builder = InlineKeyboardBuilder()
    for order in orders[:5]:  #  5  
        builder.button(
            text=f"#{order.id}",
            callback_data=f"adm:q:card:{order.id}:1"
        )
    builder.adjust(5)  # 5   
    
    nav_builder = InlineKeyboardBuilder()
    nav_builder.button(text="  ", callback_data="adm:q:search")
    nav_builder.button(text="  ", callback_data="adm:menu")
    nav_builder.adjust(2)
    builder.attach(nav_builder)
    
    await _call_html(msg.answer, 
        text_response,
        reply_markup=builder.as_markup(),
    )


# P1-11:   
@queue_router.message(
    StateFilter(QueueActionFSM.search_by_master),
    StaffRoleFilter(_ALLOWED_ROLES),
)
async def queue_search_by_master(msg: Message, staff: StaffUser, state: FSMContext) -> None:
    """P1-11:     (ID,   )."""
    text = (msg.text or "").strip()
    
    if not text:
        await _call_html(msg.answer, "  ID,    .")
        return
    
    await state.set_state(None)
    
    from sqlalchemy import select, or_, func
    from field_service.db import models as m
    
    session_factory = msg.bot.get("session_factory")
    if not session_factory:
        await _call_html(msg.answer, "  .  .")
        return
    
    async with session_factory() as session:
        #     
        master_search_conditions = []
        
        #   ID (  )
        if text.isdigit():
            master_id = int(text)
            master_search_conditions.append(m.masters.id == master_id)
        
        #    (case-insensitive)
        master_search_conditions.append(
            or_(
                func.lower(m.masters.first_name).like(f"%{text.lower()}%"),
                func.lower(m.masters.last_name).like(f"%{text.lower()}%"),
            )
        )
        
        #   
        phone_digits = ''.join(c for c in text if c.isdigit())
        if len(phone_digits) >= 10:
            master_search_conditions.append(m.masters.phone.like(f"%{phone_digits}%"))
        
        #  
        masters_stmt = (
            select(m.masters.id, m.masters.first_name, m.masters.last_name, m.masters.phone)
            .where(or_(*master_search_conditions))
            .limit(10)
        )
        masters_result = await session.execute(masters_stmt)
        masters = masters_result.all()
        
        if not masters:
            builder = InlineKeyboardBuilder()
            builder.button(text="  ", callback_data="adm:q:search")
            builder.button(text="  ", callback_data="adm:menu")
            builder.adjust(1)
            await _call_html(msg.answer, 
                f"  '{text}'  .",
                reply_markup=builder.as_markup()
            )
            return
        
        #    1  -    
        if len(masters) > 1:
            lines = [f" <b> : {len(masters)}</b>\n"]
            builder = InlineKeyboardBuilder()
            for master in masters:
                full_name = f"{master.last_name} {master.first_name}"
                lines.append(f" #{master.id} {full_name} ({master.phone or ''})")
                builder.button(
                    text=f"#{master.id} {full_name[:15]}",
                    callback_data=f"adm:q:search:master:{master.id}"
                )
            builder.adjust(1)
            
            nav_builder = InlineKeyboardBuilder()
            nav_builder.button(text="  ", callback_data="adm:q:search")
            nav_builder.button(text="  ", callback_data="adm:menu")
            nav_builder.adjust(2)
            builder.attach(nav_builder)
            
            await _call_html(msg.answer, 
                "\n".join(lines) + "\n\n :",
                reply_markup=builder.as_markup(),
            )
            return
        
        #    1  -   
        master = masters[0]
        master_id = master.id
        
        #   
        orders_stmt = (
            select(
                m.orders.id,
                m.orders.client_phone,
                m.orders.client_name,
                m.orders.status,
                m.orders.created_at,
                m.cities.name.label("city_name"),
                m.districts.name.label("district_name"),
            )
            .join(m.cities, m.cities.id == m.orders.city_id)
            .outerjoin(m.districts, m.districts.id == m.orders.district_id)
            .where(m.orders.assigned_master_id == master_id)
            .order_by(m.orders.created_at.desc())
            .limit(20)
        )
        
        #   
        city_ids = visible_city_ids_for(staff)
        if city_ids is not None:
            orders_stmt = orders_stmt.where(m.orders.city_id.in_(city_ids))
        
        orders_result = await session.execute(orders_stmt)
        orders = orders_result.all()
    
    if not orders:
        full_name = f"{master.last_name} {master.first_name}"
        builder = InlineKeyboardBuilder()
        builder.button(text="  ", callback_data="adm:q:search")
        builder.button(text="  ", callback_data="adm:menu")
        builder.adjust(1)
        await _call_html(msg.answer, 
            f"   #{master_id} {full_name}  .",
            reply_markup=builder.as_markup()
        )
        return
    
    #  
    full_name = f"{master.last_name} {master.first_name}"
    lines = [f" <b>  #{master_id} {full_name}</b>"]
    lines.append(f": {len(orders)}\n")
    
    for order in orders[:10]:
        status_emoji = {
            m.OrderStatus.ASSIGNED: "",
            m.OrderStatus.EN_ROUTE: "",
            m.OrderStatus.WORKING: "",
            m.OrderStatus.PAYMENT: "",
            m.OrderStatus.CLOSED: "",
        }.get(order.status, "")
        
        lines.append(
            f"{status_emoji} #{order.id}  {order.city_name or '?'}"
            f"{f', {order.district_name}' if order.district_name else ''}\n"
            f"    {order.client_name or ''}\n"
            f"    {order.status.value if hasattr(order.status, 'value') else order.status}"
        )
    
    if len(orders) > 10:
        lines.append(f"\n...   {len(orders) - 10} ")
    
    text_response = "\n".join(lines)
    
    # 
    builder = InlineKeyboardBuilder()
    for order in orders[:5]:
        builder.button(
            text=f"#{order.id}",
            callback_data=f"adm:q:card:{order.id}:1"
        )
    builder.adjust(5)
    
    nav_builder = InlineKeyboardBuilder()
    nav_builder.button(text="  ", callback_data="adm:q:search")
    nav_builder.button(text="  ", callback_data="adm:menu")
    nav_builder.adjust(2)
    builder.attach(nav_builder)
    
    await _call_html(msg.answer, 
        text_response,
        reply_markup=builder.as_markup(),
    )


# P1-11: Callback     
@queue_router.callback_query(
    F.data.regexp(r"^adm:q:search:master:(\d+)$"),
    StaffRoleFilter(_ALLOWED_ROLES),
)
async def cb_queue_search_master_selected(cq: CallbackQuery, staff: StaffUser, state: FSMContext) -> None:
    """P1-11:     -   ."""
    try:
        master_id = int(cq.data.split(":")[-1])
    except (ValueError, IndexError):
        await _safe_answer(cq, "  ID ", show_alert=True)
        return
    
    from sqlalchemy import select
    from field_service.db import models as m
    
    session_factory = cq.message.bot.get("session_factory")
    if not session_factory:
        await _safe_answer(cq, "  ", show_alert=True)
        return
    
    async with session_factory() as session:
        #  
        master_stmt = select(m.masters).where(m.masters.id == master_id)
        master_result = await session.execute(master_stmt)
        master = master_result.scalar_one_or_none()
        
        if not master:
            await _safe_answer(cq, "   ", show_alert=True)
            return
        
        #   
        orders_stmt = (
            select(
                m.orders.id,
                m.orders.client_phone,
                m.orders.client_name,
                m.orders.status,
                m.orders.created_at,
                m.cities.name.label("city_name"),
                m.districts.name.label("district_name"),
            )
            .join(m.cities, m.cities.id == m.orders.city_id)
            .outerjoin(m.districts, m.districts.id == m.orders.district_id)
            .where(m.orders.assigned_master_id == master_id)
            .order_by(m.orders.created_at.desc())
            .limit(20)
        )
        
        city_ids = visible_city_ids_for(staff)
        if city_ids is not None:
            orders_stmt = orders_stmt.where(m.orders.city_id.in_(city_ids))
        
        orders_result = await session.execute(orders_stmt)
        orders = orders_result.all()
    
    if not orders:
        full_name = f"{master.last_name} {master.first_name}"
        builder = InlineKeyboardBuilder()
        builder.button(text="  ", callback_data="adm:q:search")
        builder.button(text="  ", callback_data="adm:menu")
        builder.adjust(1)
        await _call_html(cq.message.edit_text, 
            f"   #{master_id} {full_name}  .",
            reply_markup=builder.as_markup()
        )
        await _safe_answer(cq)
        return
    
    # 
    full_name = f"{master.last_name} {master.first_name}"
    lines = [f" <b>  #{master_id} {full_name}</b>"]
    lines.append(f": {len(orders)}\n")
    
    for order in orders[:10]:
        status_emoji = {
            m.OrderStatus.ASSIGNED: "",
            m.OrderStatus.EN_ROUTE: "",
            m.OrderStatus.WORKING: "",
            m.OrderStatus.PAYMENT: "",
            m.OrderStatus.CLOSED: "",
        }.get(order.status, "")
        
        lines.append(
            f"{status_emoji} #{order.id}  {order.city_name or '?'}"
            f"{f', {order.district_name}' if order.district_name else ''}\n"
            f"    {order.client_name or ''}\n"
            f"    {order.status.value if hasattr(order.status, 'value') else order.status}"
        )
    
    if len(orders) > 10:
        lines.append(f"\n...   {len(orders) - 10} ")
    
    # 
    builder = InlineKeyboardBuilder()
    for order in orders[:5]:
        builder.button(text=f"#{order.id}", callback_data=f"adm:q:card:{order.id}:1")
    builder.adjust(5)
    
    nav_builder = InlineKeyboardBuilder()
    nav_builder.button(text="  ", callback_data="adm:q:search")
    nav_builder.button(text="  ", callback_data="adm:menu")
    nav_builder.adjust(2)
    builder.attach(nav_builder)
    
    await _call_html(cq.message.edit_text, 
        "\n".join(lines),
        reply_markup=builder.as_markup(),
    )
    await _safe_answer(cq)
