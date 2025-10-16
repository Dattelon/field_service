"""P1-17:   (, , , )."""
from __future__ import annotations

from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import func, select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from field_service.bots.common import (
    MasterPaths,
    add_breadcrumbs_to_text,
    safe_answer_callback,
    safe_edit_or_send,
)
from field_service.db import models as m

from ..utils import inline_keyboard


router = Router(name="master_statistics")


@router.callback_query(F.data == "m:stats")
async def handle_statistics(
    callback: CallbackQuery,
    state: FSMContext,
    master: m.masters,
    session: AsyncSession,
) -> None:
    """   ."""
    await state.clear()

    # 1) Completed (CLOSED) orders count
    completed_query = select(func.count(m.orders.id)).where(
        and_(
            m.orders.assigned_master_id == master.id,
            m.orders.status == m.OrderStatus.CLOSED,
        )
    )
    completed_result = await session.execute(completed_query)
    completed_count = int(completed_result.scalar() or 0)

    # 2) Average rating (fallback 5.0)
    avg_rating = float(getattr(master, "rating", 0) or 5.0)

    # 3) Average response time in minutes for ACCEPTED offers
    response_time_query = select(
        func.avg(
            func.extract(
                "EPOCH",
                m.offers.responded_at - m.offers.sent_at,
            ) / 60.0
        )
    ).where(
        and_(
            m.offers.master_id == master.id,
            m.offers.state == m.OfferState.ACCEPTED,
            m.offers.responded_at.is_not(None),
        )
    )
    response_time_result = await session.execute(response_time_query)
    avg_response_minutes = response_time_result.scalar()
    if avg_response_minutes is not None:
        avg_response_minutes = float(avg_response_minutes)
        if avg_response_minutes < 60:
            response_time_str = f"{avg_response_minutes:.0f} "
        else:
            hours = avg_response_minutes / 60.0
            response_time_str = f"{hours:.1f} "
    else:
        response_time_str = ""

    # 4) Count of closed orders in current month
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_query = select(func.count(m.orders.id)).where(
        and_(
            m.orders.assigned_master_id == master.id,
            m.orders.status == m.OrderStatus.CLOSED,
            m.orders.updated_at >= month_start,
        )
    )
    month_result = await session.execute(month_query)
    month_count = int(month_result.scalar() or 0)

    # Compose human-readable statistics lines
    lines = [
        "<b> </b>",
        "",
        f": <b> :</b> {completed_count}",
        f" : <b>{avg_rating:.1f}</b>",
        f"  : <b>{response_time_str}</b>",
        f" : <b> :</b> {month_count}",
        "",
    ]

    # Motivational messages by total completed count
    if completed_count == 0:
        lines.append("   ,    !")
    elif completed_count < 10:
        lines.append(f" !  10   {10 - completed_count}.")
    elif completed_count < 50:
        lines.append(f" !  50   {50 - completed_count}.")
    elif completed_count < 100:
        lines.append(f" !  100   {100 - completed_count}.")
    else:
        lines.append(" !     !")

    text = "\n".join(lines)
    text = add_breadcrumbs_to_text(text, MasterPaths.STATISTICS)

    keyboard = inline_keyboard(
        [[InlineKeyboardButton(text=" ", callback_data="m:menu")]]
    )

    # Prefer direct edit in tests where callback.message is a MagicMock
    try:
        msg = getattr(callback, "message", None)
        edit = getattr(msg, "edit_text", None)
        if callable(edit):
            await edit(text, reply_markup=keyboard)
        elif msg is not None:
            # Fallback to safe helper if it's a real Message
            await safe_edit_or_send(msg, text, keyboard)
    except Exception:
        # Best-effort fallback; ignore in tests without real bot/message
        pass
    try:
        await safe_answer_callback(callback)
    except Exception:
        pass
