"""
P1-01: Service for automatic order closure after 24 hours
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, delete, func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from field_service.db import models as m
from field_service.db.session import SessionLocal
from field_service.services import live_log

UTC = timezone.utc
logger = logging.getLogger("autoclose")

# Задержка автозакрытия (24 часа)
AUTOCLOSE_DELAY_HOURS = 24


async def enqueue_order_for_autoclose(
    session: AsyncSession,
    order_id: int,
    closed_at: datetime,
) -> None:
    """
    Добавить заказ в очередь автозакрытия.
    
    Вызывается при переходе order.status → CLOSED.
    """
    autoclose_at = closed_at + timedelta(hours=AUTOCLOSE_DELAY_HOURS)
    
    # Проверяем, не добавлен ли уже
    exists = await session.scalar(
        select(1)
        .select_from(m.order_autoclose_queue)
        .where(m.order_autoclose_queue.order_id == order_id)
        .limit(1)
    )
    
    if exists:
        # Обновляем время
        await session.execute(
            update(m.order_autoclose_queue)
            .where(m.order_autoclose_queue.order_id == order_id)
            .values(
                closed_at=closed_at,
                autoclose_at=autoclose_at,
                processed_at=None,
            )
        )
    else:
        # Добавляем новую запись
        await session.execute(
            insert(m.order_autoclose_queue).values(
                order_id=order_id,
                closed_at=closed_at,
                autoclose_at=autoclose_at,
            )
        )
    
    live_log.push("autoclose", f"order#{order_id} enqueued for autoclose at {autoclose_at}")


async def process_autoclose_queue(
    session_factory=SessionLocal,
    *,
    now: datetime | None = None,
) -> int:
    """
    Обработать очередь автозакрытия.
    
    Returns:
        Количество обработанных заказов
    """
    if now is None:
        now = datetime.now(UTC)
    
    async with session_factory() as session:
        # Находим заказы готовые к автозакрытию
        stmt = (
            select(
                m.order_autoclose_queue.order_id,
                m.order_autoclose_queue.closed_at,
            )
            .where(
                and_(
                    m.order_autoclose_queue.autoclose_at <= now,
                    m.order_autoclose_queue.processed_at.is_(None),
                )
            )
            .limit(100)  # Обрабатываем пачками
        )
        
        rows = (await session.execute(stmt)).all()
        
        if not rows:
            return 0
        
        processed_count = 0
        
        for order_id, closed_at in rows:
            try:
                async with session.begin_nested():
                    # Проверяем актуальный статус заказа
                    order = await session.get(m.orders, order_id)
                    
                    if not order:
                        # Заказ удалён - удаляем из очереди
                        await session.execute(
                            delete(m.order_autoclose_queue)
                            .where(m.order_autoclose_queue.order_id == order_id)
                        )
                        continue
                    
                    # Если статус всё ещё CLOSED - архивируем
                    if order.status == m.OrderStatus.CLOSED:
                        # В будущем здесь может быть перенос в архивную таблицу
                        # Пока просто помечаем как обработанное
                        
                        # Логируем автозакрытие
                        await session.execute(
                            insert(m.order_status_history).values(
                                order_id=order_id,
                                from_status=m.OrderStatus.CLOSED,
                                to_status=m.OrderStatus.CLOSED,
                                reason="autoclose_24h",
                                actor_type=m.ActorType.SYSTEM,
                            )
                        )
                        
                        live_log.push(
                            "autoclose",
                            f"order#{order_id} auto-closed after 24h",
                            level="INFO",
                        )
                    
                    # Помечаем как обработанное
                    await session.execute(
                        update(m.order_autoclose_queue)
                        .where(m.order_autoclose_queue.order_id == order_id)
                        .values(processed_at=now)
                    )
                    
                    processed_count += 1
                    
            except Exception as exc:
                logger.exception("Failed to autoclose order %s: %s", order_id, exc)
                live_log.push(
                    "autoclose",
                    f"order#{order_id} autoclose failed: {exc}",
                    level="ERROR",
                )
        
        await session.commit()
        
        return processed_count


async def autoclose_scheduler(
    session_factory=SessionLocal,
    *,
    interval_seconds: int = 3600,  # Проверка раз в час
    iterations: int | None = None,
) -> None:
    """
    Фоновый планировщик для автозакрытия заказов.
    
    Args:
        session_factory: Фабрика сессий БД
        interval_seconds: Интервал проверки (по умолчанию 1 час)
        iterations: Количество итераций (None = бесконечно)
    """
    sleep_for = max(60, interval_seconds)
    loops_done = 0
    
    logger.info("Autoclose scheduler started, interval=%ss", sleep_for)
    
    while True:
        try:
            count = await process_autoclose_queue(session_factory)
            
            if count > 0:
                logger.info("Autoclose processed %s orders", count)
                live_log.push(
                    "autoclose",
                    f"processed {count} orders",
                    level="INFO",
                )
        except Exception as exc:
            logger.exception("Autoclose scheduler error: %s", exc)
            live_log.push(
                "autoclose",
                f"scheduler error: {exc}",
                level="ERROR",
            )
        
        loops_done += 1
        if iterations is not None and loops_done >= iterations:
            break
        
        await asyncio.sleep(sleep_for)
