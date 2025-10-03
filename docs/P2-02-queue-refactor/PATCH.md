"""
P2.2: Refactor queue.py to use typed state management.

CHANGES:
1. Replace magic dict keys with typed dataclasses from queue_state.py
2. Use type-safe load/save functions instead of manual dict operations
3. Simplify code by removing redundant helper functions
4. Keep all functionality intact - only internal implementation changes

APPLICATION:
1. Add import: from .queue_state import ...
2. Replace all _load_filters() calls with load_queue_filters()
3. Replace all _save_filters() calls with save_queue_filters()
4. Replace cancel state dict manipulation with typed functions
5. Remove old helper functions (_load_filters, _save_filters, _default_filters, etc.)
"""

# =============================================================================
# STEP 1: ADD IMPORTS
# =============================================================================

# After existing imports, add:
from .queue_state import (
    QueueFilters,
    QueueFiltersMessage,
    CancelOrderState,
    load_queue_filters,
    save_queue_filters,
    load_filters_message,
    save_filters_message,
    load_cancel_state,
    save_cancel_state,
    clear_cancel_state as typed_clear_cancel_state,
)

# =============================================================================
# STEP 2: REMOVE OLD CONSTANTS
# =============================================================================

# DELETE these lines:
# FILTER_DATA_KEY = "queue_filters"
# FILTER_MSG_CHAT_KEY = "queue_filters_chat_id"
# FILTER_MSG_ID_KEY = "queue_filters_message_id"
# CANCEL_ORDER_KEY = "queue_cancel_order_id"
# CANCEL_CHAT_KEY = "queue_cancel_chat_id"
# CANCEL_MESSAGE_KEY = "queue_cancel_message_id"

# =============================================================================
# STEP 3: REMOVE OLD HELPER FUNCTIONS
# =============================================================================

# DELETE these functions:
# def _default_filters() -> dict[str, Optional[str | int]]: ...
# async def _load_filters(state: FSMContext) -> dict[str, Optional[str | int]]: ...
# async def _save_filters(state: FSMContext, filters: dict[str, Optional[str | int]]) -> None: ...
# async def _store_filters_message(state: FSMContext, chat_id: int, message_id: int) -> None: ...
# async def _get_filters_message_ref(state: FSMContext) -> tuple[Optional[int], Optional[int]]: ...

# =============================================================================
# STEP 4: UPDATE _clear_cancel_state
# =============================================================================

# REPLACE function:
async def _clear_cancel_state(state: FSMContext) -> None:
    """Wrapper around typed clear_cancel_state for compatibility."""
    await typed_clear_cancel_state(state)

# =============================================================================
# STEP 5: UPDATE _parse_category_filter
# =============================================================================

# REPLACE function signature:
def _parse_category_filter(value: Optional[OrderCategory]) -> Optional[OrderCategory]:
    """Parse category filter (now already typed)."""
    return value

# =============================================================================
# STEP 6: UPDATE _format_filters_text
# =============================================================================

# REPLACE function to work with QueueFilters dataclass:
async def _format_filters_text(
    staff: StaffUser,
    filters: QueueFilters,  # Changed from dict to QueueFilters
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

# =============================================================================
# STEP 7: UPDATE _edit_or_reply
# =============================================================================

# REPLACE function:
async def _edit_or_reply(message: Message, text: str, markup: InlineKeyboardMarkup, state: FSMContext) -> None:
    try:
        await message.edit_text(text, reply_markup=markup, parse_mode="HTML")
        await save_filters_message(state, message.chat.id, message.message_id)
    except TelegramBadRequest as exc:
        if exc.message == "Message is not modified":
            return
        sent = await message.answer(text, reply_markup=markup, parse_mode="HTML")
        await save_filters_message(state, sent.chat.id, sent.message_id)

# =============================================================================
# STEP 8: UPDATE _render_filters_by_ref
# =============================================================================

# REPLACE function:
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

# =============================================================================
# STEP 9: UPDATE _render_city_selection
# =============================================================================

# REPLACE function:
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

# =============================================================================
# STEP 10: UPDATE _render_queue_list
# =============================================================================

# REPLACE function:
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
        lines.append("📭 Список пуст")
    lines.append("")
    lines.append(f"📄 Страница: {page}")
    text = "\n".join(lines)

    markup = queue_list_keyboard(items, page=page, has_next=has_next)
    await _edit_or_reply(message, text, markup, state)

# =============================================================================
# STEP 11: UPDATE ALL FILTER CALLBACKS
# =============================================================================

# cb_queue_filters_root - no changes needed

# REPLACE cb_queue_filters_city_pick:
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

# REPLACE cb_queue_filters_category:
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

# REPLACE cb_queue_filters_category_pick:
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

# REPLACE cb_queue_filters_status:
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

# REPLACE cb_queue_filters_status_pick:
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

# REPLACE cb_queue_filters_master_input:
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

# REPLACE cb_queue_filters_date_input:
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

# REPLACE cb_queue_filters_reset:
@queue_router.callback_query(
    F.data == "adm:q:flt:reset",
    StaffRoleFilter(_ALLOWED_ROLES),
)
async def cb_queue_filters_reset(cq: CallbackQuery, staff: StaffUser, state: FSMContext) -> None:
    filters = QueueFilters()  # Create default filters
    await save_queue_filters(state, filters)
    await _render_filters_menu(cq.message, staff, state)
    await _safe_answer(cq, "🔄 Фильтры сброшены")

# =============================================================================
# STEP 12: UPDATE CANCEL ORDER CALLBACKS
# =============================================================================

# REPLACE cb_queue_cancel_start:
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

# REPLACE cb_queue_cancel_back:
@queue_router.callback_query(
    F.data.startswith("adm:q:cnl:bk:"),
    StaffRoleFilter(_ALLOWED_ROLES),
)
async def cb_queue_cancel_back(cq: CallbackQuery, staff: StaffUser, state: FSMContext) -> None:
    parts = cq.data.split(":")
    try:
        order_id = int(parts[4])
    except (IndexError, ValueError):
        await _safe_answer(cq, "❌ Неверный ID", show_alert=True)
        return
    
    orders_service = get_service(cq.message.bot, "orders_service")
    order = await _call_service(
        orders_service.get_card,
        order_id,
        city_ids=visible_city_ids_for(staff)
    )
    
    if not order:
        await _clear_cancel_state(state)
        await _safe_answer(cq, "❌ Заказ не найден", show_alert=True)
        return
    
    if staff.role is not StaffRole.GLOBAL_ADMIN and order.city_id not in staff.city_ids:
        await _clear_cancel_state(state)
        await _safe_answer(cq, "❌ Нет доступа", show_alert=True)
        return
    
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
    
    await _render_order_card(cq.message, order, history, show_guarantee=show_guarantee)
    await _clear_cancel_state(state)
    await _safe_answer(cq)

# REPLACE queue_cancel_abort:
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

# REPLACE queue_cancel_reason:
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
