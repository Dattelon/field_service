from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from field_service.db import models as m
from field_service.db.session import SessionLocal
from field_service.services import live_log
from field_service.services.push_notifications import (
    notify_master as push_notify_master,
    notify_admin as push_notify_admin,
    NotificationEvent,
)
from field_service.infra.notify import send_alert
from field_service.services.commission_service import (
    CommissionOverdueEvent,
    apply_overdue_commissions,
)

UTC = timezone.utc
logger = logging.getLogger("watchdogs")


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


async def watchdog_commissions_overdue(
    bot: Bot,
    alerts_chat_id: Optional[int],
    interval_seconds: int = 600,
    *,
    iterations: int | None = None,
    session: Optional[AsyncSession] = None,
) -> None:
    """Periodically block overdue commissions and notify admins.
    
    Args:
        bot: Bot instance for sending notifications
        alerts_chat_id: Chat ID for admin alerts
        interval_seconds: Check interval in seconds
        iterations: Number of iterations (None = infinite)
        session: Optional test session (default: create own)
    """

    sleep_for = max(60, int(interval_seconds) if interval_seconds else 600)
    loops_done = 0
    while True:
        try:
            async with _maybe_session(session) as s:
                events = await apply_overdue_commissions(s, now=datetime.now(UTC))
                await s.commit()

            if events:
                live_log.push("watchdog", f"commission_overdue count={len(events)}", level="WARN")
                for event in events:
                    live_log.push(
                        "watchdog",
                        f"commission_overdue cid={event.commission_id} order={event.order_id} master={event.master_id}",
                        level="WARN",
                    )
                if alerts_chat_id is not None and bot is not None:
                    for event in events:
                        await _notify_overdue_commission(bot, alerts_chat_id, event)
                        # P0-3: Уведомить мастера о блокировке
                        await _notify_master_blocked(bot, event, session=session)
                for event in events:
                    logger.info(
                        "commission_overdue cid=%s order=%s master=%s",
                        event.commission_id,
                        event.order_id,
                        event.master_id,
                    )
        except Exception as exc:
            logger.exception("watchdog_commissions_overdue error")
            live_log.push("watchdog", f"watchdog_commissions_overdue error: {exc}", level="ERROR")

        loops_done += 1
        if iterations is not None and loops_done >= iterations:
            break

        await asyncio.sleep(sleep_for)


async def _notify_overdue_commission(bot: Bot, chat_id: int, event: CommissionOverdueEvent) -> None:
    if bot is None or chat_id is None:
        return
    master_name = event.master_full_name or f"Мастер #{event.master_id}"
    try:
        # Compose explicit alert text to match expected format
        text = (
            f"🚫 Просрочка комиссии #{event.commission_id}\n\n"
            f"Заказ: #{event.order_id}\n"
            f"Мастер: {master_name} (#{event.master_id})"
        )
        kb = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="Открыть", callback_data=f"adm:f:cm:{event.commission_id}")]]
        )
        await send_alert(bot, text, chat_id=chat_id, reply_markup=kb)
    except Exception:
        logger.warning("watchdog notification failed", exc_info=True)
        live_log.push("watchdog", "notification send failed", level="WARN")


async def _notify_master_blocked(
    bot: Bot, 
    event: CommissionOverdueEvent,
    *,
    session: Optional[AsyncSession] = None,
) -> None:
    """P0-3: Уведомить мастера о блокировке аккаунта за просрочку комиссии.
    
    Args:
        bot: Bot instance for sending messages
        event: Commission overdue event details
        session: Optional test session (default: create own)
    """
    reason_text = (
        f"Просрочка комиссии #{event.commission_id} по заказу #{event.order_id}"
    )
    try:
        async with _maybe_session(session) as s:
            result = await s.execute(
                select(m.masters.tg_user_id)
                .where(m.masters.id == event.master_id)
            )
            master_row = result.first()
            if not master_row or not master_row.tg_user_id:
                logger.warning(
                    "Cannot notify master %s: no tg_user_id",
                    event.master_id,
                )
                return

            tg_user_id = master_row.tg_user_id

            try:
                await push_notify_master(
                    s,
                    master_id=event.master_id,
                    event=NotificationEvent.ACCOUNT_BLOCKED,
                    reason=reason_text,
                )
                await s.commit()
            except Exception as push_exc:
                await s.rollback()
                logger.warning(
                    "Failed to enqueue blocked notification for master %s: %s",
                    event.master_id,
                    push_exc,
                    exc_info=True,
                )

            message = (
                "🚫 <b>Ваш аккаунт заблокирован</b>\n\n"
                f"Причина: {reason_text}.\n\n"
                "Чтобы разблокировать аккаунт, оплатите комиссию и свяжитесь с поддержкой."
            )

            await bot.send_message(
                chat_id=tg_user_id,
                text=message,
                parse_mode="HTML",
            )

            live_log.push(
                "watchdog",
                f"master_blocked_notified master={event.master_id} tg={tg_user_id}",
                level="INFO",
            )
            logger.info(
                "master_blocked_notified master=%s tg_user_id=%s",
                event.master_id,
                tg_user_id,
            )
    except Exception as exc:
        logger.warning(
            "Failed to notify master %s about blocking: %s",
            event.master_id,
            exc,
            exc_info=True,
        )
        live_log.push(
            "watchdog",
            f"master_blocked_notify_failed master={event.master_id} error={exc}",
            level="WARN",
        )


# ===== P1-21: Commission Deadline Reminders =====


async def watchdog_commission_deadline_reminders(
    master_bot_token: str,
    interval_seconds: int = 600,
    *,
    iterations: int | None = None,
    session: Optional[AsyncSession] = None,
) -> None:
    """P1-21: Periodically check commissions and send deadline reminders at 24h, 6h, 1h before deadline.
    
    Args:
        master_bot_token: Token master-бота для отправки уведомлений мастерам
        interval_seconds: Интервал проверки в секундах
        iterations: Количество итераций (None = бесконечно)
        session: Optional test session (default: create own)
    """
    from datetime import timedelta
    from sqlalchemy import and_, insert
    from aiogram.client.default import DefaultBotProperties
    from aiogram.enums import ParseMode

    REMINDER_HOURS = [24, 6, 1]  # Отправляем уведомления за 24ч, 6ч и 1ч
    
    # Создаём master bot instance для отправки мастерам
    master_bot = Bot(
        master_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    
    sleep_for = max(60, int(interval_seconds) if interval_seconds else 600)
    loops_done = 0
    
    try:
        while True:
            try:
                now = datetime.now(UTC)
                async with _maybe_session(session) as s:
                    # Находим все комиссии в статусе WAIT_PAY
                    result = await s.execute(
                        select(m.commissions)
                        .where(
                            and_(
                                m.commissions.status == m.CommissionStatus.WAIT_PAY,
                                m.commissions.deadline_at > now  # Ещё не просрочены
                            )
                        )
                    )
                    pending_commissions = result.scalars().all()
                    
                    notifications_sent = 0
                    
                    for commission in pending_commissions:
                        time_until_deadline = commission.deadline_at - now
                        hours_until = time_until_deadline.total_seconds() / 3600
                        
                        # Проверяем каждый порог уведомлений
                        for reminder_hours in REMINDER_HOURS:
                            # Нужно отправить если:
                            # 1. До дедлайна осталось меньше reminder_hours
                            # 2. Ещё не отправляли уведомление для этого порога
                            if hours_until <= reminder_hours:
                                # Проверяем не отправляли ли уже
                                check = await s.execute(
                                    select(m.commission_deadline_notifications)
                                    .where(
                                        and_(
                                            m.commission_deadline_notifications.commission_id == commission.id,
                                            m.commission_deadline_notifications.hours_before == reminder_hours
                                        )
                                    )
                                )
                                already_sent = check.scalar_one_or_none()
                                
                                if not already_sent:
                                    # Отправляем уведомление мастеру через master_bot
                                    sent = await _send_deadline_reminder(
                                        master_bot,  # ← Используем master_bot!
                                        s, 
                                        commission, 
                                        reminder_hours
                                    )
                                    
                                    if sent:
                                        # Записываем что отправили
                                        await s.execute(
                                            insert(m.commission_deadline_notifications).values(
                                                commission_id=commission.id,
                                                hours_before=reminder_hours
                                            )
                                        )
                                        notifications_sent += 1
                    
                    await s.commit()
                    
                    if notifications_sent > 0:
                        live_log.push(
                            "watchdog",
                            f"commission_deadline_reminders sent={notifications_sent}",
                            level="INFO"
                        )
                        logger.info(
                            "commission_deadline_reminders sent=%d notifications",
                            notifications_sent
                        )
                        
            except Exception as exc:
                logger.exception("watchdog_commission_deadline_reminders error")
                live_log.push(
                    "watchdog",
                    f"watchdog_commission_deadline_reminders error: {exc}",
                    level="ERROR"
                )
            
            loops_done += 1
            if iterations is not None and loops_done >= iterations:
                break
            
            await asyncio.sleep(sleep_for)
    finally:
        # Закрываем master_bot session
        await master_bot.session.close()


async def _send_deadline_reminder(
    bot: Bot,
    session,
    commission: m.commissions,
    hours_before: int
) -> bool:
    """Отправить уведомление мастеру о приближающемся дедлайне комиссии."""
    try:
        # Получаем мастера и заказ
        result = await session.execute(
            select(m.masters.tg_user_id, m.orders.id)
            .join(m.orders, m.orders.id == commission.order_id)
            .where(m.masters.id == commission.master_id)
        )
        row = result.first()
        
        if not row or not row.tg_user_id:
            logger.warning(
                "Cannot send deadline reminder: master %s has no tg_user_id",
                commission.master_id
            )
            return False
        
        tg_user_id = row.tg_user_id
        order_id = row.id
        
        # Формируем текст уведомления
        if hours_before == 24:
            time_text = "24 часа"
            emoji = "⏰"
        elif hours_before == 6:
            time_text = "6 часов"
            emoji = "⚠️"
        else:  # 1 hour
            time_text = "1 час"
            emoji = "🔴"
        
        amount_str = f"{commission.amount:.2f}₽"
        
        message = (
            f"{emoji} <b>Напоминание об оплате комиссии</b>\n\n"
            f"До дедлайна оплаты комиссии осталось <b>{time_text}</b>\n\n"
            f"📋 Заказ #{order_id}\n"
            f"💰 Сумма: {amount_str}\n\n"
            f"Пожалуйста, отметьте оплату или загрузите чек в разделе \"Финансы\".\n\n"
            f"⚠️ При просрочке оплаты ваш аккаунт будет заблокирован."
        )
        
        # Отправляем уведомление
        await bot.send_message(
            chat_id=tg_user_id,
            text=message,
            parse_mode="HTML"
        )
        
        logger.info(
            "commission_deadline_reminder sent: commission=%s master=%s hours=%s",
            commission.id,
            commission.master_id,
            hours_before
        )
        
        return True
        
    except Exception as exc:
        logger.warning(
            "Failed to send deadline reminder for commission %s: %s",
            commission.id,
            exc,
            exc_info=True
        )
        return False


# ===== Expired Breaks Watchdog =====


async def expire_old_breaks(*, session: Optional[AsyncSession] = None) -> int:
    """Завершает истёкшие перерывы мастеров.
    
    Args:
        session: Опциональная тестовая сессия
        
    Returns:
        Количество завершённых перерывов
    """
    from sqlalchemy import text

    async with _maybe_session(session) as s:
        result = await s.execute(
            text(
                """
                UPDATE masters
                SET
                    shift_status = 'SHIFT_OFF',
                    is_on_shift = false,
                    break_until = NULL,
                    updated_at = NOW()
                WHERE shift_status = 'BREAK'
                  AND break_until IS NOT NULL
                  AND break_until <= NOW()
                RETURNING id, tg_user_id, full_name
                """
            )
        )
        expired_breaks = result.fetchall()
        await s.commit()

        if expired_breaks:
            live_log.push(
                "watchdog",
                f"expired_breaks_ended count={len(expired_breaks)}",
                level="INFO",
            )

            for master_id, tg_user_id, full_name in expired_breaks:
                logger.info(
                    "break_expired_auto_ended master_id=%s name=%s",
                    master_id,
                    full_name or "???",
                )
                live_log.push(
                    "watchdog",
                    f"break_expired master={master_id} auto_ended tg={tg_user_id}",
                    level="INFO",
                )

        return len(expired_breaks)


async def watchdog_expired_breaks(
    interval_seconds: int = 60,
    *,
    iterations: int | None = None,
    session: Optional[AsyncSession] = None,
) -> None:
    """
    BUGFIX 2025-10-10: Automatically end expired breaks and set masters to SHIFT_OFF.

    Периодически проверяет мастеров на перерыве и переводит их в SHIFT_OFF,
    если break_until истёк и перерыв не завершён вручную.
    
    Args:
        interval_seconds: Интервал проверки в секундах
        iterations: Количество итераций (None = бесконечно)
        session: Optional test session (default: create own)
    """

    sleep_for = max(30, int(interval_seconds) if interval_seconds else 60)
    loops_done = 0

    live_log.push(
        "watchdog",
        f"watchdog_expired_breaks started (interval={sleep_for}s)",
        level="INFO",
    )

    while True:
        try:
            await expire_old_breaks(session=session)
        except Exception as exc:
            logger.exception("watchdog_expired_breaks error")
            live_log.push(
                "watchdog",
                f"watchdog_expired_breaks error: {exc}",
                level="ERROR",
            )

        loops_done += 1
        if iterations is not None and loops_done >= iterations:
            break

        await asyncio.sleep(sleep_for)


# ===== Expired Offers Watchdog =====


async def watchdog_expired_offers(
    interval_seconds: int = 60,
    *,
    iterations: int | None = None,
    session: Optional[AsyncSession] = None,
) -> None:
    """Periodically mark expired offers as EXPIRED.
    
    Args:
        interval_seconds: Интервал проверки в секундах
        iterations: Количество итераций (None = бесконечно)
        session: Optional test session (default: create own)
    """
    from sqlalchemy import text
    
    sleep_for = max(30, int(interval_seconds) if interval_seconds else 60)
    loops_done = 0
    
    while True:
        try:
            now = datetime.now(UTC)
            async with _maybe_session(session) as s:
                # Помечаем все истёкшие офферы как EXPIRED
                result = await s.execute(
                    text("""
                        UPDATE offers
                        SET state = 'EXPIRED', responded_at = NOW()
                        WHERE state = 'SENT'
                          AND expires_at <= NOW()
                        RETURNING id, order_id, master_id
                    """)
                )
                expired_offers = result.fetchall()
                await s.commit()
                
                if expired_offers:
                    live_log.push(
                        "watchdog",
                        f"expired_offers count={len(expired_offers)}",
                        level="INFO"
                    )
                    for offer_id, order_id, master_id in expired_offers:
                        logger.info(
                            "offer_expired id=%s order=%s master=%s",
                            offer_id,
                            order_id,
                            master_id
                        )
                        live_log.push(
                            "watchdog",
                            f"offer_expired oid={offer_id} order={order_id} master={master_id}",
                            level="INFO"
                        )
                        
        except Exception as exc:
            logger.exception("watchdog_expired_offers error")
            live_log.push(
                "watchdog",
                f"watchdog_expired_offers error: {exc}",
                level="ERROR"
            )
        
        loops_done += 1
        if iterations is not None and loops_done >= iterations:
            break
        
        await asyncio.sleep(sleep_for)
