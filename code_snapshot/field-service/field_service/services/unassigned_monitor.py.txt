from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Optional

from aiogram import Bot
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from field_service.db import models as m
from field_service.db.session import SessionLocal
from field_service.services.push_notifications import notify_logist, NotificationEvent

UTC = timezone.utc
logger = logging.getLogger(__name__)


@asynccontextmanager
async def _maybe_session(session: Optional[AsyncSession]):
    """Context manager для работы с опциональной сессией."""
    if session is not None:
        # Используем переданную сессию, не закрываем её
        yield session
        return
    # Создаём временную сессию через SessionLocal
    async with SessionLocal() as s:
        yield s


async def scan_and_notify(*, session: Optional[AsyncSession] = None) -> int:
    """Сканирует неназначенные заказы и возвращает их количество.
    
    Args:
        session: Опциональная тестовая сессия
        
    Returns:
        Количество неназначенных заказов старше 10 минут
    """
    threshold = datetime.now(UTC) - timedelta(minutes=10)

    async with _maybe_session(session) as s:
        count = await s.scalar(
            select(func.count())
            .select_from(m.orders)
            .where(
                and_(
                    m.orders.status == m.OrderStatus.SEARCHING,
                    m.orders.created_at < threshold,
                )
            )
        )
        return int(count or 0)


async def monitor_unassigned_orders(
    bot: Bot,
    alerts_chat_id: int,
    *,
    interval_seconds: int = 600,
    session: Optional[AsyncSession] = None,
) -> None:
    """Poll orders and alert logist chat about unassigned backlog.
    
    Args:
        bot: Bot instance for sending notifications
        alerts_chat_id: Chat ID for logist alerts
        interval_seconds: Check interval in seconds
        session: Optional test session (default: create own)
    """
    sleep_for = max(60, int(interval_seconds))
    while True:
        try:
            if bot is None or not alerts_chat_id:
                await asyncio.sleep(sleep_for)
                continue

            total = await scan_and_notify(session=session)
            
            if total > 0:
                await notify_logist(
                    bot,
                    alerts_chat_id,
                    event=NotificationEvent.UNASSIGNED_ORDERS,
                    count=total,
                )
        except Exception as exc:
            logger.exception("Unassigned monitor error: %s", exc)
        await asyncio.sleep(sleep_for)
