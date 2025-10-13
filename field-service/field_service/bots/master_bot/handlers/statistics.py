"""P1-17: Статистика мастера.

Показывает мастеру его достижения и метрики:
- Всего выполнено заказов
- Средняя оценка
- Среднее время отклика
- Заказов за текущий месяц
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

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

from ..utils import clear_step_messages, escape_html, inline_keyboard

router = Router(name="master_statistics")


@router.callback_query(F.data == "m:stats")
async def handle_statistics(
    callback: CallbackQuery,
    state: FSMContext,
    master: m.masters,
    session: AsyncSession,
) -> None:
    """Показать статистику мастера."""
    message = callback.message
    bot_instance = getattr(message, "bot", None) or getattr(callback, "bot", None)
    chat = getattr(message, "chat", None)
    chat_id = getattr(chat, "id", None)
    if chat_id is None and getattr(callback, "from_user", None) is not None:
        chat_id = getattr(callback.from_user, "id", None)
    if bot_instance and chat_id is not None:
        await clear_step_messages(bot_instance, state, chat_id)
    await state.clear()

    # 1. Всего выполнено заказов (CLOSED)
    completed_query = select(func.count(m.orders.id)).where(
        and_(
            m.orders.assigned_master_id == master.id,
            m.orders.status == m.OrderStatus.CLOSED,
        )
    )
    completed_result = await session.execute(completed_query)
    completed_count = completed_result.scalar() or 0

    # 2. Средняя оценка (из masters.rating)
    avg_rating = float(master.rating) if master.rating else 5.0

    # 3. Среднее время отклика (в минутах)
    # Вычисляем EXTRACT(EPOCH FROM (responded_at - sent_at))/60 для ACCEPTED офферов
    response_time_query = select(
        func.avg(
            func.extract(
                "EPOCH",
                m.offers.responded_at - m.offers.sent_at
            ) / 60
        )
    ).where(
        and_(
            m.offers.master_id == master.id,
            m.offers.state == m.OfferState.ACCEPTED,
            m.offers.responded_at.isnot(None),
        )
    )
    response_time_result = await session.execute(response_time_query)
    avg_response_minutes = response_time_result.scalar()
    
    # Форматируем время отклика
    if avg_response_minutes is not None:
        avg_response_minutes = float(avg_response_minutes)
        if avg_response_minutes < 60:
            response_time_str = f"{avg_response_minutes:.0f} мин"
        else:
            hours = avg_response_minutes / 60
            response_time_str = f"{hours:.1f} ч"
    else:
        response_time_str = "—"

    # 4. Заказов за текущий месяц
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
    month_count = month_result.scalar() or 0

    # Формируем текст карточки
    lines = [
        "<b>📊 Моя статистика</b>",
        "",
        f"✅ <b>Заказов выполнено:</b> {completed_count}",
        f"⭐ <b>Средняя оценка:</b> {avg_rating:.1f}",
        f"⚡ <b>Время отклика:</b> {response_time_str}",
        f"📅 <b>Завершено за месяц:</b> {month_count}",
        "",
    ]
    
    # Добавляем мотивирующее сообщение в зависимости от показателей
    if completed_count == 0:
        lines.append("🚀 Начните принимать заказы, чтобы увидеть свой прогресс!")
    elif completed_count < 10:
        lines.append(f"💪 Отличное начало! До 10 заказов осталось {10 - completed_count}")
    elif completed_count < 50:
        lines.append(f"🔥 Так держать! До 50 заказов осталось {50 - completed_count}")
    elif completed_count < 100:
        lines.append(f"⭐ Вы на пути к сотне! Осталось {100 - completed_count}")
    else:
        lines.append("🏆 Вы профессионал! Продолжайте в том же духе!")

    text = "\n".join(lines)
    text = add_breadcrumbs_to_text(text, MasterPaths.STATISTICS)

    keyboard = inline_keyboard([
        [InlineKeyboardButton(text="🏠 Меню", callback_data="m:menu")]
    ])

    if callback.message:
        await safe_edit_or_send(callback.message, text, keyboard)
    await safe_answer_callback(callback)
