from __future__ import annotations

from datetime import datetime
from typing import Iterable, Optional

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from field_service.db.models import OrderStatus

from .dto import CityRef, StaffRole, StaffUser
from .filters import StaffRoleFilter
from .keyboards import main_menu
from .states import QueueFiltersFSM
from .utils import get_service

queue_router = Router(name="admin_queue")

_ALLOWED_ROLES = {StaffRole.GLOBAL_ADMIN, StaffRole.CITY_ADMIN, StaffRole.LOGIST}

CATEGORY_CHOICES: tuple[tuple[str, str], ...] = (
    ("ELECTRICS", "Электрика"),
    ("PLUMBING", "Сантехника"),
    ("APPLIANCES", "Бытовая техника"),
    ("WINDOWS", "Окна"),
    ("HANDYMAN", "Универсал"),
    ("ROADSIDE", "Автопомощь"),
)
CATEGORY_LABELS = {code: label for code, label in CATEGORY_CHOICES}
STATUS_CHOICES = tuple((status.value, status.value) for status in OrderStatus)
FILTER_DATA_KEY = "queue_filters"
FILTER_MSG_CHAT_KEY = "queue_filters_chat_id"
FILTER_MSG_ID_KEY = "queue_filters_message_id"
_MAX_CITIES = 120


def _default_filters() -> dict[str, Optional[str | int]]:
    return {
        "city_id": None,
        "category": None,
        "status": None,
        "master_id": None,
        "date": None,
    }


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
    builder.button(text="Город", callback_data="adm:q:flt:city")
    builder.button(text="Категория", callback_data="adm:q:flt:cat")
    builder.button(text="Статус", callback_data="adm:q:flt:status")
    builder.button(text="Мастер", callback_data="adm:q:flt:master")
    builder.button(text="Дата", callback_data="adm:q:flt:date")
    builder.button(text="Применить", callback_data="adm:q:flt:apply")
    builder.button(text="Сброс", callback_data="adm:q:flt:reset")
    builder.button(text="Назад", callback_data="adm:q")
    builder.adjust(2, 2, 2, 2)
    return builder.as_markup()


def _city_keyboard(cities: Iterable[CityRef], selected_id: Optional[int]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for city in cities:
        title = city.name
        if selected_id == city.id:
            title = f"• {title}"
        builder.button(text=title, callback_data=f"adm:q:flt:c:{city.id}")
    builder.button(text="Без города", callback_data="adm:q:flt:c:0")
    builder.button(text="Назад", callback_data="adm:q:flt")
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
            text = f"• {label}"
        builder.button(text=text, callback_data=f"{prefix}:{value}")
    builder.button(text="Без значения", callback_data=f"{prefix}:{clear_suffix}")
    builder.button(text="Назад", callback_data="adm:q:flt")
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
        lines.append("<b>Фильтры очереди</b>")
    city_text = "—"
    city_id = filters.get("city_id")
    if city_id:
        city = await orders_service.get_city(int(city_id))
        city_text = city.name if city else f"#{city_id}"
    category_code = filters.get("category")
    category_text = CATEGORY_LABELS.get(category_code, "—") if category_code else "—"
    status_code = filters.get("status")
    status_text = status_code or "—"
    master_id = filters.get("master_id")
    master_text = f"#{master_id}" if master_id else "—"
    date_value = filters.get("date") or "—"
    lines.extend(
        [
            f"Город: {city_text}",
            f"Категория: {category_text}",
            f"Статус: {status_text}",
            f"Мастер: {master_text}",
            f"Дата: {date_value}",
        ]
    )
    return "
".join(lines)


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
    await _edit_or_reply(message, "Выберите город", _city_keyboard(cities, filters.get("city_id")), state)


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
    orders_service = get_service(message.bot, "orders_service")
    filters = await _load_filters(state)
    filters_text = await _format_filters_text(staff, filters, orders_service, include_header=False)
    builder = InlineKeyboardBuilder()
    builder.button(text="Назад", callback_data="adm:q:flt")
    builder.adjust(1)
    text = f"<b>Список (WIP)</b>
{filters_text}
Страница: {page}"
    await _edit_or_reply(message, text, builder.as_markup(), state)


@queue_router.callback_query(
    F.data == "adm:q",
    StaffRoleFilter(_ALLOWED_ROLES),
)
async def cb_queue_menu(cq: CallbackQuery, staff: StaffUser) -> None:
    builder = InlineKeyboardBuilder()
    builder.button(text="Фильтры", callback_data="adm:q:flt")
    builder.button(text="Список", callback_data="adm:q:list:1")
    builder.button(text="Назад", callback_data="adm:menu")
    builder.adjust(1)
    await cq.message.edit_text("Раздел очереди", reply_markup=builder.as_markup())
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
            await cq.answer("Некорректный город", show_alert=True)
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
        entries=CATEGORY_CHOICES,
        prefix="adm:q:flt:cat",
        selected=filters.get("category"),
        state=state,
        title="Выберите категорию",
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
        title="Выберите статус",
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
        filters["status"] = value
    await _save_filters(state, filters)
    await _render_filters_menu(cq.message, staff, state)
    await cq.answer()


@queue_router.callback_query(
    F.data == "adm:q:flt:master",
    StaffRoleFilter(_ALLOWED_ROLES),
)
async def cb_queue_filters_master(cq: CallbackQuery, staff: StaffUser, state: FSMContext) -> None:
    await state.set_state(QueueFiltersFSM.master)
    await cq.answer("Введите ID мастера сообщением", show_alert=True)


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
            await msg.answer("ID мастера должен быть целым числом или '-' для сброса.")
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
    await cq.answer("Введите дату YYYY-MM-DD или '-' для сброса", show_alert=True)


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
            await msg.answer("Дата должна быть в формате YYYY-MM-DD или '-' для сброса.")
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
    await cq.answer("Фильтры сброшены")


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
        await cq.answer("Некорректная страница", show_alert=True)
        return
    await _render_queue_list(cq.message, staff, state, page=page)
    await cq.answer()


@queue_router.callback_query(
    F.data.startswith("adm:q:card:"),
    StaffRoleFilter(_ALLOWED_ROLES),
)
async def cb_queue_card(cq: CallbackQuery, staff: StaffUser, state: FSMContext) -> None:
    try:
        order_id = int(cq.data.split(":")[3])
    except (IndexError, ValueError):
        await cq.answer("Некорректная заявка", show_alert=True)
        return
    await _render_filters_menu(cq.message, staff, state)
    await cq.answer(f"Карточка (WIP), id={order_id}", show_alert=True)


@queue_router.callback_query(
    F.data == "adm:q:bk",
    StaffRoleFilter(_ALLOWED_ROLES),
)
async def cb_queue_back(cq: CallbackQuery, staff: StaffUser, state: FSMContext) -> None:
    builder = InlineKeyboardBuilder()
    builder.button(text="Фильтры", callback_data="adm:q:flt")
    builder.button(text="Список", callback_data="adm:q:list:1")
    builder.button(text="Назад", callback_data="adm:menu")
    builder.adjust(1)
    await cq.message.edit_text("Раздел очереди", reply_markup=builder.as_markup())
    await cq.answer()

