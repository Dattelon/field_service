"""
P1-05: PUSH-УВЕДОМЛЕНИЯ КРИТИЧНЫХ СОБЫТИЙ

Расширение системы уведомлений для важных событий.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from aiogram import Bot
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from field_service.db import models as m
from field_service.services import live_log
from field_service.infra.notify import send_alert


class NotificationEvent(str, Enum):
    """Типы критичных уведомлений."""
    # Для мастеров
    MODERATION_APPROVED = "moderation_approved"
    MODERATION_REJECTED = "moderation_rejected"
    ACCOUNT_BLOCKED = "account_blocked"
    ACCOUNT_UNBLOCKED = "account_unblocked"
    NEW_OFFER = "new_offer"
    LIMIT_CHANGED = "limit_changed"
    ORDER_RETURNED = "order_returned"
    
    # Для админов
    ESCALATION_LOGIST = "escalation_logist"
    ESCALATION_ADMIN = "escalation_admin"
    COMMISSION_OVERDUE = "commission_overdue"
    
    # Для логистов
    UNASSIGNED_ORDERS = "unassigned_orders"


# Шаблоны сообщений
NOTIFICATION_TEMPLATES = {
    NotificationEvent.MODERATION_APPROVED: (
        "✅ <b>Анкета одобрена!</b>\n\n"
        "Теперь вы можете принимать заказы. "
        "Включите смену в меню."
    ),
    NotificationEvent.MODERATION_REJECTED: (
        "❌ <b>Анкета отклонена</b>\n\n"
        "Причина: {reason}\n\n"
        "Обратитесь в поддержку для уточнения."
    ),
    NotificationEvent.ACCOUNT_BLOCKED: (
        "🚫 <b>Аккаунт заблокирован</b>\n\n"
        "Причина: {reason}\n\n"
        "Для разблокировки обратитесь в поддержку."
    ),
    NotificationEvent.ACCOUNT_UNBLOCKED: (
        "✅ <b>Аккаунт разблокирован</b>\n\n"
        "Вы снова можете принимать заказы."
    ),
    NotificationEvent.NEW_OFFER: (
        "🆕 <b>Новый заказ #{order_id}</b>\n\n"
        "📍 {city}, {district}\n"
        "⏰ {timeslot}\n"
        "🛠 {category}\n\n"
        "Откройте бот для принятия заказа."
    ),
    NotificationEvent.LIMIT_CHANGED: (
        "🎯 <b>Лимит активных заказов изменён</b>\n\n"
        "Новый лимит: {limit}"
    ),
    NotificationEvent.ORDER_RETURNED: (
        "🔁 <b>Заказ #{order_id} возвращён в поиск</b>\n\n"
        "Причина: {reason}\n\n"
        "Заказ снова доступен для принятия мастерами."
    ),
    NotificationEvent.ESCALATION_LOGIST: (
        "⚠️ <b>Эскалация заказа #{order_id}</b>\n\n"
        "Заказ не распределён. Требуется ручное назначение."
    ),
    NotificationEvent.ESCALATION_ADMIN: (
        "🚨 <b>Критическая эскалация #{order_id}</b>\n\n"
        "Заказ не распределён после логиста. Срочное назначение!"
    ),
    NotificationEvent.COMMISSION_OVERDUE: (
        "⏱ <b>Просрочена комиссия #{commission_id}</b>\n\n"
        "Заказ: #{order_id}\n"
        "Мастер: {master_name} (#{master_id})\n"
        "Мастер заблокирован автоматически."
    ),
    NotificationEvent.UNASSIGNED_ORDERS: (
        "📋 <b>Нераспределённые заказы: {count}</b>\n\n"
        "В очереди {count} заказов более 10 минут."
    ),
}


async def notify_master(
    session: AsyncSession,
    *,
    master_id: int,
    event: NotificationEvent,
    **kwargs: Any,
) -> None:
    """
    Отправить уведомление мастеру через notifications_outbox.
    
    Args:
        session: Сессия БД
        master_id: ID мастера
        event: Тип события
        **kwargs: Параметры для шаблона
    """
    template = NOTIFICATION_TEMPLATES.get(event)
    if not template:
        template = "Уведомление: {event}"
    
    try:
        message = template.format(event=event.value, **kwargs)
    except KeyError as exc:
        live_log.push(
            "notifications",
            f"Template error for {event}: missing key {exc}",
            level="ERROR"
        )
        message = f"Уведомление: {event.value}"
    
    await session.execute(
        insert(m.notifications_outbox).values(
            master_id=master_id,
            event=event.value,
            payload={"message": message, **kwargs},
        )
    )
    
    live_log.push(
        "notifications",
        f"Queued {event.value} for master#{master_id}",
        level="INFO"
    )


async def notify_admin(
    bot: Bot,
    alerts_chat_id: int,
    *,
    event: NotificationEvent,
    **kwargs: Any,
) -> None:
    """
    Отправить уведомление админам в канал алертов.
    
    Args:
        bot: Экземпляр бота
        alerts_chat_id: ID чата для алертов
        event: Тип события
        **kwargs: Параметры для шаблона
    """
    template = NOTIFICATION_TEMPLATES.get(event)
    if not template:
        template = "Алерт: {event}"
    
    try:
        message = template.format(event=event.value, **kwargs)
    except KeyError as exc:
        live_log.push(
            "notifications",
            f"Template error for {event}: missing key {exc}",
            level="ERROR"
        )
        message = f"Алерт: {event.value}"
    
    try:
        await send_alert(bot, message, chat_id=alerts_chat_id)
        live_log.push(
            "notifications",
            f"Sent {event.value} to admin channel",
            level="INFO"
        )
    except Exception as exc:
        live_log.push(
            "notifications",
            f"Failed to send {event.value}: {exc}",
            level="ERROR"
        )


async def notify_logist(
    bot: Bot,
    alerts_chat_id: int,
    *,
    event: NotificationEvent,
    **kwargs: Any,
) -> None:
    """
    Отправить уведомление логистам (пока через тот же канал).
    
    В будущем можно создать отдельный канал для логистов.
    """
    # Пока используем тот же канал что и админы
    await notify_admin(bot, alerts_chat_id, event=event, **kwargs)


# Примеры использования:

"""
# При одобрении мастера (admin_masters.py):
from field_service.services.push_notifications import notify_master, NotificationEvent

await notify_master(
    session,
    master_id=master_id,
    event=NotificationEvent.MODERATION_APPROVED,
)

# При эскалации (distribution_worker.py):
from field_service.services.push_notifications import notify_admin, NotificationEvent

await notify_admin(
    bot,
    alerts_chat_id=env_settings.alerts_chat_id,
    event=NotificationEvent.ESCALATION_LOGIST,
    order_id=order_id,
)

# При просрочке комиссии (watchdogs.py):
await notify_master(
    session,
    master_id=master_id,
    event=NotificationEvent.ACCOUNT_BLOCKED,
    reason="Просрочка оплаты комиссии",
)

await notify_admin(
    bot,
    alerts_chat_id=env_settings.alerts_chat_id,
    event=NotificationEvent.COMMISSION_OVERDUE,
    commission_id=commission_id,
    order_id=order_id,
    master_id=master_id,
    master_name=master_name,
)
"""

# Service initialization logging disabled for Windows console compatibility
# print("✅ P1-05: PUSH-УВЕДОМЛЕНИЯ - сервис создан")
# print("Интегрировать в существующие обработчики событий")
