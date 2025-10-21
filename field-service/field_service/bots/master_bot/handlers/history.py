"""   (P1-9)."""
from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Optional

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

# P1-23: Breadcrumbs navigation
from field_service.bots.common import MasterPaths, add_breadcrumbs_to_text, safe_answer_callback, safe_edit_or_send
from field_service.db import models as m
from field_service.services import time_service
from field_service.config import settings

from ..texts import (
    HISTORY_EMPTY,
    HISTORY_HEADER_TEMPLATE,
    HISTORY_STATS_TEMPLATE,
    ORDER_STATUS_TITLES,
    history_order_line,
    history_order_card,
)
from ..utils import escape_html, inline_keyboard

router = Router(name="master_history")
_log = logging.getLogger("master_bot.history")

HISTORY_PAGE_SIZE = 10
HISTORY_STATUSES = (m.OrderStatus.CLOSED, m.OrderStatus.CANCELED)


def _callback_uid(callback: CallbackQuery) -> int | None:
    return getattr(getattr(callback, "from_user", None), "id", None)


def _timeslot_text(
    start_utc: datetime | None,
    end_utc: datetime | None,
    tz_value: str | None = None,
) -> Optional[str]:
    tz = time_service.resolve_timezone(tz_value or settings.timezone)
    return time_service.format_timeslot_local(start_utc, end_utc, tz=tz)


@router.callback_query(F.data == "m:hist")
async def history_root(
    callback: CallbackQuery,
    session: AsyncSession,
    master: m.masters,
    state: FSMContext,
) -> None:
    """   ( )."""
    await state.clear()
    _log.info("history_root: master_id=%s", master.id)
    await _render_history(callback, session, master, page=1, filter_status=None)
    await safe_answer_callback(callback)


@router.callback_query(F.data.regexp(r"^m:hist:(\d+)(?::(\w+))?$"))
async def history_page(
    callback: CallbackQuery,
    session: AsyncSession,
    master: m.masters,
) -> None:
    """     ."""
    parts = callback.data.split(":")
    page = int(parts[2])
    filter_status = parts[3] if len(parts) > 3 else None
    
    _log.info("history_page: master_id=%s, page=%s, filter=%s", master.id, page, filter_status)
    await _render_history(callback, session, master, page=page, filter_status=filter_status)
    await safe_answer_callback(callback)


@router.callback_query(F.data.regexp(r"^m:hist:card:(\d+)(?::(\d+))?(?::(\w+))?$"))
async def history_card(
    callback: CallbackQuery,
    session: AsyncSession,
    master: m.masters,
) -> None:
    """   ."""
    parts = callback.data.split(":")
    order_id = int(parts[3])
    page = int(parts[4]) if len(parts) > 4 else 1
    filter_status = parts[5] if len(parts) > 5 else None
    
    _log.info("history_card: master_id=%s, order_id=%s", master.id, order_id)
    
    stmt = (
        select(m.orders)
        .where(
            and_(
                m.orders.master_id == master.id,
                m.orders.id == order_id,
                m.orders.status.in_(HISTORY_STATUSES),
            )
        )
    )
    result = await session.execute(stmt)
    order = result.scalar_one_or_none()
    
    if not order:
        await safe_answer_callback(callback, "   ", show_alert=True)
        await _render_history(callback, session, master, page=page, filter_status=filter_status)
        return
    
    await session.refresh(order, ["city", "district", "category"])
    
    text_without_breadcrumbs = history_order_card(
        order_id=order.id,
        status=ORDER_STATUS_TITLES.get(order.status, order.status),
        city=order.city.name if order.city else "",
        district=order.district.name if order.district else None,
        street=order.street_address,
        house=order.house_number,
        apartment=order.apartment_number,
        address_comment=order.address_comment,
        category=order.category.label if order.category else "",
        description=order.description,
        timeslot=_timeslot_text(order.timeslot_start, order.timeslot_end),
        client_name=order.client_name,
        client_phone=order.client_phone,
        final_amount=order.final_amount,
        created_at=order.created_at,
        closed_at=order.updated_at if order.status == m.OrderStatus.CLOSED else None,
    )
    
    # P1-23: Add breadcrumbs navigation
    breadcrumb_path = MasterPaths.history_order_card(order.id)
    text = add_breadcrumbs_to_text(text_without_breadcrumbs, breadcrumb_path)
    
    back_callback = f"m:hist:{page}"
    if filter_status:
        back_callback += f":{filter_status}"
    
    keyboard = inline_keyboard([
        InlineKeyboardButton(text="Назад к истории", callback_data=back_callback),
        InlineKeyboardButton(text="Главное меню", callback_data="m:menu")
    ])
    
    await safe_edit_or_send(callback, text, keyboard)
    await safe_answer_callback(callback)


async def _render_history(
    callback: CallbackQuery,
    session: AsyncSession,
    master: m.masters,
    page: int,
    filter_status: str | None,
) -> None:
    """       ."""
    _log.info("_render_history: master_id=%s, page=%s, filter=%s", master.id, page, filter_status)

    if filter_status == "closed":
        statuses = (m.OrderStatus.CLOSED,)
    elif filter_status == "canceled":
        statuses = (m.OrderStatus.CANCELED,)
    else:
        statuses = HISTORY_STATUSES

    count_stmt = (
        select(func.count(m.orders.id))
        .where(
            and_(
                m.orders.master_id == master.id,
                m.orders.status.in_(statuses),
            )
        )
    )
    count_result = await session.execute(count_stmt)
    total = count_result.scalar() or 0
    _log.info("_render_history: found %s orders", total)

    _log.info("_render_history: checking if total == 0")
    if total == 0:
        text = HISTORY_EMPTY
        keyboard = inline_keyboard([
            InlineKeyboardButton(text="Главное меню", callback_data="m:menu")
        ])
        await safe_edit_or_send(callback, text, keyboard)
        return
    
    total_pages = math.ceil(total / HISTORY_PAGE_SIZE)
    page = max(1, min(page, total_pages))
    offset = (page - 1) * HISTORY_PAGE_SIZE

    _log.info("_render_history: calculated pagination - total_pages=%s, page=%s, offset=%s", total_pages, page, offset)

    orders_stmt = (
        select(m.orders)
        .where(
            and_(
                m.orders.master_id == master.id,
                m.orders.status.in_(statuses),
            )
        )
        .order_by(m.orders.updated_at.desc())
        .offset(offset)
        .limit(HISTORY_PAGE_SIZE)
    )
    orders_result = await session.execute(orders_stmt)
    orders = orders_result.scalars().all()

    _log.info("_render_history: loaded %s orders from database", len(orders))

    stats_stmt = select(
        func.count(m.orders.id).label("total_completed"),
        func.sum(m.orders.final_amount).label("total_earned"),
    ).where(
        and_(
            m.orders.master_id == master.id,
            m.orders.status == m.OrderStatus.CLOSED,
        )
    )
    stats_result = await session.execute(stats_stmt)
    stats = stats_result.one()

    _log.info("_render_history: loaded stats - completed=%s, earned=%s", stats.total_completed, stats.total_earned)

    header = HISTORY_HEADER_TEMPLATE.format(
        page=page,
        pages=total_pages,
        total=total,
    )
    
    stats_text = HISTORY_STATS_TEMPLATE.format(
        total_completed=stats.total_completed or 0,
        total_earned=float(stats.total_earned or 0),
        avg_rating="",  # TODO:   
    )
    
    lines = [header, "", stats_text, ""]
    for order in orders:
        await session.refresh(order, ["city", "district", "category"])
        line = history_order_line(
            order_id=order.id,
            status=ORDER_STATUS_TITLES.get(order.status, order.status),
            city=order.city.name if order.city else "",
            district=order.district.name if order.district else None,
            category=order.category.label if order.category else "",
            timeslot=_timeslot_text(order.timeslot_start, order.timeslot_end),
        )
        lines.append(line)

    text = "\n".join(lines)

    _log.info("_render_history: formatted text, total lines=%s", len(lines))

    rows: list[list[InlineKeyboardButton]] = []
    
    for order in orders:
        callback_data = f"m:hist:card:{order.id}:{page}"
        if filter_status:
            callback_data += f":{filter_status}"
        rows.append([
            InlineKeyboardButton(
                text=f"#{order.id}  {ORDER_STATUS_TITLES.get(order.status, order.status)}",
                callback_data=callback_data,
            )
        ])
    
    filter_row: list[InlineKeyboardButton] = []
    if filter_status != "closed":
        filter_row.append(
            InlineKeyboardButton(
                text="✅ Закрытые",
                callback_data=f"m:hist:1:closed",
            )
        )
    if filter_status != "canceled":
        filter_row.append(
            InlineKeyboardButton(
                text="❌ Отменённые",
                callback_data=f"m:hist:1:canceled",
            )
        )
    if filter_status is not None:
        filter_row.append(
            InlineKeyboardButton(
                text="🔄 Все",
                callback_data="m:hist:1",
            )
        )
    if filter_row:
        rows.append(filter_row)
    
    if total_pages > 1:
        nav_row: list[InlineKeyboardButton] = []
        if page > 1:
            prev_callback = f"m:hist:{page - 1}"
            if filter_status:
                prev_callback += f":{filter_status}"
            nav_row.append(
                InlineKeyboardButton(text="◀️ Назад", callback_data=prev_callback)
            )
        nav_row.append(
            InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="m:hist:noop")
        )
        if page < total_pages:
            next_callback = f"m:hist:{page + 1}"
            if filter_status:
                next_callback += f":{filter_status}"
            nav_row.append(
                InlineKeyboardButton(text="Вперёд ▶️", callback_data=next_callback)
            )
        rows.append(nav_row)
    
    #  " "
    rows.append([
        InlineKeyboardButton(text="Главное меню", callback_data="m:menu")
    ])
    
    keyboard = inline_keyboard(rows)

    _log.info("_render_history: built keyboard with %s rows", len(rows))

    # P1-23: Add breadcrumbs navigation
    _log.info("_render_history: adding breadcrumbs to text")
    text_with_breadcrumbs = add_breadcrumbs_to_text(text, MasterPaths.HISTORY)
    _log.info("_render_history: breadcrumbs added, final text length=%s", len(text_with_breadcrumbs))

    _log.info("_render_history: sending message, text length=%s, keyboard rows=%s", len(text_with_breadcrumbs), len(keyboard.inline_keyboard) if keyboard else 0)
    await safe_edit_or_send(callback, text_with_breadcrumbs, keyboard)
    _log.info("_render_history: message sent")
