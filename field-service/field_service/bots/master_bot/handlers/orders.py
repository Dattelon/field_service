from __future__ import annotations

import math
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from types import SimpleNamespace

from aiogram import Bot, F, Router
import logging
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, ContentType, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import and_, func, insert, null, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from field_service.bots.common import safe_answer_callback, safe_edit_or_send, safe_send_message
# P1-23: Breadcrumbs navigation
from field_service.bots.common import MasterPaths, add_breadcrumbs_to_text
from field_service.bots.common.copy_utils import copy_button, format_copy_message
from field_service.db import models as m
from field_service.config import settings
from field_service.services import time_service
from field_service.services.commission_service import CommissionService

from ..states import CloseOrderStates
from ..texts import (
    ACTIVE_STATUS_ACTIONS,
    ActiveOrderCard,
    CLOSE_ACT_PROMPT,
    CLOSE_AMOUNT_ERROR,
    CLOSE_AMOUNT_PROMPT,
    CLOSE_DOCUMENT_ERROR,
    CLOSE_DOCUMENT_RECEIVED,
    CLOSE_GUARANTEE_SUCCESS,
    CLOSE_NEXT_STEPS,
    CLOSE_PAYMENT_TEMPLATE,
    CLOSE_SUCCESS_TEMPLATE,
    NAV_BACK,
    NAV_MENU,
    OFFERS_EMPTY,
    OFFERS_HEADER_TEMPLATE,
    OFFERS_REFRESH_BUTTON,
    NO_ACTIVE_ORDERS,
    ORDER_STATUS_TITLES,
    ALERT_ACCEPT_SUCCESS,
    ALERT_ALREADY_TAKEN,
    ALERT_CLOSE_NOT_ALLOWED,
    ALERT_CLOSE_NOT_FOUND,
    ALERT_CLOSE_STATUS,
    ALERT_DECLINE_SUCCESS,
    ALERT_EN_ROUTE_FAIL,
    ALERT_EN_ROUTE_SUCCESS,
    ALERT_LIMIT_REACHED,
    ALERT_ORDER_NOT_FOUND,
    ALERT_WORKING_FAIL,
    ALERT_WORKING_SUCCESS,
    OFFER_DECLINE_CONFIRM,  # P0-1: Добавлен импорт для диалога подтверждения
    alert_account_blocked,
    offer_card,
    offer_line,
    OFFER_NOT_FOUND,
)
from ..utils import (
    cleanup_close_prompts,
    escape_html,
    inline_keyboard,
    normalize_money,
    now_utc,
    remember_close_prompt,
)
from ..keyboards import close_order_cancel_keyboard

router = Router(name="master_orders")
_log = logging.getLogger("master_bot.orders")
_log.info("master_bot.orders module loaded from %s", __file__)


def _callback_uid(callback: CallbackQuery) -> int | None:
    return getattr(getattr(callback, "from_user", None), "id", None)


def _nav_row(back_callback: str, menu_callback: str = "m:menu") -> list[InlineKeyboardButton]:
    return [
        InlineKeyboardButton(text=NAV_BACK, callback_data=back_callback),
        InlineKeyboardButton(text=NAV_MENU, callback_data=menu_callback),
    ]


def menu_row(menu_callback: str = "m:menu") -> list[InlineKeyboardButton]:
    return [InlineKeyboardButton(text=NAV_MENU, callback_data=menu_callback)]


def _parse_offer_callback_payload(data: str, action: str) -> tuple[int, int]:
    parts = data.split(":")
    if len(parts) < 4 or parts[0] != "m" or parts[1] != "new" or parts[2] != action:
        raise ValueError(f"callback mismatch for {action}: {data}")
    try:
        order_id = int(parts[3])
    except ValueError as exc:
        raise ValueError(f"invalid order id in callback: {data}") from exc
    page = 1
    if len(parts) > 4:
        try:
            page_candidate = int(parts[4])
        except ValueError:
            page_candidate = 1
        if page_candidate > 0:
            page = page_candidate
    return order_id, page

OFFERS_PAGE_SIZE = 5
ACTIVE_STATUSES: tuple[m.OrderStatus, ...] = (
    m.OrderStatus.ASSIGNED,
    m.OrderStatus.EN_ROUTE,
    m.OrderStatus.WORKING,
    m.OrderStatus.PAYMENT,
)


def _timeslot_text(
    start_utc: datetime | None,
    end_utc: datetime | None,
    tz_value: str | None = None,
) -> Optional[str]:
    tz = time_service.resolve_timezone(tz_value or settings.timezone)
    return time_service.format_timeslot_local(start_utc, end_utc, tz=tz)


@router.callback_query(F.data == "m:new")
async def offers_root(
    callback: CallbackQuery,
    session: AsyncSession,
    master: m.masters,
) -> None:
    _log.info("offers_root: uid=%s order_id=%s", _callback_uid(callback), None)
    await _render_offers(callback, session, master, page=1)
    await safe_answer_callback(callback)


@router.callback_query(F.data.regexp(r"^m:new:(\d+)$"))
async def offers_page(
    callback: CallbackQuery,
    session: AsyncSession,
    master: m.masters,
) -> None:
    page = int(callback.data.rsplit(":", 1)[-1])
    await _render_offers(callback, session, master, page=page)
    await safe_answer_callback(callback)


@router.callback_query(F.data.regexp(r"^m:new:card:(\d+)(?::(\d+))?$"))
async def offers_card(
    callback: CallbackQuery,
    session: AsyncSession,
    master: m.masters,
) -> None:
    try:
        order_id, page = _parse_offer_callback_payload(callback.data, "card")
    except ValueError as exc:
        _log.warning("offers_card invalid callback: %s", exc)
        await safe_answer_callback(callback, OFFER_NOT_FOUND, show_alert=False)
        await _render_offers(callback, session, master, page=1)
        return
    _log.info("offers_card: uid=%s order_id=%s", _callback_uid(callback), order_id)
    await _render_offer_card(callback, session, master, order_id, page)
    await safe_answer_callback(callback)


@router.callback_query(F.data.regexp(r"^m:new:acc:(\d+)(?::(\d+))?$"))
async def offer_accept(
    callback: CallbackQuery,
    session: AsyncSession,
    master: m.masters,
) -> None:
    """
    Обработчик принятия оффера мастером.
    
    Использует централизованный сервис OrdersService для атомарного принятия оффера.
    """
    _log.info("offer_accept START: master=%s callback_data=%s", master.id, callback.data)
    
    # Шаг 1: Парсим callback_data
    try:
        order_id, page = _parse_offer_callback_payload(callback.data, "acc")
        _log.info("offer_accept: parsed order_id=%s page=%s", order_id, page)
    except ValueError as exc:
        _log.warning("offer_accept invalid callback: %s", exc)
        await safe_answer_callback(callback, ALERT_ORDER_NOT_FOUND, show_alert=False)
        await _render_offers(callback, session, master, page=1)
        return

    # Шаг 2: Проверка блокировки мастера
    if master.is_blocked:
        _log.info("offer_accept: master=%s is BLOCKED, rejecting", master.id)
        block_reason = getattr(master, 'blocked_reason', None)
        alert_text = alert_account_blocked(block_reason)
        await safe_answer_callback(callback, alert_text, show_alert=False)
        return

    # Шаг 3: Проверка лимита активных заказов
    limit = await _get_active_limit(session, master)
    active_orders = await _count_active_orders(session, master.id)
    _log.info("offer_accept: master=%s limit=%s active=%s", master.id, limit, active_orders)
    
    if limit and active_orders >= limit:
        _log.info("offer_accept: master=%s LIMIT REACHED, rejecting", master.id)
        await safe_answer_callback(callback, ALERT_LIMIT_REACHED, show_alert=False)
        return

    # Шаг 4: Находим offer_id по order_id и master_id
    offer_stmt = select(m.offers.id).where(
        and_(
            m.offers.order_id == order_id,
            m.offers.master_id == master.id,
            m.offers.state.in_((m.OfferState.SENT, m.OfferState.VIEWED)),
        )
    ).order_by(m.offers.id.desc()).limit(1)
    
    offer_result = await session.execute(offer_stmt)
    offer_row = offer_result.first()
    
    if offer_row is None:
        _log.warning("offer_accept: no active offer found for order=%s master=%s", order_id, master.id)
        await safe_answer_callback(callback, "⚠️ Оффер не найден", show_alert=False)
        await _render_offers(callback, session, master, page=page)
        return
    
    offer_id = offer_row.id
    _log.info("offer_accept: found offer_id=%s for order=%s master=%s", offer_id, order_id, master.id)

    # Шаг 5: Используем централизованный сервис для принятия оффера
    from field_service.services.orders_service import OrdersService
    
    orders_service = OrdersService(session)
    success, error_message = await orders_service.accept_offer(
        offer_id=offer_id,
        master_id=master.id,
    )
    
    if not success:
        _log.warning("offer_accept: failed to accept offer_id=%s: %s", offer_id, error_message)
        await safe_answer_callback(callback, error_message or "❌ Не удалось принять заказ", show_alert=False)
        await _render_offers(callback, session, master, page=page)
        return
    
    # Шаг 6: Успешное принятие - показываем карточку принятого заказа
    _log.info("offer_accept SUCCESS: order=%s assigned to master=%s", order_id, master.id)
    await safe_answer_callback(callback, ALERT_ACCEPT_SUCCESS, show_alert=False)
    await _render_active_order(callback, session, master, order_id=order_id)



@router.callback_query(F.data.regexp(r"^m:new:dec:(\d+)(?::(\d+))?$"))
async def offer_decline_confirm(
    callback: CallbackQuery,
    session: AsyncSession,
    master: m.masters,
) -> None:
    """Показывает диалог подтверждения перед отклонением оффера."""
    try:
        order_id, page = _parse_offer_callback_payload(callback.data, "dec")
    except ValueError as exc:
        _log.warning("offer_decline_confirm invalid callback: %s", exc)
        await safe_answer_callback(callback, ALERT_ORDER_NOT_FOUND, show_alert=False)
        await _render_offers(callback, session, master, page=1)
        return
    
    _log.info("offer_decline_confirm: uid=%s order_id=%s", _callback_uid(callback), order_id)
    
    # Формируем текст подтверждения
    confirm_text = OFFER_DECLINE_CONFIRM.format(order_id=order_id)
    
    # Клавиатура с подтверждением
    keyboard = inline_keyboard([
        [
            InlineKeyboardButton(
                text="✅ Да, отклонить",
                callback_data=f"m:new:dec_yes:{order_id}:{page}"
            ),
            InlineKeyboardButton(
                text="❌ Нет, вернуться",
                callback_data=f"m:new:card:{order_id}:{page}"
            ),
        ]
    ])
    
    await safe_edit_or_send(callback, confirm_text, keyboard)
    await safe_answer_callback(callback)


# P0-1: Финальное отклонение после подтверждения
@router.callback_query(F.data.regexp(r"^m:new:dec_yes:(\d+)(?::(\d+))?$"))
async def offer_decline_execute(
    callback: CallbackQuery,
    session: AsyncSession,
    master: m.masters,
) -> None:
    """Выполняет отклонение оффера после подтверждения."""
    try:
        order_id, page = _parse_offer_callback_payload(callback.data, "dec_yes")
    except ValueError as exc:
        _log.warning("offer_decline_execute invalid callback: %s", exc)
        await safe_answer_callback(callback, ALERT_ORDER_NOT_FOUND, show_alert=False)
        await _render_offers(callback, session, master, page=1)
        return

    _log.info("offer_decline_execute: uid=%s order_id=%s", _callback_uid(callback), order_id)

    await session.execute(
        update(m.offers)
        .where((m.offers.order_id == order_id) & (m.offers.master_id == master.id))
        .values(state=m.OfferState.DECLINED, responded_at=func.now())
    )
    await session.commit()

    # Показываем уведомление об успехе
    await safe_answer_callback(callback, ALERT_DECLINE_SUCCESS, show_alert=False)
    
    # Возвращаем в главное меню
    from field_service.bots.common import safe_delete_and_send
    from ..keyboards import main_menu_keyboard
    
    menu_text = f"✅ Заказ #{order_id} отменён.\n\nВыберите действие:"
    await safe_delete_and_send(callback, menu_text, reply_markup=main_menu_keyboard(master))


@router.callback_query(F.data == "m:act")
async def active_order_entry(
    callback: CallbackQuery,
    session: AsyncSession,
    master: m.masters,
) -> None:
    _log.info("active_order_entry: uid=%s order_id=%s", _callback_uid(callback), None)
    await _render_active_order(callback, session, master, order_id=None)
    await safe_answer_callback(callback)


@router.callback_query(F.data.regexp(r"^m:act:card:(\d+)$"))
async def active_order_card(
    callback: CallbackQuery,
    session: AsyncSession,
    master: m.masters,
) -> None:
    order_id = int(callback.data.split(":")[-1])
    _log.info("active_order_card: uid=%s order_id=%s", _callback_uid(callback), order_id)
    await _render_active_order(callback, session, master, order_id=order_id)
    await safe_answer_callback(callback)


@router.callback_query(F.data.regexp(r"^m:act:enr:(\d+)$"))
async def active_set_enroute(
    callback: CallbackQuery,
    session: AsyncSession,
    master: m.masters,
) -> None:
    order_id = int(callback.data.split(":")[-1])
    _log.info("active_set_enroute: uid=%s order_id=%s", _callback_uid(callback), order_id)
    changed = await _update_order_status(
        session,
        master.id,
        order_id,
        expected=m.OrderStatus.ASSIGNED,
        new=m.OrderStatus.EN_ROUTE,
        reason="master_en_route",
    )
    if not changed:
        await safe_answer_callback(callback, ALERT_EN_ROUTE_FAIL, show_alert=False)
        return
    await safe_answer_callback(callback, ALERT_EN_ROUTE_SUCCESS)
    await _render_active_order(callback, session, master, order_id=order_id)


@router.callback_query(F.data.regexp(r"^m:act:wrk:(\d+)$"))
async def active_set_working(
    callback: CallbackQuery,
    session: AsyncSession,
    master: m.masters,
) -> None:
    order_id = int(callback.data.split(":")[-1])
    _log.info("active_set_working: uid=%s order_id=%s", _callback_uid(callback), order_id)
    changed = await _update_order_status(
        session,
        master.id,
        order_id,
        expected=m.OrderStatus.EN_ROUTE,
        new=m.OrderStatus.WORKING,
        reason="master_working",
    )
    if not changed:
        await safe_answer_callback(callback, ALERT_WORKING_FAIL, show_alert=False)
        return
    await safe_answer_callback(callback, ALERT_WORKING_SUCCESS)
    await _render_active_order(callback, session, master, order_id=order_id)


async def _send_close_prompt(
    bot: Bot | None,
    master: m.masters,
    callback: CallbackQuery,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> Message | None:
    """Send the next-step prompt reliably regardless of callback message availability.

    In some environments callback.message may be present but lack a bound bot instance,
    which makes Message.answer() a no-op or raises. To be robust, always resolve the
    target chat id and use safe_send_message with an explicit bot instance.
    """
    # First try the simplest path: answer directly to the source message if possible.
    try:
        if getattr(callback, "message", None) is not None:
            return await callback.message.answer(text, reply_markup=reply_markup)
    except Exception:
        pass  # Fallback to explicit send

    # Resolve target chat id: prefer message.chat.id, then callback.from_user.id, then master.tg_user_id
    target_id = None
    if getattr(callback, "message", None) is not None and getattr(callback.message, "chat", None) is not None:
        target_id = getattr(callback.message.chat, "id", None)
    if target_id is None:
        target_id = getattr(getattr(callback, "from_user", None), "id", None)
    if target_id is None:
        target_id = getattr(master, "tg_user_id", None)
    if target_id is None:
        _log.warning(
            "active_close_start: no target chat for callback id=%s",
            getattr(callback, "id", None),
        )
        return None

    # Resolve bot instance: prefer injected bot, then callback.bot, then message.bot
    bot_instance = bot or getattr(callback, "bot", None)
    if bot_instance is None and getattr(callback, "message", None) is not None:
        bot_instance = getattr(callback.message, "bot", None)
    if bot_instance is None:
        _log.warning(
            "_send_close_prompt: no bot instance for callback id=%s",
            getattr(callback, "id", None),
        )
        return None

    return await safe_send_message(bot_instance, target_id, text, reply_markup=reply_markup)


@router.callback_query(F.data.regexp(r"^m:act:cls:(\d+)$"))
async def active_close_start(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    master: m.masters,
    bot: Bot | None = None,
) -> None:
    order_id = int(callback.data.split(":")[-1])
    _log.info("active_close_start: uid=%s order_id=%s", _callback_uid(callback), order_id)
    
    try:
        order = await session.get(m.orders, order_id)
    except Exception as exc:
        _log.exception("active_close_start: FAILED to load order: %s", exc)
        await safe_answer_callback(callback, "Ошибка загрузки заказа", show_alert=False)
        return
    if order is None or order.assigned_master_id != master.id:
        _log.warning("active_close_start: order not found or not assigned to master")
        await safe_answer_callback(callback, ALERT_ORDER_NOT_FOUND, show_alert=False)
        return
    if order.status != m.OrderStatus.WORKING:
        _log.warning(
            "active_close_start: order status not WORKING, current=%s, sending alert",
            order.status,
        )
        await safe_answer_callback(callback, ALERT_CLOSE_NOT_ALLOWED, show_alert=False)
        return

    await state.update_data(close_order_id=order_id, close_order_amount=None)

    bot_instance = bot or getattr(callback, "bot", None)
    if bot_instance is None and callback.message is not None:
        bot_instance = callback.message.bot

    chat_id = None
    if getattr(callback, "message", None) is not None and getattr(callback.message, "chat", None) is not None:
        chat_id = getattr(callback.message.chat, "id", None)

    await cleanup_close_prompts(state, bot_instance, chat_id)

    order_type = getattr(order, "type", getattr(order, "order_type", None))
    if order_type == m.OrderType.GUARANTEE:
        await state.update_data(close_order_amount=str(Decimal("0")))
        await state.set_state(CloseOrderStates.act)
        prompt_text = CLOSE_ACT_PROMPT
    else:
        await state.set_state(CloseOrderStates.amount)
        prompt_text = CLOSE_AMOUNT_PROMPT

    state_snapshot = await state.get_data()
    try:
        current_state = await state.get_state()
    except AttributeError:
        current_state = getattr(state, "state", None)
    _log.info(
        "active_close_start: state=%s data=%s",
        current_state,
        state_snapshot,
    )

    prompt_message = await _send_close_prompt(
        bot_instance,
        master,
        callback,
        prompt_text,
        reply_markup=close_order_cancel_keyboard(),
    )
    await remember_close_prompt(state, prompt_message)
    await safe_answer_callback(callback)


@router.callback_query(F.data == "m:act:cls:cancel")
async def active_close_cancel(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    master: m.masters,
) -> None:
    """P0-3: Обработчик отмены процесса закрытия заказа."""
    _log.info("active_close_cancel: uid=%s", _callback_uid(callback))
    
    # Получаем order_id перед очисткой state
    data = await state.get_data()
    order_id = data.get("close_order_id")

    message = callback.message
    bot_instance = getattr(message, "bot", None) or getattr(callback, "bot", None)
    chat_id = getattr(getattr(message, "chat", None), "id", None)
    await cleanup_close_prompts(state, bot_instance, chat_id)

    # Очищаем FSM state
    await state.clear()
    
    # Показываем уведомление
    await safe_answer_callback(callback, "❌ Закрытие заказа отменено")
    
    # Возвращаемся к карточке активного заказа
    if order_id:
        await _render_active_order(callback, session, master, order_id=int(order_id))
    else:
        # Если order_id нет, возвращаемся к списку активных заказов
        await _render_active_order(callback, session, master, order_id=None)


@router.message(CloseOrderStates.amount)
async def active_close_amount(message: Message, state: FSMContext) -> None:
    amount = normalize_money(message.text or "")
    bot_instance = getattr(message, "bot", None)
    chat = getattr(message, "chat", None)
    chat_id = getattr(chat, "id", None)
    if amount is None:
        await cleanup_close_prompts(state, bot_instance, chat_id)
        prompt = await message.answer(
            CLOSE_AMOUNT_ERROR,
            reply_markup=close_order_cancel_keyboard(),
        )
        await remember_close_prompt(state, prompt)
        return
    _log.info("active_close_amount: uid=%s amount=%s", getattr(getattr(message, "from_user", None), "id", None), amount)
    await state.update_data(close_order_amount=str(amount))
    await cleanup_close_prompts(state, bot_instance, chat_id)
    await state.set_state(CloseOrderStates.act)
    prompt = await message.answer(
        CLOSE_ACT_PROMPT,
        reply_markup=close_order_cancel_keyboard(),
    )
    await remember_close_prompt(state, prompt)


@router.message(
    CloseOrderStates.act,
    F.content_type.in_({ContentType.PHOTO, ContentType.DOCUMENT}),
)
async def active_close_act(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    master: m.masters,
) -> None:
    data = await state.get_data()
    order_id = int(data.get("close_order_id"))
    amount = Decimal(str(data.get("close_order_amount", "0")))

    bot_instance = getattr(message, "bot", None)
    chat = getattr(message, "chat", None)
    chat_id = getattr(chat, "id", None)

    _log.info(
        "active_close_act: uid=%s order_id=%s amount=%s content_type=%s",
        getattr(getattr(message, "from_user", None), "id", None),
        order_id,
        amount,
        getattr(message, "content_type", None),
    )

    order = await session.get(m.orders, order_id)
    if order is None or order.assigned_master_id != master.id:
        await message.answer(ALERT_CLOSE_NOT_FOUND)
        await cleanup_close_prompts(state, bot_instance, chat_id)
        await state.clear()
        return
    if order.status != m.OrderStatus.WORKING:
        await message.answer(ALERT_CLOSE_STATUS)
        await cleanup_close_prompts(state, bot_instance, chat_id)
        await state.clear()
        return

    file_id = message.photo[-1].file_id if message.photo else message.document.file_id
    file_type = (
        m.AttachmentFileType.PHOTO if message.photo else m.AttachmentFileType.DOCUMENT
    )
    session.add(
        m.attachments(
            entity_type=m.AttachmentEntity.ORDER,
            entity_id=order_id,
            file_type=file_type,
            file_id=file_id,
            uploaded_by_master_id=master.id,
        )
    )

    order_type = getattr(order, "type", getattr(order, "order_type", None))
    is_guarantee = order_type == m.OrderType.GUARANTEE
    order.updated_at = now_utc()
    order.version = (order.version or 0) + 1

    if is_guarantee:
        order.total_sum = Decimal("0")
        order.status = m.OrderStatus.CLOSED
        await session.execute(
            insert(m.order_status_history).values(
                order_id=order_id,
                from_status=m.OrderStatus.WORKING,
                to_status=m.OrderStatus.CLOSED,
                changed_by_master_id=master.id,
                reason="guarantee_completed",
                actor_type=m.ActorType.MASTER,
            )
        )
        # P1-01: Добавляем в очередь автозакрытия
        from field_service.services.autoclose_scheduler import enqueue_order_for_autoclose
        await enqueue_order_for_autoclose(
            session,
            order_id=order.id,
            closed_at=now_utc()
        )
    else:
        order.total_sum = amount
        order.status = m.OrderStatus.PAYMENT
        await session.execute(
            insert(m.order_status_history).values(
                order_id=order_id,
                from_status=m.OrderStatus.WORKING,
                to_status=m.OrderStatus.PAYMENT,
                changed_by_master_id=master.id,
                reason="master_uploaded_act",
                actor_type=m.ActorType.MASTER,
            )
        )
        await CommissionService(session).create_for_order(order_id)

    await session.commit()
    await cleanup_close_prompts(state, bot_instance, chat_id)
    await state.clear()

    # Возврат в главное меню с информативным сообщением
    from ..keyboards import main_menu_keyboard
    
    if is_guarantee:
        text = CLOSE_GUARANTEE_SUCCESS.format(order_id=order_id)
    else:
        text = CLOSE_NEXT_STEPS.format(order_id=order_id, amount=amount)
    
    await message.answer(text, reply_markup=main_menu_keyboard(master))


@router.message(CloseOrderStates.act)
async def active_close_act_invalid(message: Message, state: FSMContext) -> None:
    bot_instance = getattr(message, "bot", None)
    chat = getattr(message, "chat", None)
    chat_id = getattr(chat, "id", None)
    await cleanup_close_prompts(state, bot_instance, chat_id)
    prompt = await message.answer(
        CLOSE_DOCUMENT_ERROR,
        reply_markup=close_order_cancel_keyboard(),
    )
    await remember_close_prompt(state, prompt)


async def _render_offers(
    event: Message | CallbackQuery,
    session: AsyncSession,
    master: m.masters,
    *,
    page: int,
) -> None:
    offers = await _load_offers(session, master.id)
    if not offers:
        keyboard = inline_keyboard(
            [
                [InlineKeyboardButton(text=OFFERS_REFRESH_BUTTON, callback_data="m:new")],
                menu_row(),
            ]
        )
        await safe_edit_or_send(event, OFFERS_EMPTY, keyboard)
        return

    total = len(offers)
    pages = max(1, math.ceil(total / OFFERS_PAGE_SIZE))
    page = max(1, min(page, pages))
    start = (page - 1) * OFFERS_PAGE_SIZE
    chunk = offers[start : start + OFFERS_PAGE_SIZE]

    lines = [OFFERS_HEADER_TEMPLATE.format(page=page, pages=pages, total=total), ""]
    keyboard_rows: list[list[InlineKeyboardButton]] = []
    for item in chunk:
        order_id = item.order_id
        category_value = (
            item.category.value
            if isinstance(item.category, m.OrderCategory)
            else str(item.category or "—")
        )
        lines.append(
            offer_line(
                order_id,
                item.city or "—",
                item.district,
                category_value,
                item.timeslot_text,
            )
        )
        keyboard_rows.append(
            [
                InlineKeyboardButton(
                    text=f"Открыть #{order_id}",
                    callback_data=f"m:new:card:{order_id}:{page}",
                )
            ]
        )

    if pages > 1:
        nav_row: list[InlineKeyboardButton] = []
        if page > 1:
            nav_row.append(
                InlineKeyboardButton(text="◀️ Назад", callback_data=f"m:new:{page - 1}")
            )
        if page < pages:
            nav_row.append(
                InlineKeyboardButton(text="Вперёд ▶️", callback_data=f"m:new:{page + 1}")
            )
        if nav_row:
            keyboard_rows.append(nav_row)

    keyboard_rows.append(menu_row())

    keyboard = inline_keyboard(keyboard_rows)
    
    # P1-23: Add breadcrumbs navigation
    text_without_breadcrumbs = "\n".join(lines)
    text = add_breadcrumbs_to_text(text_without_breadcrumbs, MasterPaths.NEW_ORDERS)
    
    try:
        await safe_edit_or_send(event, text, keyboard)
    except Exception as exc:  # telemetry for hard-to-reproduce UI issues
        _log.exception("render_offers failed: %s", exc)
        # Fallback: send minimal plain text without keyboard
        if isinstance(event, CallbackQuery) and event.message is not None:
            await event.message.answer(text)


async def _render_offer_card(
    event: Message | CallbackQuery,
    session: AsyncSession,
    master: m.masters,
    order_id: int,
    page: int,
) -> None:
    row = await _load_offer_detail(session, master.id, order_id)
    if row is None:
        await safe_edit_or_send(
            event,
            OFFER_NOT_FOUND,
            inline_keyboard([
                _nav_row("m:new")
            ]),
        )
        return

    order = row.order
    slot_text = _timeslot_text(
        order.timeslot_start_utc,
        order.timeslot_end_utc,
        getattr(row, "city_tz", None),
    )
    category = (
        order.category.value
        if isinstance(order.category, m.OrderCategory)
        else str(order.category or "—")
    )
    card_text = offer_card(
        order_id=order.id,
        city=row.city or "—",
        district=row.district,
        street=row.street,
        house=order.house,
        timeslot=slot_text,
        category=str(category),
        description=order.description or "",
    )

    keyboard = inline_keyboard(
        [
            [
                InlineKeyboardButton(
                    text="✅ Взять",
                    callback_data=f"m:new:acc:{order.id}:{page}",
                ),
                InlineKeyboardButton(
                    text="✖️ Отказаться",
                    callback_data=f"m:new:dec:{order.id}:{page}",
                ),
            ],
            _nav_row(f"m:new:{page}" if page > 1 else "m:new"),
        ]
    )
    await safe_edit_or_send(event, card_text, keyboard)


async def _render_active_order(
    event: Message | CallbackQuery,
    session: AsyncSession,
    master: m.masters,
    order_id: int | None,
) -> None:
    """Отображает активные заказы мастера.
    
    Если order_id=None - показывает список всех активных заказов.
    Если order_id передан - показывает карточку конкретного заказа.
    """
    _log.info("_render_active_order START: master=%s order_id=%s", master.id, order_id)
    if order_id is None:
        # Показываем список всех активных заказов
        _log.info("_render_active_order: loading all active orders for master=%s", master.id)
        active_orders = await _load_active_orders(session, master.id)
        _log.info("_render_active_order: found %d active orders", len(active_orders))
        
        if not active_orders:
            await safe_edit_or_send(
                event,
                NO_ACTIVE_ORDERS,
                inline_keyboard([
                    menu_row()
                ]),
            )
            return
        
        # Формируем заголовок
        count = len(active_orders)
        if count == 1:
            header = "<b>📦 Активный заказ</b>"
        else:
            header = f"<b>📦 Активные заказы ({count})</b>"
        
        lines = [header, ""]
        keyboard_rows: list[list[InlineKeyboardButton]] = []
        
        for row in active_orders:
            order = row.order
            status_title = ORDER_STATUS_TITLES.get(order.status, order.status.value)
            slot_text = _timeslot_text(
                order.timeslot_start_utc,
                order.timeslot_end_utc,
                getattr(row, "city_tz", None),
            )
            
            # Добавляем строку с кратким описанием заказа
            category = (
                order.category.value
                if isinstance(order.category, m.OrderCategory)
                else str(order.category or "—")
            )
            line = f"#{order.id} • {row.city or '—'}"
            if row.district:
                line += f", {row.district}"
            line += f" • {category}"
            if slot_text:
                line += f" • {slot_text}"
            line += f"\n🔁 {status_title}"
            lines.append(line)
            
            # Добавляем кнопку для открытия карточки
            keyboard_rows.append(
                [
                    InlineKeyboardButton(
                        text=f"Открыть #{order.id}",
                        callback_data=f"m:act:card:{order.id}",
                    )
                ]
            )
            lines.append("")  # Пустая строка между заказами
        
        keyboard_rows.append(menu_row())
        keyboard = inline_keyboard(keyboard_rows)
        
        # P1-23: Add breadcrumbs navigation
        text_without_breadcrumbs = "\n".join(lines)
        text = add_breadcrumbs_to_text(text_without_breadcrumbs, MasterPaths.ACTIVE_ORDERS)
        
        try:
            await safe_edit_or_send(event, text, keyboard)
        except Exception as exc:
            _log.exception("render_active_orders_list failed: %s", exc)
            if isinstance(event, CallbackQuery) and event.message is not None:
                await event.message.answer(text)
        return
    
    # Показываем карточку конкретного заказа
    _log.info("_render_active_order: loading specific order=%s for master=%s", order_id, master.id)
    row = await _load_active_order(session, master.id, order_id)
    _log.info("_render_active_order: order loaded, found=%s", row is not None)
    if row is None:
        _log.warning("_render_active_order: order=%s not found or not active for master=%s", order_id, master.id)
        await safe_edit_or_send(
            event,
            "❌ Заказ не найден или уже не активен.",
            inline_keyboard([
                _nav_row("m:act")
            ]),
        )
        return

    order = row.order
    slot_text = _timeslot_text(
        order.timeslot_start_utc,
        order.timeslot_end_utc,
        getattr(row, "city_tz", None),
    )
    card = ActiveOrderCard(
        order_id=order.id,
        city=row.city or "—",
        district=row.district,
        street=row.street,
        house=order.house,
        timeslot=slot_text,
        status=order.status,
        category=order.category.value if isinstance(order.category, m.OrderCategory) else str(order.category or ""),
    )
    text_lines = card.lines()

    if order.status in ACTIVE_STATUSES or order.status == m.OrderStatus.PAYMENT:
        text_lines.append(
            f"👤 Клиент: {escape_html(order.client_name or '—')}"
        )
        text_lines.append(
            f"📞 Телефон: {escape_html(order.client_phone or '—')}"
        )

    if order.description:
        text_lines.extend(["", escape_html(order.description)])

    keyboard_rows: list[list[InlineKeyboardButton]] = []
    action = ACTIVE_STATUS_ACTIONS.get(order.status)
    if action:
        title, prefix = action
        keyboard_rows.append(
            [InlineKeyboardButton(text=title, callback_data=f"{prefix}:{order.id}")]
        )

    # P0-4: Кнопка "Позвонить клиенту" убрана т.к. tel: ссылки не работают в Telegram
    # Телефон виден в тексте и копируется через кнопку "📋 Телефон"
    
    # P1-19: Кнопки быстрого копирования
    if order.status in ACTIVE_STATUSES or order.status == m.OrderStatus.PAYMENT:
        copy_row: list[InlineKeyboardButton] = []
        if order.client_phone:
            copy_row.append(copy_button("📋 Телефон", order.id, "cph", "m"))
        # Адрес всегда доступен для копирования
        copy_row.append(copy_button("📋 Адрес", order.id, "addr", "m"))
        if copy_row:
            keyboard_rows.append(copy_row)

    keyboard_rows.append(_nav_row("m:act"))
    keyboard = inline_keyboard(keyboard_rows)
    
    # P1-23: Add breadcrumbs navigation
    text_without_breadcrumbs = "\n".join(text_lines)
    breadcrumb_path = MasterPaths.active_order_card(order.id)
    text = add_breadcrumbs_to_text(text_without_breadcrumbs, breadcrumb_path)
    
    _log.info("_render_active_order: sending card for order=%s to master=%s", order_id, master.id)
    try:
        await safe_edit_or_send(event, text, keyboard)
        _log.info("_render_active_order: card sent successfully for order=%s", order_id)
    except Exception as exc:
        _log.exception("render_active failed: %s", exc)
        if isinstance(event, CallbackQuery) and event.message is not None:
            await event.message.answer(text)


async def _update_order_status(
    session: AsyncSession,
    master_id: int,
    order_id: int,
    *,
    expected: m.OrderStatus,
    new: m.OrderStatus,
    reason: str,
) -> bool:
    updated = await session.execute(
        update(m.orders)
        .where(
            and_(
                m.orders.id == order_id,
                m.orders.assigned_master_id == master_id,
                m.orders.status == expected,
            )
        )
        .values(status=new, updated_at=func.now())
        .returning(m.orders.id)
    )
    if not updated.first():
        await session.rollback()
        return False
    await session.execute(
        insert(m.order_status_history).values(
            order_id=order_id,
            from_status=expected,
            to_status=new,
            changed_by_master_id=master_id,
            reason=reason,
            actor_type=m.ActorType.MASTER,
        )
    )
    await session.commit()
    return True


async def _load_offers(session: AsyncSession, master_id: int) -> list[SimpleNamespace]:
    stmt = (
        select(
            m.offers.order_id,
            m.cities.name.label("city"),
            m.districts.name.label("district"),
            m.orders.category,
            m.cities.timezone.label("city_tz"),
            m.orders.timeslot_start_utc,
            m.orders.timeslot_end_utc,
        )
        .join(m.orders, m.orders.id == m.offers.order_id)
        .join(m.cities, m.cities.id == m.orders.city_id)
        .outerjoin(m.districts, m.districts.id == m.orders.district_id)
        .where(
            m.offers.master_id == master_id,
            m.offers.state.in_((m.OfferState.SENT, m.OfferState.VIEWED)),
            m.orders.status != m.OrderStatus.DEFERRED,  # ✅ Скрываем DEFERRED от мастеров
            m.offers.expires_at > func.now(),  # ✅ BUGFIX: Скрываем истёкшие офферы
        )
        .order_by(m.offers.sent_at.desc(), m.offers.order_id.desc())
    )
    result = await session.execute(stmt)
    rows = []
    for row in result:
        rows.append(
            SimpleNamespace(
                order_id=row.order_id,
                city=row.city,
                district=row.district,
                category=row.category,
                city_tz=row.city_tz,
                timeslot_start=row.timeslot_start_utc,
                timeslot_end=row.timeslot_end_utc,
                timeslot_text=_timeslot_text(row.timeslot_start_utc, row.timeslot_end_utc, row.city_tz),
            )
        )
    return rows


async def _load_offer_detail(
    session: AsyncSession,
    master_id: int,
    order_id: int,
) -> SimpleNamespace | None:
    stmt = (
        select(
            m.orders,
            m.cities.name.label("city"),
            m.cities.timezone.label("city_tz"),
            m.districts.name.label("district"),
            m.streets.name.label("street"),
        )
        .join(m.cities, m.cities.id == m.orders.city_id)
        .outerjoin(m.districts, m.districts.id == m.orders.district_id)
        .outerjoin(m.streets, m.streets.id == m.orders.street_id)
        .join(m.offers, and_(m.offers.order_id == m.orders.id, m.offers.master_id == master_id))
        .where(m.orders.id == order_id)
        .limit(1)
    )
    row = (await session.execute(stmt)).first()
    if not row:
        return None
    return SimpleNamespace(order=row.orders, city=row.city, city_tz=row.city_tz, district=row.district, street=row.street)


async def _load_active_orders(
    session: AsyncSession,
    master_id: int,
) -> list[SimpleNamespace]:
    """Загружает список всех активных заказов мастера."""
    stmt = (
        select(
            m.orders,
            m.cities.name.label("city"),
            m.cities.timezone.label("city_tz"),
            m.districts.name.label("district"),
            m.streets.name.label("street"),
        )
        .join(m.cities, m.cities.id == m.orders.city_id)
        .outerjoin(m.districts, m.districts.id == m.orders.district_id)
        .outerjoin(m.streets, m.streets.id == m.orders.street_id)
        .where(
            m.orders.assigned_master_id == master_id,
            m.orders.status.in_(ACTIVE_STATUSES),
        )
        .order_by(m.orders.updated_at.desc(), m.orders.id.desc())
    )
    result = await session.execute(stmt)
    rows = []
    for row in result:
        rows.append(
            SimpleNamespace(
                order=row.orders,
                city=row.city,
                city_tz=row.city_tz,
                district=row.district,
                street=row.street,
            )
        )
    return rows


async def _load_active_order(
    session: AsyncSession,
    master_id: int,
    order_id: int | None,
) -> SimpleNamespace | None:
    stmt = (
        select(
            m.orders,
            m.cities.name.label("city"),
            m.cities.timezone.label("city_tz"),
            m.districts.name.label("district"),
            m.streets.name.label("street"),
        )
        .join(m.cities, m.cities.id == m.orders.city_id)
        .outerjoin(m.districts, m.districts.id == m.orders.district_id)
        .outerjoin(m.streets, m.streets.id == m.orders.street_id)
        .where(
            m.orders.assigned_master_id == master_id,
            m.orders.status.in_(ACTIVE_STATUSES),
        )
        .order_by(m.orders.updated_at.desc(), m.orders.id.desc())
    )
    if order_id is not None:
        stmt = stmt.where(m.orders.id == order_id)
    row = (await session.execute(stmt)).first()
    if not row:
        return None
    return SimpleNamespace(order=row.orders, city=row.city, city_tz=row.city_tz, district=row.district, street=row.street)


async def _get_active_limit(session: AsyncSession, master: m.masters) -> int:
    if master.max_active_orders_override is not None and master.max_active_orders_override > 0:
        return master.max_active_orders_override
    value = (
        await session.execute(
            select(m.settings.value).where(m.settings.key == "max_active_orders")
        )
    ).scalar_one_or_none()
    try:
        return int(value) if value is not None else 5
    except (TypeError, ValueError):
        return 5


async def _count_active_orders(session: AsyncSession, master_id: int) -> int:
    stmt = (
        select(func.count())
        .select_from(m.orders)
        .where(
            m.orders.assigned_master_id == master_id,
            m.orders.status.in_(ACTIVE_STATUSES),
        )
    )
    return int((await session.execute(stmt)).scalar_one())


# P1-19: Handler для быстрого копирования данных
@router.callback_query(F.data.regexp(r"^m:copy:(cph|addr):(\d+)$"))
async def copy_data_handler(
    callback: CallbackQuery,
    session: AsyncSession,
    master: m.masters,
) -> None:
    """
    Обрабатывает копирование данных заказа (телефон, адрес).
    
    Callback format: m:copy:type:order_id
    - type: cph (client_phone) или addr (address)
    - order_id: ID заказа
    """
    parts = callback.data.split(":")
    if len(parts) != 4:
        await safe_answer_callback(callback, "Ошибка формата", show_alert=False)
        return
    
    data_type = parts[2]
    try:
        order_id = int(parts[3])
    except ValueError:
        await safe_answer_callback(callback, "Неверный ID заказа", show_alert=False)
        return
    
    # Загружаем заказ из БД
    stmt = (
        select(
            m.orders.id,
            m.orders.client_phone,
            m.orders.house,
            m.cities.name.label("city"),
            m.districts.name.label("district"),
            m.streets.name.label("street"),
        )
        .join(m.cities, m.cities.id == m.orders.city_id)
        .outerjoin(m.districts, m.districts.id == m.orders.district_id)
        .outerjoin(m.streets, m.streets.id == m.orders.street_id)
        .where(
            m.orders.id == order_id,
            m.orders.assigned_master_id == master.id,
        )
    )
    row = (await session.execute(stmt)).first()
    
    if not row:
        await safe_answer_callback(callback, "Заказ не найден", show_alert=False)
        return
    
    # Формируем данные для копирования
    if data_type == "cph":
        if not row.client_phone:
            await safe_answer_callback(callback, "Телефон не указан", show_alert=False)
            return
        data = row.client_phone
    elif data_type == "addr":
        address_parts = [row.city]
        if row.district:
            address_parts.append(row.district)
        if row.street:
            address_parts.append(row.street)
        if row.house:
            address_parts.append(str(row.house))
        data = ", ".join(address_parts)
    else:
        await safe_answer_callback(callback, "Неизвестный тип данных", show_alert=False)
        return
    
    # Отправляем данные: короткое уведомление в alert и подробности в отдельном сообщении
    message_text = format_copy_message(data_type, data)
    await safe_answer_callback(callback, "📋 Данные отправлены", show_alert=False)

    target_chat_id = None
    if callback.message is not None:
        target_chat_id = callback.message.chat.id
    elif callback.from_user is not None:
        target_chat_id = callback.from_user.id

    if target_chat_id is not None:
        await safe_send_message(
            callback.bot,
            target_chat_id,
            message_text,
            parse_mode="HTML",
        )

    _log.info(
        "copy_data: uid=%s order_id=%s type=%s",
        _callback_uid(callback),
        order_id,
        data_type,
    )


