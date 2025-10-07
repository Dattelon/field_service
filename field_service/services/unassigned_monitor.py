from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from sqlalchemy import and_, func, select

from field_service.db import models as m
from field_service.db.session import SessionLocal
from field_service.services.push_notifications import notify_logist, NotificationEvent

UTC = timezone.utc
logger = logging.getLogger(__name__)


async def monitor_unassigned_orders(
    bot: Bot,
    alerts_chat_id: int,
    *,
    interval_seconds: int = 600,
) -> None:
    """Poll orders and alert logist chat about unassigned backlog."""
    sleep_for = max(60, int(interval_seconds))
    while True:
        try:
            if bot is None or not alerts_chat_id:
                await asyncio.sleep(sleep_for)
                continue

            threshold = datetime.now(UTC) - timedelta(minutes=10)

            async with SessionLocal() as session:
                count = await session.scalar(
                    select(func.count())
                    .select_from(m.orders)
                    .where(
                        and_(
                            m.orders.status == m.OrderStatus.SEARCHING,
                            m.orders.created_at < threshold,
                        )
                    )
                )

                total = int(count or 0)
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
