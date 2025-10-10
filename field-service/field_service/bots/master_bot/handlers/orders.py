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
from ..utils import escape_html, inline_keyboard, normalize_money, now_utc
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
        await safe_answer_callback(callback, OFFER_NOT_FOUND, show_alert=True)
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
    _log.info("offer_accept START: master=%s callback_data=%s", master.id, callback.data)
    try:
        order_id, page = _parse_offer_callback_payload(callback.data, "acc")
        _log.info("offer_accept: parsed order_id=%s page=%s", order_id, page)
    except ValueError as exc:
        _log.warning("offer_accept invalid callback: %s", exc)
        await safe_answer_callback(callback, ALERT_ORDER_NOT_FOUND, show_alert=True)
        await _render_offers(callback, session, master, page=1)
        return

    if master.is_blocked:
        _log.info("offer_accept: master=%s is BLOCKED, rejecting", master.id)
        # P0-4: Показываем причину блокировки
        block_reason = getattr(master, 'blocked_reason', None)
        alert_text = alert_account_blocked(block_reason)
        await safe_answer_callback(callback, alert_text, show_alert=True)
        return

    limit = await _get_active_limit(session, master)
    active_orders = await _count_active_orders(session, master.id)
    _log.info("offer_accept: master=%s limit=%s active=%s", master.id, limit, active_orders)
    if limit and active_orders >= limit:
        _log.info("offer_accept: master=%s LIMIT REACHED, rejecting", master.id)
        await safe_answer_callback(callback, ALERT_LIMIT_REACHED, show_alert=True)
        return

    _log.info("offer_accept: acquiring lock on order=%s", order_id)
    # ✅ FIX 1.1: Атомарная блокировка заказа с FOR UPDATE SKIP LOCKED
    # Предотвращает Race Condition при параллельных запросах от разных мастеров
    order_snapshot = await session.execute(
        select(m.orders.status, m.orders.assigned_master_id, m.orders.version)
        .where(m.orders.id == order_id)
        .with_for_update(skip_locked=True)  # ✅ Атомарная блокировка
        .limit(1)
    )
    row = order_snapshot.first()
    
    # Если заказ уже заблокирован другим мастером - skip_locked вернёт None
    if row is None:
        _log.info(
            "offer_accept: order=%s either not found or already locked by another master",
            order_id
        )
        await safe_answer_callback(callback, ALERT_ALREADY_TAKEN, show_alert=True)
        await _render_offers(callback, session, master, page=page)
        return

    current_status: m.OrderStatus = row.status
    assigned_master_id = row.assigned_master_id
    current_version = row.version or 1
    _log.info("offer_accept: order=%s status=%s assigned_master=%s", 
             order_id, current_status, assigned_master_id)

    # ✅ FIX 1.2: Разрешаем принятие DEFERRED заказов
    # Если заказ в DEFERRED, разрешаем принять и автоматически переводим в ASSIGNED
    allowed_statuses = {
        m.OrderStatus.SEARCHING,
        m.OrderStatus.GUARANTEE,
        m.OrderStatus.CREATED,
        m.OrderStatus.DEFERRED,  # ✅ Теперь мастер может принять заказ в DEFERRED
    }

    if assigned_master_id is not None or current_status not in allowed_statuses:
        _log.info("offer_accept: order=%s ALREADY TAKEN or wrong status, rejecting", order_id)
        await safe_answer_callback(callback, ALERT_ALREADY_TAKEN, show_alert=True)
        await _render_offers(callback, session, master, page=page)
        return
    
    # Логируем если принимаем DEFERRED заказ
    if current_status == m.OrderStatus.DEFERRED:
        _log.info(
            "offer_accept: accepting DEFERRED order=%s by master=%s, will auto-resume",
            order_id, master.id
        )

    _log.info("offer_accept: checking offer for order=%s master=%s", order_id, master.id)
    # ✅ BUGFIX: Проверяем что оффер существует и не истёк
    # ВАЖНО: Берём самый свежий оффер (ORDER BY id DESC)
    offer_check = await session.execute(
        select(m.offers.state, m.offers.expires_at)
        .where(
            and_(
                m.offers.order_id == order_id,
                m.offers.master_id == master.id
            )
        )
        .order_by(m.offers.id.desc())  # ✅ Берём самый свежий оффер
        .limit(1)
    )
    offer_row = offer_check.first()
    
    if offer_row is None:
        _log.warning("offer_accept: no offer found for order=%s master=%s", order_id, master.id)
        await safe_answer_callback(callback, "⚠️ Оффер не найден", show_alert=True)
        await _render_offers(callback, session, master, page=page)
        return
    
    offer_state, expires_at = offer_row
    _log.info("offer_accept: offer state=%s expires_at=%s", offer_state, expires_at)
    
    # Проверяем что оффер в статусе SENT или VIEWED
    if offer_state not in (m.OfferState.SENT, m.OfferState.VIEWED):
        if offer_state == m.OfferState.EXPIRED:
            _log.info("offer_accept: offer expired for order=%s master=%s", order_id, master.id)
            await safe_answer_callback(callback, "⏰ Время истекло. Заказ ушёл другим мастерам.", show_alert=True)
        elif offer_state == m.OfferState.DECLINED:
            _log.info("offer_accept: offer already declined for order=%s master=%s", order_id, master.id)
            await safe_answer_callback(callback, "❌ Вы уже отклонили этот заказ", show_alert=True)
        else:
            _log.info("offer_accept: offer in wrong state=%s for order=%s master=%s", offer_state, order_id, master.id)
            await safe_answer_callback(callback, ALERT_ALREADY_TAKEN, show_alert=True)
        await _render_offers(callback, session, master, page=page)
        return
    
    # Проверяем что оффер не истёк по времени
    now_utc = datetime.now(timezone.utc)
    _log.info(
        "offer_accept: time check: now_utc=%s expires_at=%s is_expired=%s",
        now_utc.isoformat(),
        expires_at.isoformat() if expires_at else None,
        (expires_at < now_utc) if expires_at else False
    )
    if expires_at and expires_at < now_utc:
        _log.info("offer_accept: offer expired by time for order=%s master=%s (expires_at=%s)", 
                 order_id, master.id, expires_at.isoformat())
        await safe_answer_callback(callback, "⏰ Время истекло. Заказ ушёл другим мастерам.", show_alert=True)
        await _render_offers(callback, session, master, page=page)
        return

    _log.info("offer_accept: starting UPDATE orders for order=%s master=%s", order_id, master.id)
    updated = await session.execute(
        update(m.orders)
        .where(
            and_(
                m.orders.id == order_id,
                m.orders.assigned_master_id.is_(None),
                m.orders.status == current_status,
                m.orders.version == current_version,
            )
        )
        .values(
            assigned_master_id=master.id,
            status=m.OrderStatus.ASSIGNED,
            updated_at=func.now(),
            version=current_version + 1,
        )
        .returning(m.orders.id)
    )
    _log.info("offer_accept: UPDATE orders completed for order=%s, checking result...", order_id)
    
    if not updated.first():
        _log.warning("offer_accept: UPDATE orders returned 0 rows for order=%s (already taken or status changed)", order_id)
        await safe_answer_callback(callback, ALERT_ALREADY_TAKEN, show_alert=True)
        await _render_offers(callback, session, master, page=page)
        return

    _log.info("offer_accept: UPDATE orders SUCCESS for order=%s, starting UPDATE offers...", order_id)
    # Обновляем только активный оффер мастера (SENT/VIEWED → ACCEPTED)
    # ВАЖНО: Добавляем проверку expires_at в WHERE чтобы избежать race condition с watchdog
    offer_update_result = await session.execute(
        update(m.offers)
        .where(
            and_(
                m.offers.order_id == order_id,
                m.offers.master_id == master.id,
                m.offers.state.in_((m.OfferState.SENT, m.OfferState.VIEWED)),
                # ✅ Атомарная проверка: оффер не должен быть истёкшим
                or_(
                    m.offers.expires_at.is_(None),
                    m.offers.expires_at > func.now()
                )
            )
        )
        .values(state=m.OfferState.ACCEPTED, responded_at=func.now())
        .returning(m.offers.id)
    )
    _log.info("offer_accept: UPDATE offers completed for order=%s master=%s, checking result...", order_id, master.id)
    
    # Если не удалось обновить - оффер истёк или уже обработан
    offer_first = offer_update_result.first()
    _log.info("offer_accept: UPDATE offers result for order=%s: %s", order_id, "SUCCESS" if offer_first else "FAILED")
    if not offer_first:
        _log.warning(
            "offer_accept: failed to update offer to ACCEPTED for order=%s master=%s (likely expired or changed state)",
            order_id, master.id
        )
        await safe_answer_callback(callback, "⏰ Время истекло. Заказ ушёл другим мастерам.", show_alert=True)
        # Откатываем изменения в orders
        await session.rollback()
        await _render_offers(callback, session, master, page=page)
        return
    
    _log.info("offer_accept: canceling other masters' offers for order=%s", order_id)
    # Отменяем офферы других мастеров
    await session.execute(
        update(m.offers)
        .where(
            and_(
                m.offers.order_id == order_id,
                m.offers.master_id != master.id,
                m.offers.state.in_((m.OfferState.SENT, m.OfferState.VIEWED)),
            )
        )
        .values(state=m.OfferState.CANCELED, responded_at=func.now())
    )
    _log.info("offer_accept: other masters' offers canceled for order=%s, inserting status history", order_id)
    
    try:
        await session.execute(
            insert(m.order_status_history).values(
                order_id=order_id,
                from_status=current_status,
                to_status=m.OrderStatus.ASSIGNED,
                changed_by_master_id=master.id,
                reason="accepted_by_master",
                actor_type=m.ActorType.MASTER,
                context={
                    "master_id": master.id,
                    "master_name": master.full_name or "",
                    "action": "offer_accepted",
                    "method": "manual_accept"
                }
            )
        )
        _log.info("offer_accept: status history inserted successfully for order=%s", order_id)
    except Exception as history_err:
        _log.exception("offer_accept: FAILED to insert status history for order=%s: %s", order_id, history_err)
        await session.rollback()
        await safe_answer_callback(callback, "❌ Ошибка при принятии заказа", show_alert=True)
        await _render_offers(callback, session, master, page=page)
        return
    
    # ✅ STEP 4.1: Запись метрик распределения (ДО commit, но ошибки игнорируются)
    _log.info("offer_accept: starting distribution_metrics recording for order=%s", order_id)
    try:
        _log.info("offer_accept: fetching order info for metrics, order=%s", order_id)
        # Получаем полную информацию о заказе для метрик
        order_info = await session.execute(
            select(
                m.orders.city_id,
                m.orders.district_id,
                m.orders.category,
                m.orders.type,
                m.orders.preferred_master_id,
                m.orders.dist_escalated_logist_at,
                m.orders.dist_escalated_admin_at,
                m.orders.created_at,
            ).where(m.orders.id == order_id)
        )
        order_row = order_info.first()
        _log.info("offer_accept: order info fetched, fetching offer stats for order=%s", order_id)
        # Получаем раунд и количество кандидатов из offers
        offer_stats = await session.execute(
            select(
                func.max(m.offers.round_number).label("max_round"),
                func.count(func.distinct(m.offers.master_id)).label("total_candidates")
            ).where(m.offers.order_id == order_id)
        )
        stats_row = offer_stats.first()
        _log.info("offer_accept: offer stats fetched for order=%s, order_row=%s stats_row=%s", 
                 order_id, order_row is not None, stats_row is not None)
        
        if order_row and stats_row:
            now_utc = datetime.now(timezone.utc)
            time_to_assign = int((now_utc - order_row.created_at).total_seconds()) if order_row.created_at else None
            
            _log.info("offer_accept: inserting distribution_metrics for order=%s", order_id)
            await session.execute(
                insert(m.distribution_metrics).values(
                    order_id=order_id,
                    master_id=master.id,
                    round_number=stats_row.max_round or 1,
                    candidates_count=stats_row.total_candidates or 1,
                    time_to_assign_seconds=time_to_assign,
                    preferred_master_used=(master.id == order_row.preferred_master_id),
                    was_escalated_to_logist=(order_row.dist_escalated_logist_at is not None),
                    was_escalated_to_admin=(order_row.dist_escalated_admin_at is not None),
                    city_id=order_row.city_id,
                    district_id=order_row.district_id,
                    # ✅ BUGFIX: Конвертируем Enum в строку для VARCHAR колонок
                    category=order_row.category.value if hasattr(order_row.category, 'value') else str(order_row.category),
                    order_type=order_row.type.value if hasattr(order_row.type, 'value') else str(order_row.type),
                    metadata_json={
                        "accepted_via": "master_bot",
                        "from_status": current_status.value if hasattr(current_status, 'value') else str(current_status),
                    }
                )
            )
            _log.info(
                "distribution_metrics recorded: order=%s master=%s round=%s candidates=%s time=%ss",
                order_id, master.id, stats_row.max_round, stats_row.total_candidates, time_to_assign
            )
    except Exception as metrics_err:
        # Метрики не должны ломать основной процесс - просто логируем ошибку
        _log.error("Failed to record distribution_metrics for order=%s: %s", order_id, metrics_err)
        # НЕ делаем rollback - метрики опциональны, основные данные должны сохраниться
    
    # ✅ CRITICAL: Commit всех изменений (orders, offers, history, metrics)
    _log.info("offer_accept: committing transaction for order=%s", order_id)
    await session.commit()
    _log.info("offer_accept: transaction committed successfully for order=%s", order_id)
    
    # ✅ BUGFIX: Сбрасываем кэш SQLAlchemy после commit
    # Без этого _render_offers будет читать устаревшие данные из кэша
    session.expire_all()
    _log.info("offer_accept: session cache expired for order=%s", order_id)

    await safe_answer_callback(callback, ALERT_ACCEPT_SUCCESS, show_alert=True)
    # Переход к карточке принятого заказа вместо списка предложений
    await _render_active_order(callback, session, master, order_id=order_id)


# P0-1: Промежуточный шаг - показываем диалог подтверждения
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
        await safe_answer_callback(callback, ALERT_ORDER_NOT_FOUND, show_alert=True)
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
        await safe_answer_callback(callback, ALERT_ORDER_NOT_FOUND, show_alert=True)
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
    await safe_answer_callback(callback, ALERT_DECLINE_SUCCESS, show_alert=True)
    
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
        await safe_answer_callback(callback, ALERT_EN_ROUTE_FAIL, show_alert=True)
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
        await safe_answer_callback(callback, ALERT_WORKING_FAIL, show_alert=True)
        return
    await safe_answer_callback(callback, ALERT_WORKING_SUCCESS)
    await _render_active_order(callback, session, master, order_id=order_id)


async def _send_close_prompt(bot: Bot | None, master: m.masters, callback: CallbackQuery, text: str, reply_markup: InlineKeyboardMarkup | None = None) -> None:
    """Send the next-step prompt reliably regardless of callback message availability.

    In some environments callback.message may be present but lack a bound bot instance,
    which makes Message.answer() a no-op or raises. To be robust, always resolve the
    target chat id and use safe_send_message with an explicit bot instance.
    """
    # First try the simplest path: answer directly to the source message if possible.
    try:
        if getattr(callback, "message", None) is not None:
            await callback.message.answer(text, reply_markup=reply_markup)
            return
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
        return

    # Resolve bot instance: prefer injected bot, then callback.bot, then message.bot
    bot_instance = bot or getattr(callback, "bot", None)
    if bot_instance is None and getattr(callback, "message", None) is not None:
        bot_instance = getattr(callback.message, "bot", None)
    if bot_instance is None:
        _log.warning(
            "_send_close_prompt: no bot instance for callback id=%s",
            getattr(callback, "id", None),
        )
        return

    await safe_send_message(bot_instance, target_id, text, reply_markup=reply_markup)


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
        await safe_answer_callback(callback, "Ошибка загрузки заказа", show_alert=True)
        return
    if order is None or order.assigned_master_id != master.id:
        _log.warning("active_close_start: order not found or not assigned to master")
        await safe_answer_callback(callback, ALERT_ORDER_NOT_FOUND, show_alert=True)
        return
    if order.status != m.OrderStatus.WORKING:
        _log.warning(
            "active_close_start: order status not WORKING, current=%s, sending alert",
            order.status,
        )
        await safe_answer_callback(callback, ALERT_CLOSE_NOT_ALLOWED, show_alert=True)
        return

    await state.update_data(close_order_id=order_id, close_order_amount=None)

    bot_instance = bot or getattr(callback, "bot", None)
    if bot_instance is None and callback.message is not None:
        bot_instance = callback.message.bot

    if order.type == m.OrderType.GUARANTEE:  # FIX: use .type not .order_type
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

    await _send_close_prompt(bot_instance, master, callback, prompt_text, reply_markup=close_order_cancel_keyboard())
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
    if amount is None:
        await message.answer(CLOSE_AMOUNT_ERROR, reply_markup=close_order_cancel_keyboard())
        return
    _log.info("active_close_amount: uid=%s amount=%s", getattr(getattr(message, "from_user", None), "id", None), amount)
    await state.update_data(close_order_amount=str(amount))
    await state.set_state(CloseOrderStates.act)
    await message.answer(CLOSE_ACT_PROMPT, reply_markup=close_order_cancel_keyboard())


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
        await state.clear()
        return
    if order.status != m.OrderStatus.WORKING:
        await message.answer(ALERT_CLOSE_STATUS)
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

    is_guarantee = order.type == m.OrderType.GUARANTEE  # FIX: use .type not .order_type
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
    await state.clear()

    # Возврат в главное меню с информативным сообщением
    from ..keyboards import main_menu_keyboard
    
    if is_guarantee:
        text = CLOSE_GUARANTEE_SUCCESS.format(order_id=order_id)
    else:
        text = CLOSE_NEXT_STEPS.format(order_id=order_id, amount=amount)
    
    await message.answer(text, reply_markup=main_menu_keyboard(master))


@router.message(CloseOrderStates.act)
async def active_close_act_invalid(message: Message) -> None:
    await message.answer(CLOSE_DOCUMENT_ERROR, reply_markup=close_order_cancel_keyboard())


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
                _nav_row("m:menu"),
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
                InlineKeyboardButton(text="◀️", callback_data=f"m:new:{page - 1}")
            )
        if page < pages:
            nav_row.append(
                InlineKeyboardButton(text="▶️", callback_data=f"m:new:{page + 1}")
            )
        if nav_row:
            keyboard_rows.append(nav_row)

    keyboard_rows.append(_nav_row("m:menu"))

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
    if order_id is None:
        # Показываем список всех активных заказов
        active_orders = await _load_active_orders(session, master.id)
        
        if not active_orders:
            await safe_edit_or_send(
                event,
                NO_ACTIVE_ORDERS,
                inline_keyboard([
                    _nav_row("m:menu")
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
        
        keyboard_rows.append(_nav_row("m:menu"))
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
    row = await _load_active_order(session, master.id, order_id)
    if row is None:
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
    
    try:
        await safe_edit_or_send(event, text, keyboard)
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
        await safe_answer_callback(callback, "Ошибка формата", show_alert=True)
        return
    
    data_type = parts[2]
    try:
        order_id = int(parts[3])
    except ValueError:
        await safe_answer_callback(callback, "Неверный ID заказа", show_alert=True)
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
        await safe_answer_callback(callback, "Заказ не найден", show_alert=True)
        return
    
    # Формируем данные для копирования
    if data_type == "cph":
        if not row.client_phone:
            await safe_answer_callback(callback, "Телефон не указан", show_alert=True)
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
        await safe_answer_callback(callback, "Неизвестный тип данных", show_alert=True)
        return
    
    # Отправляем данные через alert для быстрого копирования
    message_text = format_copy_message(data_type, data)
    await safe_answer_callback(callback, data, show_alert=True)
    
    _log.info(
        "copy_data: uid=%s order_id=%s type=%s",
        _callback_uid(callback),
        order_id,
        data_type,
    )
