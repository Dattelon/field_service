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


async def _safe_answer(cq: CallbackQuery, *args, **kwargs) -> None:
    try:
        await cq.answer(*args, **kwargs)
    except TelegramBadRequest:
        pass


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
    (OrderCategory.ELECTRICS, "Электрика"),
    (OrderCategory.PLUMBING, "Сантехника"),
    (OrderCategory.APPLIANCES, "Бытовая техника"),
    (OrderCategory.WINDOWS, "Окна и двери"),
    (OrderCategory.HANDYMAN, "Универсал на час"),
    (OrderCategory.ROADSIDE, "Автопомощь"),
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
    is_deferred = status == 'DEFERRED'  # ⚠️ Новый параметр
    return order_card_keyboard(
        order.id,
        attachments=order.attachments,
        allow_return=allow_return,
        allow_cancel=allow_cancel,
        show_guarantee=show_guarantee,
        is_deferred=is_deferred,
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
    filters: QueueFilters,
    orders_service,
    *,
    include_header: bool = True,
) -> str:
    lines: list[str] = []
    if include_header:
        lines.append("<b>🔧 Фильтры очереди</b>")
    
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
    
    lines.extend([
        f"🏙 Город: {city_text}",
        f"📂 Категория: {category_text}",
        f"📊 Статус: {status_text}",
        f"👷 Мастер: {master_text}",
        f"📅 Дата: {date_value}",
    ])
    return "\n".join(lines)


async def _edit_or_reply(message: Message, text: str, markup: InlineKeyboardMarkup, state: FSMContext) -> None:
    try:
        await message.edit_text(text, reply_markup=markup, parse_mode="HTML")
        await save_filters_message(state, message.chat.id, message.message_id)
    except TelegramBadRequest as exc:
        if exc.message == "Message is not modified":
            return
        sent = await message.answer(text, reply_markup=markup, parse_mode="HTML")
        await save_filters_message(state, sent.chat.id, sent.message_id)


async def _render_filters_menu(message: Message, staff: StaffUser, state: FSMContext) -> None:
    orders_service = get_service(message.bot, "orders_service")
    filters = await load_queue_filters(state)
    text = await _format_filters_text(staff, filters, orders_service)
    await _edit_or_reply(message, text, _filters_menu_keyboard(), state)


async def _render_filters_by_ref(bot, staff: StaffUser, state: FSMContext) -> None:
    msg_ref = await load_filters_message(state)
    if not msg_ref:
        return
    
    orders_service = get_service(bot, "orders_service")
    filters = await load_queue_filters(state)
    text = await _format_filters_text(staff, filters, orders_service)
    markup = _filters_menu_keyboard()
    
    try:
        await bot.edit_message_text(
            chat_id=msg_ref.chat_id,
            message_id=msg_ref.message_id,
            text=text,
            reply_markup=markup,
            parse_mode="HTML",
        )
    except TelegramBadRequest as exc:
        if exc.message != "Message is not modified":
            sent = await bot.send_message(
                msg_ref.chat_id,
                text,
                reply_markup=markup,
                parse_mode="HTML",
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
        "🏙 Выберите город:",
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
        items, has_next = await orders_service.list_queue(
            city_ids=city_filter,
            page=page,
            page_size=QUEUE_PAGE_SIZE,
            status_filter=filters.status,
            category=filters.category,
            master_id=filters.master_id,
            timeslot_date=timeslot_date,
        )

    filters_text = await _format_filters_text(
        staff, filters, orders_service, include_header=False
    )
    lines = ["<b>📦 Очередь заявок</b>", filters_text]
    if items:
        lines.append("")
        lines.extend(_format_order_line(item) for item in items)
    else:
        lines.append("")
        lines.append("💭 Список пуст")
    lines.append("")
    lines.append(f"📄 Страница: {page}")
    text = "\n".join(lines)

    markup = queue_list_keyboard(items, page=page, has_next=has_next)
    await _edit_or_reply(message, text, markup, state)





# P1-9: Функция для меню очереди
def _queue_menu_markup() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🔍 Поиск по ID", callback_data="adm:q:search")
    builder.button(text="🔧 Фильтры", callback_data="adm:q:flt")
    builder.button(text="📋 Открыть очередь", callback_data="adm:orders:queue:1")
    builder.button(text="🏠 В меню", callback_data="adm:menu")
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
        "\U0001f4e6 <b>\u0417\u0430\u044f\0432\043a\0438</b>\n\n"
        "\u0412\u044b\u0431\0435\0440\0438\0442\0435 \u0440\u0430\0437\0434\0435\043b \u0434\043b\044f \u043f\0440\043e\0441\043c\043e\0442\0440\0430 \u0437\0430\044f\0432\043e\043a."
    )

    markup = orders_menu(staff, counts)
    try:
        await cq.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    except TelegramBadRequest as exc:
        if exc.message != "Message is not modified":
            await cq.message.answer(text, reply_markup=markup, parse_mode="HTML")
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
        await _safe_answer(cq, "Неверная страница", show_alert=True)
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
        await _safe_answer(cq, "Неверная страница", show_alert=True)
        return

    orders_service = get_service(cq.message.bot, "orders_service")
    city_filter = visible_city_ids_for(staff)

    items, has_next = await orders_service.list_warranty_orders(
        city_ids=city_filter,
        page=page,
        page_size=QUEUE_PAGE_SIZE,
    )

    lines = ["<b>🛡 Заявки на гарантии</b>"]
    if items:
        lines.append("")
        lines.extend(_format_order_line(item) for item in items)
    else:
        lines.append("")
        lines.append("💭 Список пуст")
    lines.append("")
    lines.append(f"📄 Страница: {page}")

    text = "\n".join(lines)

    kb = InlineKeyboardBuilder()
    for order in items:
        kb.button(text=f"#{order.id}", callback_data=f"adm:q:card:{order.id}")
    if items:
        kb.adjust(1)

    nav = InlineKeyboardBuilder()
    nav_count = 0
    if page > 1:
        nav.button(text="◀️ Назад", callback_data=f"adm:orders:warranty:{page - 1}")
        nav_count += 1
    if has_next:
        nav.button(text="▶️ Далее", callback_data=f"adm:orders:warranty:{page + 1}")
        nav_count += 1
    if nav_count:
        nav.adjust(nav_count)
        kb.attach(nav)

    kb.button(text="⬅️ Назад", callback_data="adm:orders_menu")
    markup = kb.as_markup()

    try:
        await cq.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    except TelegramBadRequest as exc:
        if exc.message != "Message is not modified":
            await cq.message.answer(text, reply_markup=markup, parse_mode="HTML")

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
        await _safe_answer(cq, "Неверная страница", show_alert=True)
        return

    orders_service = get_service(cq.message.bot, "orders_service")
    city_filter = visible_city_ids_for(staff)

    items, has_next = await orders_service.list_closed_orders(
        city_ids=city_filter,
        page=page,
        page_size=QUEUE_PAGE_SIZE,
    )

    lines = ["<b>✅ Закрытые заявки</b>"]
    if items:
        lines.append("")
        lines.extend(_format_order_line(item) for item in items)
    else:
        lines.append("")
        lines.append("💭 Список пуст")
    lines.append("")
    lines.append(f"📄 Страница: {page}")

    text = "\n".join(lines)

    kb = InlineKeyboardBuilder()
    for order in items:
        kb.button(text=f"#{order.id}", callback_data=f"adm:q:card:{order.id}")
    if items:
        kb.adjust(1)

    nav = InlineKeyboardBuilder()
    nav_count = 0
    if page > 1:
        nav.button(text="◀️ Назад", callback_data=f"adm:orders:closed:{page - 1}")
        nav_count += 1
    if has_next:
        nav.button(text="▶️ Далее", callback_data=f"adm:orders:closed:{page + 1}")
        nav_count += 1
    if nav_count:
        nav.adjust(nav_count)
        kb.attach(nav)

    kb.button(text="⬅️ Назад", callback_data="adm:orders_menu")
    markup = kb.as_markup()

    try:
        await cq.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    except TelegramBadRequest as exc:
        if exc.message != "Message is not modified":
            await cq.message.answer(text, reply_markup=markup, parse_mode="HTML")

    await _safe_answer(cq)


@queue_router.callback_query(
    F.data == "adm:q",
    StaffRoleFilter(_ALLOWED_ROLES),
)
async def cb_queue_menu(cq: CallbackQuery, staff: StaffUser) -> None:
    await cq.message.edit_text("📦 <b>Очередь заказов</b>", reply_markup=_queue_menu_markup(), parse_mode="HTML")
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
            await _safe_answer(cq, "❌ Неверный ID города", show_alert=True)
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
        title="📂 Выберите категорию:",
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
            await _safe_answer(cq, "❌ Неверная категория", show_alert=True)
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
        title="📊 Выберите статус:",
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
            await _safe_answer(cq, "❌ Неверный статус", show_alert=True)
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
            await msg.answer("❌ ID мастера должен быть числом. Введите число или '-' для сброса.")
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
            await msg.answer("❌ Неверный формат даты. Используйте YYYY-MM-DD или '-' для сброса.")
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
    await _safe_answer(cq, "🔄 Фильтры сброшены")


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
    await _render_order_card(cq.message, order, history, show_guarantee=show_guarantee)
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
        f": {address_label}\n"
        "  ."
    )
    allow_auto = bool(order.district_id)
    markup = assign_menu_keyboard(order.id, allow_auto=allow_auto)
    try:
        await cq.message.edit_text(text, reply_markup=markup)
    except TelegramBadRequest as exc:
        if exc.message == 'Message is not modified':
            await _safe_answer(cq)
            return
        await cq.message.answer(text, reply_markup=markup)
    await _safe_answer(cq)








@queue_router.callback_query(
    F.data.startswith("adm:q:as:auto:"),
    StaffRoleFilter(_ALLOWED_ROLES),
)
async def cb_queue_assign_auto(cq: CallbackQuery, staff: StaffUser) -> None:
    parts = cq.data.split(":")
    try:
        order_id = int(parts[4])
    except (IndexError, ValueError):
        await _safe_answer(cq, "Неверный формат", show_alert=True)
        return

    orders_service = get_service(cq.message.bot, "orders_service")
    distribution_service = get_service(cq.message.bot, "distribution_service")
    order = await _call_service(orders_service.get_card, order_id, city_ids=visible_city_ids_for(staff))
    if not order:
        await _safe_answer(cq, "Заказ не найден", show_alert=True)
        return
    if staff.role is not StaffRole.GLOBAL_ADMIN and order.city_id not in staff.city_ids:
        await _safe_answer(cq, "Нет доступа к этому городу", show_alert=True)
        return

    # ⚠️ ПРОВЕРКА СТАТУСА DEFERRED
    if (order.status or "").upper() == "DEFERRED":
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        
        builder = InlineKeyboardBuilder()
        builder.button(text="✅ Да, запустить", callback_data=f"adm:q:as:auto:force:{order_id}")
        builder.button(text="❌ Отмена", callback_data=f"adm:q:card:{order_id}")
        builder.adjust(2)
        
        try:
            await cq.message.edit_text(
                f"⚠️ <b>Заказ #{order.id} в статусе ОТЛОЖЕН</b>\n\n"
                "Сейчас нерабочее время. Автораспределение может не найти мастеров.\n\n"
                "Запустить распределение сейчас?",
                reply_markup=builder.as_markup(),
                parse_mode="HTML",
            )
        except TelegramBadRequest:
            await cq.message.answer(
                f"⚠️ <b>Заказ #{order.id} в статусе ОТЛОЖЕН</b>\n\n"
                "Сейчас нерабочее время. Автораспределение может не найти мастеров.\n\n"
                "Запустить распределение сейчас?",
                reply_markup=builder.as_markup(),
                parse_mode="HTML",
            )
        await _safe_answer(cq)
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
        await _safe_answer(cq, " ", show_alert=False)
    else:
        alert_codes = {"no_district", "no_category", "forbidden", "not_found", "offer_conflict"}
        await _safe_answer(cq, result.message, show_alert=result.code in alert_codes)


@queue_router.callback_query(
    F.data.startswith("adm:q:as:auto:force:"),
    StaffRoleFilter(_ALLOWED_ROLES),
)
async def cb_queue_assign_auto_force(cq: CallbackQuery, staff: StaffUser) -> None:
    """Принудительное автораспределение для DEFERRED заказов."""
    parts = cq.data.split(":")
    try:
        order_id = int(parts[5])
    except (IndexError, ValueError):
        await _safe_answer(cq, "Неверный формат", show_alert=True)
        return

    orders_service = get_service(cq.message.bot, "orders_service")
    distribution_service = get_service(cq.message.bot, "distribution_service")
    order = await _call_service(orders_service.get_card, order_id, city_ids=visible_city_ids_for(staff))
    if not order:
        await _safe_answer(cq, "Заказ не найден", show_alert=True)
        return
    if staff.role is not StaffRole.GLOBAL_ADMIN and order.city_id not in staff.city_ids:
        await _safe_answer(cq, "Нет доступа к этому городу", show_alert=True)
        return

    ok, result = await distribution_service.assign_auto(order_id, staff.id)

    lines: list[str] = [f"Заказ #{order.id}"]
    lines.append("Автораспределение запущено." if ok else "Не удалось запустить распределение.")
    lines.append("")
    lines.append(result.message)
    if not ok and result.code == "no_candidates":
        lines.append("")
        lines.append("Нет доступных мастеров. Попробуйте назначить вручную.")

    text_body = "\n".join(lines)

    builder = InlineKeyboardBuilder()
    builder.button(text="Карточка заказа", callback_data=f"adm:q:card:{order_id}")
    builder.button(text="Назначение", callback_data=f"adm:q:as:{order_id}")
    builder.adjust(1)

    try:
        await cq.message.edit_text(text_body, reply_markup=builder.as_markup(), parse_mode="HTML")
    except TelegramBadRequest as exc:
        if exc.message != "Message is not modified":
            await cq.message.answer(text_body, reply_markup=builder.as_markup(), parse_mode="HTML")

    if ok:
        await _safe_answer(cq, "Распределение запущено", show_alert=False)
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
        await _safe_answer(cq, "Неверный формат", show_alert=True)
        return

    orders_service = get_service(cq.message.bot, "orders_service")
    order = await _call_service(orders_service.get_card, order_id, city_ids=visible_city_ids_for(staff))
    if not order:
        await _safe_answer(cq, "Заказ не найден", show_alert=True)
        return
    if staff.role is not StaffRole.GLOBAL_ADMIN and order.city_id not in staff.city_ids:
        await _safe_answer(cq, "Нет доступа к этому городу", show_alert=True)
        return

    # ⚠️ ПРЕДУПРЕЖДЕНИЕ ДЛЯ DEFERRED
    warning_prefix = ""
    if (order.status or "").upper() == "DEFERRED":
        warning_prefix = "⚠️ <b>Заказ сейчас ОТЛОЖЕН (нерабочее время)</b>\n\n"

    masters, has_next = await orders_service.manual_candidates(
        order_id,
        page=page,
        page_size=MANUAL_PAGE_SIZE,
        city_ids=visible_city_ids_for(staff),
    )
    text = warning_prefix + _manual_candidates_text(order, masters, page)
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
    await _safe_answer(cq, " ")




@queue_router.callback_query(
    F.data.startswith("adm:q:activate:"),
    StaffRoleFilter(_ALLOWED_ROLES),
)
async def cb_queue_activate_deferred(cq: CallbackQuery, staff: StaffUser) -> None:
    """Активировать DEFERRED заказ (перевести в PENDING)."""
    parts = cq.data.split(":")
    try:
        order_id = int(parts[3])
    except (IndexError, ValueError):
        await _safe_answer(cq, "Неверный формат", show_alert=True)
        return

    orders_service = get_service(cq.message.bot, "orders_service")
    order = await _call_service(orders_service.get_card, order_id, city_ids=visible_city_ids_for(staff))
    if not order:
        await _safe_answer(cq, "Заказ не найден", show_alert=True)
        return
    if staff.role is not StaffRole.GLOBAL_ADMIN and order.city_id not in staff.city_ids:
        await _safe_answer(cq, "Нет доступа к этому городу", show_alert=True)
        return

    # Переводим DEFERRED → PENDING
    ok = await orders_service.activate_deferred_order(order_id, staff.id)
    
    if not ok:
        await _safe_answer(cq, "Не удалось активировать заказ", show_alert=True)
        return
    
    # Обновляем карточку
    updated = await _call_service(orders_service.get_card, order_id, city_ids=visible_city_ids_for(staff))
    if not updated:
        await _safe_answer(cq, "Заказ не найден", show_alert=True)
        return
    
    history = await _call_service(
        orders_service.list_status_history,
        order_id,
        limit=ORDER_CARD_HISTORY_LIMIT,
        city_ids=visible_city_ids_for(staff)
    )
    
    show_guarantee = await _should_show_guarantee_button(updated, orders_service, visible_city_ids_for(staff))
    await _render_order_card(cq.message, updated, history, show_guarantee=show_guarantee)
    await _safe_answer(cq, "✅ Заказ переведён в активный поиск")


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

    await cq.message.answer(
        f"  #{new_order_id}     ."
    )
    await _safe_answer(cq)


@queue_router.callback_query(
    F.data.startswith("adm:q:ret:"),
    StaffRoleFilter(_ALLOWED_ROLES),
)
async def cb_queue_return(cq: CallbackQuery, staff: StaffUser) -> None:
    """P0-3: Показать диалог подтверждения возврата заказа в поиск."""
    parts = cq.data.split(":")
    try:
        order_id = int(parts[3])
    except (IndexError, ValueError):
        await _safe_answer(cq, "❌ Неверный ID заказа", show_alert=True)
        return
    
    orders_service = get_service(cq.message.bot, "orders_service")
    order = await _call_service(orders_service.get_card, order_id, city_ids=visible_city_ids_for(staff))
    if not order:
        await _safe_answer(cq, "❌ Заказ не найден", show_alert=True)
        return
    if staff.role is not StaffRole.GLOBAL_ADMIN and order.city_id not in staff.city_ids:
        await _safe_answer(cq, "❌ Нет доступа к этому городу", show_alert=True)
        return
    
    # Формируем информативное сообщение
    master_info = "не назначен"
    if order.master_name:
        master_info = f"<b>{html.escape(order.master_name)}</b>"
        if order.master_phone:
            master_info += f" ({html.escape(order.master_phone)})"
    elif order.master_id:
        master_info = f"мастер #{order.master_id}"
    
    address_parts = []
    if order.city_name:
        address_parts.append(order.city_name)
    if order.district_name:
        address_parts.append(order.district_name)
    address = ", ".join(address_parts) if address_parts else "—"
    
    text = (
        f"⚠️ <b>Вернуть заказ #{order_id} в поиск?</b>\n\n"
        f"📍 Адрес: {html.escape(address)}\n"
        f"👤 Текущий мастер: {master_info}\n"
        f"📊 Статус: {html.escape(order.status or '—')}\n\n"
        f"Заказ будет снят с мастера и отправлен на автораспределение."
    )
    
    markup = queue_return_confirm_keyboard(order_id)
    
    try:
        await cq.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    except TelegramBadRequest as exc:
        if exc.message != "Message is not modified":
            await cq.message.answer(text, reply_markup=markup, parse_mode="HTML")
    await _safe_answer(cq)


@queue_router.callback_query(
    F.data.startswith("adm:q:ret:confirm:"),
    StaffRoleFilter(_ALLOWED_ROLES),
)
async def cb_queue_return_confirm(cq: CallbackQuery, staff: StaffUser) -> None:
    """P0-3: Фактический возврат заказа в поиск после подтверждения."""
    parts = cq.data.split(":")
    try:
        order_id = int(parts[4])
    except (IndexError, ValueError):
        await _safe_answer(cq, "❌ Неверный ID заказа", show_alert=True)
        return
    
    orders_service = get_service(cq.message.bot, "orders_service")
    order = await _call_service(orders_service.get_card, order_id, city_ids=visible_city_ids_for(staff))
    if not order:
        await _safe_answer(cq, "❌ Заказ не найден", show_alert=True)
        return
    if staff.role is not StaffRole.GLOBAL_ADMIN and order.city_id not in staff.city_ids:
        await _safe_answer(cq, "❌ Нет доступа к этому городу", show_alert=True)
        return
    
    ok = await orders_service.return_to_search(order_id, staff.id)
    if not ok:
        await _safe_answer(cq, "❌ Не удалось вернуть заказ в поиск", show_alert=True)
        return
    
    updated = await _call_service(orders_service.get_card, order_id, city_ids=visible_city_ids_for(staff))
    if not updated:
        await _safe_answer(cq, "❌ Заказ не найден", show_alert=True)
        return
    
    history = await _call_service(
        orders_service.list_status_history,
        order_id,
        limit=ORDER_CARD_HISTORY_LIMIT,
        city_ids=visible_city_ids_for(staff)
    )
    show_guarantee = await _should_show_guarantee_button(updated, orders_service, visible_city_ids_for(staff))
    await _render_order_card(cq.message, updated, history, show_guarantee=show_guarantee)
    await _safe_answer(cq, "✅ Заказ возвращён в поиск")


@queue_router.callback_query(
    F.data.startswith("adm:q:cnl:"),
    StaffRoleFilter(_ALLOWED_ROLES),
)
async def cb_queue_cancel_start(cq: CallbackQuery, staff: StaffUser, state: FSMContext) -> None:
    parts = cq.data.split(":")
    try:
        order_id = int(parts[3])
    except (IndexError, ValueError):
        await _safe_answer(cq, "❌ Неверный ID заказа", show_alert=True)
        return
    
    orders_service = get_service(cq.message.bot, "orders_service")
    order = await _call_service(
        orders_service.get_card,
        order_id,
        city_ids=visible_city_ids_for(staff)
    )
    
    if not order:
        await _safe_answer(cq, "❌ Заказ не найден", show_alert=True)
        return
    
    if staff.role is not StaffRole.GLOBAL_ADMIN and order.city_id not in staff.city_ids:
        await _safe_answer(cq, "❌ Нет доступа к этому городу", show_alert=True)
        return
    
    await state.set_state(QueueActionFSM.cancel_reason)
    await save_cancel_state(state, order_id, cq.message.chat.id, cq.message.message_id)
    
    await cq.message.edit_text(
        f"📝 Введите причину отмены заказа #{order_id}\n\n"
        f"Минимум {CANCEL_REASON_MIN} символов (или пустое сообщение для пропуска).\n"
        f"Для отмены введите /cancel",
        reply_markup=queue_cancel_keyboard(order_id),
        parse_mode="HTML",
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
    
    await msg.answer("🔙 Отмена прервана.")
    
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
        await msg.bot.edit_message_text(
            chat_id=cancel_state.chat_id,
            message_id=cancel_state.message_id,
            text=text_body,
            reply_markup=markup,
            parse_mode="HTML",
        )
    except TelegramBadRequest as exc:
        if exc.message != "Message is not modified":
            await msg.bot.send_message(
                cancel_state.chat_id,
                text_body,
                reply_markup=markup,
                parse_mode="HTML",
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
        await msg.answer(
            f"❌ Причина отмены должна содержать минимум {CANCEL_REASON_MIN} символов "
            f"(максимум {CANCEL_REASON_MAX})."
        )
        return
    
    cancel_state = await load_cancel_state(state)
    
    if not cancel_state:
        await _clear_cancel_state(state)
        await msg.answer("❌ Ошибка: не найдено состояние отмены. Попробуйте снова.")
        return
    orders_service = get_service(msg.bot, "orders_service")
    order = await _call_service(
        orders_service.get_card,
        cancel_state.order_id,
        city_ids=visible_city_ids_for(staff)
    )
    
    if not order:
        await _clear_cancel_state(state)
        await msg.answer("❌ Заказ не найден.")
        return
    
    if staff.role is not StaffRole.GLOBAL_ADMIN and order.city_id not in staff.city_ids:
        await _clear_cancel_state(state)
        await msg.answer("❌ Нет доступа к этому городу.")
        return
    
    ok = await orders_service.cancel(
        cancel_state.order_id,
        reason=reason,
        by_staff_id=staff.id
    )
    
    if ok:
        await msg.answer(f"✅ Заказ #{cancel_state.order_id} отменён.")
    else:
        await msg.answer("❌ Не удалось отменить заказ.")
    
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
            await msg.bot.edit_message_text(
                chat_id=cancel_state.chat_id,
                message_id=cancel_state.message_id,
                text=text_body,
                reply_markup=markup,
                parse_mode="HTML",
            )
        except TelegramBadRequest as exc:
            if exc.message != "Message is not modified":
                await msg.bot.send_message(
                    cancel_state.chat_id,
                    text_body,
                    reply_markup=markup,
                    parse_mode="HTML",
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

# P1-9: ПОИСК ЗАКАЗА ПО ID
@queue_router.callback_query(
    F.data == "adm:q:search",
    StaffRoleFilter(_ALLOWED_ROLES),
)
async def cb_queue_search_start(cq: CallbackQuery, staff: StaffUser, state: FSMContext) -> None:
    """P1-9: Начать поиск заказа по ID."""
    await state.set_state(QueueActionFSM.search_by_id)
    await cq.message.answer(
        "📋 <b>Поиск заказа по ID</b>\n\n"
        "Введите номер заказа (например, 12345) или '-' для отмены.",
        parse_mode="HTML",
    )
    await _safe_answer(cq, "Введите ID заказа")


@queue_router.message(
    StateFilter(QueueActionFSM.search_by_id),
    StaffRoleFilter(_ALLOWED_ROLES),
    F.text == "-",
)
async def queue_search_cancel(msg: Message, staff: StaffUser, state: FSMContext) -> None:
    """P1-9: Отменить поиск."""
    await state.set_state(None)
    await msg.answer("🔙 Поиск отменён.")


@queue_router.message(
    StateFilter(QueueActionFSM.search_by_id),
    StaffRoleFilter(_ALLOWED_ROLES),
)
async def queue_search_by_id(msg: Message, staff: StaffUser, state: FSMContext) -> None:
    """P1-9: Поиск заказа по ID."""
    text = (msg.text or "").strip()
    
    # Валидация ID
    if not text.isdigit():
        await msg.answer(
            "⚠️ ID заказа должен быть числом.\n"
            "Попробуйте ещё раз или введите '-' для отмены."
        )
        return
    
    order_id = int(text)
    await state.set_state(None)
    
    # Загрузить заказ
    orders_service = get_service(msg.bot, "orders_service")
    order = await _call_service(
        orders_service.get_card,
        order_id,
        city_ids=visible_city_ids_for(staff)
    )
    
    if not order:
        builder = InlineKeyboardBuilder()
        builder.button(text="🔍 Искать другой", callback_data="adm:q:search")
        builder.button(text="🏠 В меню", callback_data="adm:menu")
        builder.adjust(1)
        await msg.answer(
            f"❌ Заказ #{order_id} не найден или у вас нет доступа к этому городу.",
            reply_markup=builder.as_markup()
        )
        return
    
    # Проверить доступ (дополнительная проверка)
    if staff.role is not StaffRole.GLOBAL_ADMIN and order.city_id not in staff.city_ids:
        builder = InlineKeyboardBuilder()
        builder.button(text="🔍 Искать другой", callback_data="adm:q:search")
        builder.button(text="🏠 В меню", callback_data="adm:menu")
        builder.adjust(1)
        await msg.answer(
            f"❌ Заказ #{order_id} находится в городе, к которому у вас нет доступа.",
            reply_markup=builder.as_markup()
        )
        return
    
    # Загрузить историю и отобразить карточку
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
    
    # Отправить карточку
    text_body = _format_order_card_text(order, history)
    markup = _order_card_markup(order, show_guarantee=show_guarantee)
    
    await msg.answer(text_body, reply_markup=markup, parse_mode="HTML")
    
    # Подтверждение
    builder = InlineKeyboardBuilder()
    builder.button(text="🔍 Искать другой", callback_data="adm:q:search")
    builder.adjust(1)
    await msg.answer(
        f"✅ Найден заказ #{order_id}",
        reply_markup=builder.as_markup()
    )


@queue_router.callback_query(
    F.data == "adm:q:bk",
    StaffRoleFilter(_ALLOWED_ROLES),
)
async def cb_queue_back(cq: CallbackQuery, staff: StaffUser, state: FSMContext) -> None:
    await cq.message.edit_text("📦 <b>Очередь заказов</b>", reply_markup=_queue_menu_markup(), parse_mode="HTML")
    await _safe_answer(cq)
