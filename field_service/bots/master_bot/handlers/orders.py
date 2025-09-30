from __future__ import annotations

import math
from datetime import datetime
from decimal import Decimal
from typing import Optional
from types import SimpleNamespace

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, ContentType, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import and_, func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from field_service.bots.common import safe_answer_callback, safe_edit_or_send
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
    CLOSE_PAYMENT_TEMPLATE,
    CLOSE_SUCCESS_TEMPLATE,
    BACK_TO_MENU,
    BACK_TO_OFFERS,
    OFFERS_EMPTY,
    OFFERS_HEADER_TEMPLATE,
    OFFERS_REFRESH_BUTTON,
    NO_ACTIVE_ORDERS,
    ORDER_STATUS_TITLES,
    ALERT_ACCEPT_SUCCESS,
    ALERT_ACCOUNT_BLOCKED,
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
    offer_card,
    offer_line,
    OFFER_NOT_FOUND,
)
from ..utils import escape_html, inline_keyboard, normalize_money, now_utc

router = Router(name="master_orders")

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
    parts = callback.data.split(":")
    order_id = int(parts[2])
    page = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 1
    await _render_offer_card(callback, session, master, order_id, page)
    await safe_answer_callback(callback)


@router.callback_query(F.data.regexp(r"^m:new:acc:(\d+)(?::(\d+))?$"))
async def offer_accept(
    callback: CallbackQuery,
    session: AsyncSession,
    master: m.masters,
) -> None:
    parts = callback.data.split(":")
    order_id = int(parts[2])
    page = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 1

    if master.is_blocked:
        await safe_answer_callback(callback, ALERT_ACCOUNT_BLOCKED, show_alert=True)
        return

    limit = await _get_active_limit(session, master)
    active_orders = await _count_active_orders(session, master.id)
    if limit and active_orders >= limit:
        await safe_answer_callback(callback, ALERT_LIMIT_REACHED, show_alert=True)
        return

    order_snapshot = await session.execute(
        select(m.orders.status, m.orders.assigned_master_id, m.orders.version)
        .where(m.orders.id == order_id)
        .limit(1)
    )
    row = order_snapshot.first()
    if row is None:
        await safe_answer_callback(callback, ALERT_ORDER_NOT_FOUND, show_alert=True)
        await _render_offers(callback, session, master, page=page)
        return

    current_status: m.OrderStatus = row.status
    assigned_master_id = row.assigned_master_id
    current_version = row.version or 1
    allowed_statuses = {
        m.OrderStatus.SEARCHING,
        m.OrderStatus.GUARANTEE,
        m.OrderStatus.CREATED,
    }

    if assigned_master_id is not None or current_status not in allowed_statuses:
        await safe_answer_callback(callback, ALERT_ALREADY_TAKEN, show_alert=True)
        await _render_offers(callback, session, master, page=page)
        return

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
    if not updated.first():
        await safe_answer_callback(callback, ALERT_ALREADY_TAKEN, show_alert=True)
        await _render_offers(callback, session, master, page=page)
        return

    await session.execute(
        update(m.offers)
        .where((m.offers.order_id == order_id) & (m.offers.master_id == master.id))
        .values(state=m.OfferState.ACCEPTED, responded_at=func.now())
    )
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
    await session.execute(
        insert(m.order_status_history).values(
            order_id=order_id,
            from_status=current_status,
            to_status=m.OrderStatus.ASSIGNED,
            changed_by_master_id=master.id,
            reason="accepted_by_master",
        )
    )
    await session.commit()

    await safe_answer_callback(callback, ALERT_ACCEPT_SUCCESS, show_alert=True)
    await _render_offers(callback, session, master, page=page)


@router.callback_query(F.data.regexp(r"^m:new:dec:(\d+)(?::(\d+))?$"))
async def offer_decline(
    callback: CallbackQuery,
    session: AsyncSession,
    master: m.masters,
) -> None:
    parts = callback.data.split(":")
    order_id = int(parts[2])
    page = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 1

    await session.execute(
        update(m.offers)
        .where((m.offers.order_id == order_id) & (m.offers.master_id == master.id))
        .values(state=m.OfferState.DECLINED, responded_at=func.now())
    )
    await session.commit()

    await safe_answer_callback(callback, ALERT_DECLINE_SUCCESS)
    await _render_offers(callback, session, master, page=page)


@router.callback_query(F.data == "m:act")
async def active_order_entry(
    callback: CallbackQuery,
    session: AsyncSession,
    master: m.masters,
) -> None:
    await _render_active_order(callback, session, master, order_id=None)
    await safe_answer_callback(callback)


@router.callback_query(F.data.regexp(r"^m:act:card:(\d+)$"))
async def active_order_card(
    callback: CallbackQuery,
    session: AsyncSession,
    master: m.masters,
) -> None:
    order_id = int(callback.data.split(":")[-1])
    await _render_active_order(callback, session, master, order_id=order_id)
    await safe_answer_callback(callback)


@router.callback_query(F.data.regexp(r"^m:act:enr:(\d+)$"))
async def active_set_enroute(
    callback: CallbackQuery,
    session: AsyncSession,
    master: m.masters,
) -> None:
    order_id = int(callback.data.split(":")[-1])
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


@router.callback_query(F.data.regexp(r"^m:act:cls:(\d+)$"))
async def active_close_start(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    master: m.masters,
) -> None:
    order_id = int(callback.data.split(":")[-1])
    order = await session.get(m.orders, order_id)
    if order is None or order.assigned_master_id != master.id:
        await safe_answer_callback(callback, ALERT_ORDER_NOT_FOUND, show_alert=True)
        return
    if order.status != m.OrderStatus.WORKING:
        await safe_answer_callback(callback, ALERT_CLOSE_NOT_ALLOWED, show_alert=True)
        return

    await state.update_data(close_order_id=order_id)
    if order.order_type == m.OrderType.GUARANTEE:
        await state.update_data(close_order_amount=str(Decimal("0")))
        await state.set_state(CloseOrderStates.act)
        await callback.message.answer(CLOSE_ACT_PROMPT)
    else:
        await state.set_state(CloseOrderStates.amount)
        await callback.message.answer(CLOSE_AMOUNT_PROMPT)
    await safe_answer_callback(callback)


@router.message(CloseOrderStates.amount)
async def active_close_amount(message: Message, state: FSMContext) -> None:
    amount = normalize_money(message.text or "")
    if amount is None:
        await message.answer(CLOSE_AMOUNT_ERROR)
        return
    await state.update_data(close_order_amount=str(amount))
    await state.set_state(CloseOrderStates.act)
    await message.answer(CLOSE_ACT_PROMPT)


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

    is_guarantee = order.order_type == m.OrderType.GUARANTEE
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
            )
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
            )
        )
        await CommissionService(session).create_for_order(order_id)

    await session.commit()
    await state.clear()

    if is_guarantee:
        await message.answer(CLOSE_SUCCESS_TEMPLATE.format(order_id=order_id))
    else:
        payment_text = CLOSE_PAYMENT_TEMPLATE.format(order_id=order_id, amount=amount)
        await message.answer(f"{payment_text}\n{CLOSE_DOCUMENT_RECEIVED}")
    await _render_active_order(message, session, master, order_id=order_id)


@router.message(CloseOrderStates.act)
async def active_close_act_invalid(message: Message) -> None:
    await message.answer(CLOSE_DOCUMENT_ERROR)


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
            [[InlineKeyboardButton(text=OFFERS_REFRESH_BUTTON, callback_data="m:new")]]
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

    keyboard = inline_keyboard(keyboard_rows)
    await safe_edit_or_send(event, "\n".join(lines), keyboard)


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
            inline_keyboard(
                [[InlineKeyboardButton(text=BACK_TO_OFFERS, callback_data="m:new")]]
            ),
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
            [InlineKeyboardButton(text=BACK_TO_OFFERS, callback_data="m:new")],
        ]
    )
    await safe_edit_or_send(event, card_text, keyboard)


async def _render_active_order(
    event: Message | CallbackQuery,
    session: AsyncSession,
    master: m.masters,
    order_id: int | None,
) -> None:
    row = await _load_active_order(session, master.id, order_id)
    if row is None:
        await safe_edit_or_send(
            event,
            NO_ACTIVE_ORDERS,
            inline_keyboard(
                [[InlineKeyboardButton(text=BACK_TO_MENU, callback_data="m:menu")]]
            ),
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

    keyboard_rows.append([InlineKeyboardButton(text=BACK_TO_MENU, callback_data="m:menu")])
    keyboard = inline_keyboard(keyboard_rows)

    await safe_edit_or_send(event, "\n".join(text_lines), keyboard)


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

