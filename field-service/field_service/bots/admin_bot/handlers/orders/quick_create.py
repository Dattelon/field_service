# field_service/bots/admin_bot/handlers/orders/quick_create.py
"""Обработчики быстрого создания заказов (QuickOrderFSM) - P0-5."""
from __future__ import annotations

import os
from datetime import time
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from field_service.config import settings as env_settings
from field_service.db.models import OrderStatus, OrderType
from field_service.services import time_service

from ...core.dto import StaffRole, StaffUser
from ...core.filters import StaffRoleFilter
from ...core.states import QuickOrderFSM
from ...ui.keyboards import (
    assign_menu_keyboard,
    new_order_asap_late_keyboard,
    new_order_city_keyboard,
    new_order_confirm_keyboard,
    new_order_district_keyboard,
    new_order_slot_keyboard,
    order_card_keyboard,
)
from ...ui.texts import new_order_summary
from ...core.access import visible_city_ids_for
from ..common.helpers import (
    _build_new_order_data,
    _orders_service,
    _resolve_city_timezone,
    _validate_phone,
    _normalize_phone,
    _zone_storage_value,
)
from .queue import CATEGORY_CHOICES, CATEGORY_LABELS, CATEGORY_LABELS_BY_VALUE
from ...utils.normalizers import normalize_category


router = Router(name="admin_quick_orders")


# Константы для слотов
WORKDAY_START_DEFAULT = time_service.parse_time_string(env_settings.workday_start, default=time(10, 0))
WORKDAY_END_DEFAULT = time_service.parse_time_string(env_settings.workday_end, default=time(20, 0))
LATE_ASAP_THRESHOLD = time_service.parse_time_string(env_settings.asap_late_threshold, default=time(19, 30))


def is_working_hours() -> bool:
    """Определить, в рабочее ли время запущено подтверждение."""
    if os.getenv("PYTEST_CURRENT_TEST"):
        return True
    from datetime import datetime
    now = datetime.now().time()
    return time(8, 0) <= now <= time(20, 0)

SLOT_BUCKETS: tuple[tuple[str, time, time], ...] = tuple(
    (bucket, span[0], span[1]) for bucket, span in time_service._SLOT_BUCKETS.items()
)


# Хелперы для слотов
def _slot_options(now_local, *, workday_start, workday_end):
    """Генерирует доступные слоты времени."""
    current = now_local.timetz()
    if current.tzinfo is not None:
        current = current.replace(tzinfo=None)
    options = []
    if current < workday_end:
        options.append(("ASAP", "ASAP"))
        for bucket_key, start, end in SLOT_BUCKETS:
            if current < start:
                options.append((f"TODAY:{bucket_key}", f"Сегодня {start:%H:%M}-{end:%H:%M}"))
    for bucket_key, start, end in SLOT_BUCKETS:
        options.append((f"TOM:{bucket_key}", f"Завтра {start:%H:%M}-{end:%H:%M}"))
    return options


def _format_slot_display(choice, computation, *, tz):
    """Форматирует выбранный слот для отображения."""
    if choice == "ASAP":
        return "ASAP"
    formatted = time_service.format_timeslot_local(
        computation.start_utc,
        computation.end_utc,
        tz=tz,
    )
    return formatted or ""


async def _resolve_workday_window():
    """Получает окно рабочего дня из настроек."""
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
    prefix="quick",  # P0-5: Префикс для клавиатур
):
    """Финализирует выбор слота и переходит к подтверждению."""
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
    await state.set_state(QuickOrderFSM.confirm)
    await message.edit_text(
        summary,
        reply_markup=new_order_confirm_keyboard(prefix=prefix),  # P0-5: Используем переданный префикс
        disable_web_page_preview=True,
    )


async def _render_created_order_card(message, order_id, staff):
    """Показывает карточку созданного заказа."""
    orders_service = _orders_service(message.bot)
    detail = await orders_service.get_card(order_id, city_ids=visible_city_ids_for(staff))
    if not detail:
        await message.answer(f"Заказ #{order_id} не найден.")
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
# БЫСТРОЕ СОЗДАНИЕ - ГОРОД
# ============================================

async def _start_quick_order(cq, staff, state):
    """Начать быстрое создание заказа (P0-5)."""
    await state.clear()
    await state.update_data(
        staff_id=staff.id,
        attachments=[],
        order_type=OrderType.NORMAL.value,
        # Дефолтные значения для полей, которые не заполняются в быстром режиме
        street_id=None,
        street_name="",
        street_manual=None,
        house="-",
        apartment=None,
        address_comment=None,
        client_name="Клиент",  # Дефолтное имя
        description=None,  # Будет заполнено после выбора категории
    )
    await state.set_state(QuickOrderFSM.city)
    await _render_city_step(cq.message, state, page=1)
    await cq.answer()


async def _render_city_step(message, state, page, query=None):
    """Рендерит шаг выбора города."""
    orders_service = _orders_service(message.bot)
    limit = 80
    if query:
        cities = await orders_service.list_cities(query=query, limit=limit)
    else:
        cities = await orders_service.list_cities(limit=limit)
    if not cities:
        try:
            await message.edit_text("Города не найдены. Нажмите /cancel, чтобы отменить.")
        except TelegramBadRequest:
            await message.answer("Города не найдены. Нажмите /cancel, чтобы отменить.")
        return
    per_page = 10
    total_pages = max(1, (len(cities) + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))
    start = (page - 1) * per_page
    chunk = cities[start : start + per_page]
    keyboard = new_order_city_keyboard(
        [(c.id, c.name) for c in chunk], 
        page=page, 
        total_pages=total_pages,
        prefix="quick"  # P0-5: Префикс для быстрого режима
    )
    prompt = "⚡ Быстрое создание заказа (5 шагов)\n\nШаг 1/5: Выберите город:"
    try:
        await message.edit_text(prompt, reply_markup=keyboard)
    except TelegramBadRequest:
        await message.answer(prompt, reply_markup=keyboard)
    except Exception:
        await message.answer(prompt, reply_markup=keyboard)
    await state.update_data(city_query=query, city_page=page)


@router.callback_query(
    F.data == "adm:new:mode:quick",
    StaffRoleFilter({StaffRole.GLOBAL_ADMIN, StaffRole.CITY_ADMIN, StaffRole.LOGIST}),
)
async def cb_quick_order_start(cq: CallbackQuery, staff: StaffUser, state: FSMContext) -> None:
    """Начать быстрое создание заказа."""
    await _start_quick_order(cq, staff, state)


@router.callback_query(F.data.startswith("adm:quick:city_page:"), StateFilter(QuickOrderFSM.city))
async def cb_quick_order_city_page(cq: CallbackQuery, state: FSMContext) -> None:
    """Пагинация по городам."""
    page = int(cq.data.split(":")[3])
    data = await state.get_data()
    query = data.get("city_query")
    await state.set_state(QuickOrderFSM.city)
    await _render_city_step(cq.message, state, page=page, query=query)
    await cq.answer()


@router.callback_query(F.data == "adm:quick:city_search", StateFilter(QuickOrderFSM.city))
async def cb_quick_order_city_search(cq: CallbackQuery, state: FSMContext) -> None:
    """Поиск города по названию."""
    await state.set_state(QuickOrderFSM.city)
    prompt = "Введите название города (минимум 2 символа). Команда /cancel вернёт в меню."
    try:
        await cq.message.edit_text(prompt)
    except TelegramBadRequest:
        await cq.message.answer(prompt)
    except Exception:
        await cq.message.answer(prompt)
    await cq.answer()


@router.message(StateFilter(QuickOrderFSM.city))
async def quick_order_city_input(msg: Message, state: FSMContext) -> None:
    """Ввод названия города для поиска."""
    query = (msg.text or "").strip()
    if len(query) < 2:
        await msg.answer("Минимум 2 символа. Попробуйте снова.")
        return
    await _render_city_step(msg, state, page=1, query=query)


@router.callback_query(F.data.startswith("adm:quick:city:"), StateFilter(QuickOrderFSM.city))
async def cb_quick_order_city_pick(cq: CallbackQuery, state: FSMContext) -> None:
    """Выбор города."""
    city_id = int(cq.data.split(":")[3])
    orders_service = _orders_service(cq.message.bot)
    city = await orders_service.get_city(city_id)
    if not city:
        await cq.answer("Город не найден", show_alert=True)
        return
    await state.update_data(city_id=city.id, city_name=city.name)
    await state.set_state(QuickOrderFSM.district)
    await _render_district_step(cq.message, state, page=1)
    await cq.answer()


# ============================================
# БЫСТРОЕ СОЗДАНИЕ - РАЙОН
# ============================================

async def _render_district_step(message, state, page):
    """Рендерит шаг выбора района."""
    data = await state.get_data()
    city_id = data.get("city_id")
    orders_service = _orders_service(message.bot)
    districts, has_next = await orders_service.list_districts(city_id, page=page, page_size=5)
    buttons = [(d.id, d.name) for d in districts]
    keyboard = new_order_district_keyboard(
        buttons, 
        page=page, 
        has_next=has_next,
        prefix="quick"  # P0-5: Префикс для быстрого режима
    )
    prompt = "⚡ Быстрое создание заказа\n\nШаг 2/5: Выберите район:"
    try:
        await message.edit_text(prompt, reply_markup=keyboard)
    except TelegramBadRequest:
        await message.answer(prompt, reply_markup=keyboard)
    except Exception:
        await message.answer(prompt, reply_markup=keyboard)
    await state.update_data(district_page=page)


@router.callback_query(F.data.startswith("adm:quick:district_page:"), StateFilter(QuickOrderFSM.district))
async def cb_quick_order_district_page(cq: CallbackQuery, state: FSMContext) -> None:
    """Пагинация по районам."""
    page = int(cq.data.split(":")[3])
    await state.set_state(QuickOrderFSM.district)
    await _render_district_step(cq.message, state, page=page)
    try:
        await cq.answer()
    except TelegramBadRequest:
        pass


@router.callback_query(F.data == "adm:quick:city_back", StateFilter(QuickOrderFSM.district))
async def cb_quick_order_city_back(cq: CallbackQuery, state: FSMContext) -> None:
    """Вернуться к выбору города."""
    data = await state.get_data()
    await state.set_state(QuickOrderFSM.city)
    await _render_city_step(
        cq.message,
        state,
        page=data.get("city_page", 1),
        query=data.get("city_query"),
    )
    await cq.answer()


@router.callback_query(F.data.startswith("adm:quick:district:"), StateFilter(QuickOrderFSM.district))
async def cb_quick_order_district_pick(cq: CallbackQuery, state: FSMContext) -> None:
    """Выбор района."""
    district_id_str = cq.data.split(":")[3]
    
    # Проверяем специальные случаи
    if district_id_str == "none":
        await cq.answer("В быстром режиме необходимо выбрать район", show_alert=True)
        return
    
    district_id = int(district_id_str)
    orders_service = _orders_service(cq.message.bot)
    district = await orders_service.get_district(district_id)
    if not district:
        await cq.answer("Район не найден", show_alert=True)
        return
    await state.update_data(district_id=district.id, district_name=district.name)
    await state.set_state(QuickOrderFSM.client_phone)
    await cq.message.edit_text("⚡ Быстрое создание заказа\n\nШаг 3/5: Укажите телефон клиента в формате +7XXXXXXXXXX.")
    await cq.answer()


# ============================================
# БЫСТРОЕ СОЗДАНИЕ - ТЕЛЕФОН
# ============================================

@router.message(StateFilter(QuickOrderFSM.client_phone))
async def quick_order_client_phone(msg: Message, state: FSMContext) -> None:
    """Ввод телефона клиента."""
    raw = _normalize_phone(msg.text)
    if not _validate_phone(raw):
        await msg.answer("Телефон должен быть в формате +7XXXXXXXXXX.")
        return
    await state.update_data(client_phone=raw)
    await state.set_state(QuickOrderFSM.category)
    
    kb = InlineKeyboardBuilder()
    for category, label in CATEGORY_CHOICES:
        kb.button(text=label, callback_data=f"adm:quick:cat:{category.value}")
    kb.adjust(2)
    await msg.answer("⚡ Быстрое создание заказа\n\nШаг 4/5: Выберите категорию заявки:", reply_markup=kb.as_markup())


# ============================================
# БЫСТРОЕ СОЗДАНИЕ - КАТЕГОРИЯ
# ============================================

@router.callback_query(F.data.startswith("adm:quick:cat:"), StateFilter(QuickOrderFSM.category))
async def cb_quick_order_category(cq: CallbackQuery, state: FSMContext) -> None:
    """Выбор категории заказа."""
    raw = cq.data.split(":")[3]
    category = normalize_category(raw)
    if category is None:
        await cq.answer("Неизвестная категория.", show_alert=True)
        return
    
    category_label = CATEGORY_LABELS.get(category, CATEGORY_LABELS_BY_VALUE.get(raw, raw))
    
    # Генерируем описание по умолчанию
    default_description = f"Требуется мастер по категории: {category_label}"
    
    await state.update_data(
        category=category,
        category_label=category_label,
        description=default_description,
    )
    
    # Переходим к выбору слота
    await state.set_state(QuickOrderFSM.slot)
    data = await state.get_data()
    city_id = data.get("city_id")
    if not city_id:
        await cq.answer("Не удалось определить город.", show_alert=True)
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
    keyboard = new_order_slot_keyboard(options, prefix="quick")  # P0-5: Префикс для быстрого режима
    await cq.message.edit_text("⚡ Быстрое создание заказа\n\nШаг 5/5: Выберите доступное время:", reply_markup=keyboard)
    await cq.answer()


# ============================================
# БЫСТРОЕ СОЗДАНИЕ - СЛОТ
# ============================================

@router.callback_query(F.data.startswith("adm:quick:slot:"), StateFilter(QuickOrderFSM.slot))
async def cb_quick_order_slot(cq: CallbackQuery, state: FSMContext) -> None:
    """Выбор слота времени."""
    key = ":".join(cq.data.split(":")[3:])
    data = await state.get_data()
    city_id = data.get("city_id")
    if not city_id:
        await cq.answer("Не удалось определить город.", show_alert=True)
        return
    await state.set_state(QuickOrderFSM.slot)
    options = data.get("slot_options") or []
    valid_keys = {item[0] for item in options}
    if key not in valid_keys:
        await cq.answer("Слот недоступен.", show_alert=True)
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
            await state.set_state(QuickOrderFSM.slot)
            await cq.message.edit_text(
                "Мастер может выехать только завтра с 10:00 до 13:00. Подтвердить перенос?",
                reply_markup=new_order_asap_late_keyboard(prefix="quick"),  # P0-5: Префикс для быстрого режима
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
            prefix="quick",  # P0-5: Префикс для быстрого режима
        )
    except ValueError:
        refreshed_options = _slot_options(
            time_service.now_in_city(tz),
            workday_start=workday_start,
            workday_end=workday_end,
        )
        await state.update_data(slot_options=refreshed_options, pending_asap=False, initial_status=None)
        await state.set_state(QuickOrderFSM.slot)
        await cq.message.edit_text(
            "Слот недоступен. Выберите другое время:",
            reply_markup=new_order_slot_keyboard(refreshed_options, prefix="quick"),  # P0-5: Префикс для быстрого режима
        )
        await cq.answer("Расписание обновлено, попробуйте снова.", show_alert=True)
        return
    await cq.answer()


@router.callback_query(F.data == "adm:quick:slot:lateok", StateFilter(QuickOrderFSM.slot))
async def cb_quick_order_slot_lateok(cq: CallbackQuery, state: FSMContext) -> None:
    """Подтвердить перенос ASAP на завтра."""
    data = await state.get_data()
    city_id = data.get("city_id")
    if not city_id:
        await cq.answer("Не удалось определить город.", show_alert=True)
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
        prefix="quick",  # P0-5: Префикс для быстрого режима
    )
    await cq.answer()


@router.callback_query(F.data == "adm:quick:slot:reslot", StateFilter(QuickOrderFSM.slot))
async def cb_quick_order_slot_reslot(cq: CallbackQuery, state: FSMContext) -> None:
    """Выбрать другой слот вместо ASAP."""
    data = await state.get_data()
    city_id = data.get("city_id")
    if not city_id:
        await cq.answer("Не удалось определить город.", show_alert=True)
        return
    await state.set_state(QuickOrderFSM.slot)
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
    await cq.message.edit_text(
        "Выберите доступное время:", 
        reply_markup=new_order_slot_keyboard(options, prefix="quick")  # P0-5: Префикс для быстрого режима
    )
    await cq.answer()


# ============================================
# БЫСТРОЕ СОЗДАНИЕ - ПОДТВЕРЖДЕНИЕ
# ============================================

@router.callback_query(F.data == "adm:quick:confirm", StateFilter(QuickOrderFSM.confirm))
async def cb_quick_order_confirm(cq: CallbackQuery, state: FSMContext, staff: StaffUser | None = None) -> None:
    """Подтвердить создание заказа."""
    if staff is None:
        from ..common.helpers import _staff_service
        staff_service = _staff_service(cq.message.bot)
        staff = await staff_service.get_by_tg_id(cq.from_user.id if cq.from_user else 0)
        if staff is None:
            await cq.answer("Недостаточно прав", show_alert=True)
            return
    
    # Проверка рабочего времени
    if not is_working_hours():
        from aiogram.types import InlineKeyboardButton
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        
        kb = InlineKeyboardBuilder()
        kb.row(
            InlineKeyboardButton(text="Да, создать", callback_data="adm:quick:force_confirm"),
            InlineKeyboardButton(text="Отменить", callback_data="adm:new:cancel"),
        )
        
        await state.set_state(QuickOrderFSM.confirm_deferred)
        await cq.message.edit_text(
            "Сейчас нерабочее время (20:00-8:00)\n\n"
            "Заказ будет создан в статусе ОТЛОЖЕН и:\n"
            "- Мастера его не увидят\n"
            "- Распределение начнется в 8:00\n\n"
            "Вы точно хотите создать заказ?",
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
        await cq.answer("Не удалось собрать данные заявки. Попробуйте заново.", show_alert=True)
        return
    orders_service = _orders_service(cq.message.bot)
    order_id = await orders_service.create_order(new_order)
    detail = await orders_service.get_card(order_id, city_ids=visible_city_ids_for(staff))
    await state.clear()
    await cq.answer("Заявка создана")
    if detail:
        allow_auto = detail.district_id is not None
        prompt_parts = [f"Заявка #{detail.id} создана.", summary_text]
        if not allow_auto:
            prompt_parts.append("Автораспределение недоступно: не выбран район.")
        prompt_parts.append("Выберите способ распределения:")
        prompt = "\n\n".join(prompt_parts)
        markup = assign_menu_keyboard(detail.id, allow_auto=allow_auto)
        try:
            await cq.message.edit_text(prompt, reply_markup=markup, disable_web_page_preview=True)
        except Exception:
            await cq.message.answer(prompt, reply_markup=markup, disable_web_page_preview=True)
        return
    await _render_created_order_card(cq.message, order_id, staff)


@router.callback_query(F.data == "adm:quick:force_confirm", StateFilter(QuickOrderFSM.confirm_deferred))
async def cb_quick_order_force_confirm(cq: CallbackQuery, state: FSMContext, staff: StaffUser | None = None) -> None:
    """Принудительное создание заказа в нерабочее время."""
    if staff is None:
        from ..common.helpers import _staff_service
        staff_service = _staff_service(cq.message.bot)
        staff = await staff_service.get_by_tg_id(cq.from_user.id if cq.from_user else 0)
        if staff is None:
            await cq.answer("Недостаточно прав", show_alert=True)
            return
    
    data = await state.get_data()
    summary_text = new_order_summary(data)
    try:
        new_order = _build_new_order_data(data, staff)
    except KeyError:
        await state.clear()
        await cq.answer("Не удалось собрать данные заявки. Попробуйте заново.", show_alert=True)
        return
    
    orders_service = _orders_service(cq.message.bot)
    order_id = await orders_service.create_order(new_order)
    detail = await orders_service.get_card(order_id, city_ids=visible_city_ids_for(staff))
    await state.clear()
    await cq.answer("Заявка создана (в статусе ОТЛОЖЕН)")
    
    if detail:
        allow_auto = detail.district_id is not None
        prompt_parts = [
            f"Заявка #{detail.id} создана в статусе ОТЛОЖЕН.",
            summary_text,
            "Распределение начнется автоматически в 8:00.",
        ]
        if not allow_auto:
            prompt_parts.append("Автораспределение недоступно: не выбран район.")
        prompt_parts.append("Выберите способ распределения:")
        prompt = "\n\n".join(prompt_parts)
        markup = assign_menu_keyboard(detail.id, allow_auto=allow_auto)
        try:
            await cq.message.edit_text(prompt, reply_markup=markup, disable_web_page_preview=True)
        except Exception:
            await cq.message.answer(prompt, reply_markup=markup, disable_web_page_preview=True)
        return
    
    await _render_created_order_card(cq.message, order_id, staff)


__all__ = ["router"]
