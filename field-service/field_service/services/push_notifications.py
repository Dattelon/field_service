"""
P1-05: PUSH-уведомления для мастеров и админов

Сервис для отправки уведомлений через БД очередь.
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
    """События для уведомлений."""
    # Уведомления для мастеров
    MODERATION_APPROVED = "moderation_approved"
    MODERATION_REJECTED = "moderation_rejected"
    ACCOUNT_BLOCKED = "account_blocked"
    ACCOUNT_UNBLOCKED = "account_unblocked"
    NEW_OFFER = "new_offer"
    LIMIT_CHANGED = "limit_changed"
    REFERRAL_REGISTERED = "referral_registered"
    REFERRAL_REWARD_ACCRUED = "referral_reward_accrued"

    # Уведомления для админов/логистов
    ESCALATION_LOGIST = "escalation_logist"
    ESCALATION_ADMIN = "escalation_admin"
    COMMISSION_OVERDUE = "commission_overdue"

    # Системные уведомления
    UNASSIGNED_ORDERS = "unassigned_orders"


# Шаблоны уведомлений
NOTIFICATION_TEMPLATES = {
    NotificationEvent.MODERATION_APPROVED: (
        "✅ <b>Анкета одобрена!</b>\n\n"
        "Ваша анкета проверена и одобрена. "
        "Теперь вы можете получать заявки."
    ),
    NotificationEvent.MODERATION_REJECTED: (
        "❌ <b>Анкета отклонена</b>\n\n"
        "Причина: {reason}\n\n"
        "Исправьте данные и отправьте анкету заново."
    ),
    NotificationEvent.ACCOUNT_BLOCKED: (
        "🚫 <b>Аккаунт заблокирован</b>\n\n"
        "Причина: {reason}\n\n"
        "Свяжитесь с администрацией для разблокировки."
    ),
    NotificationEvent.ACCOUNT_UNBLOCKED: (
        "🔓 <b>Аккаунт разблокирован</b>\n\n"
        "Ваш аккаунт снова активен. Можете продолжать работу."
    ),
    NotificationEvent.NEW_OFFER: (
        "🔔 <b>Новая заявка #{order_id}</b>\n\n"
        "📍 Адрес: {city}, {district}\n"
        "🕐 Время: {timeslot}\n"
        "⚙️ Категория: {category}\n\n"
        "{description}\n\n"
        "Ожидает в разделе «📥 Новые»."
    ),
    NotificationEvent.LIMIT_CHANGED: (
        "📦 <b>Изменен лимит активных заявок</b>\n\n"
        "Новый лимит: {limit}"
    ),
    NotificationEvent.REFERRAL_REGISTERED: (
        "🎉 <b>Новый реферал!</b>\n\n"
        "По вашему коду зарегистрировался новый мастер:\n"
        "{referred_name}\n\n"
        "Теперь вы будете получать бонусы с каждого его заказа!"
    ),
    NotificationEvent.REFERRAL_REWARD_ACCRUED: (
        "💰 <b>Начислен реферальный бонус!</b>\n\n"
        "Сумма: {amount} ₽\n"
        "Уровень: {level}\n"
        "Заказ: #{order_id}\n\n"
        "Проверьте раздел «🎁 Реферальная программа» для деталей."
    ),
    NotificationEvent.ESCALATION_LOGIST: (
        "⚠️ <b>Внимание: заявка #{order_id}</b>\n\n"
        "Не назначена долгое время. Требуется вмешательство логиста."
    ),
    NotificationEvent.ESCALATION_ADMIN: (
        "🚨 <b>Срочно: заявка #{order_id}</b>\n\n"
        "Не назначена критически долго. Требуется срочное вмешательство!"
    ),
    NotificationEvent.COMMISSION_OVERDUE: (
        "🚫 <b>Просрочена комиссия #{commission_id}</b>\n\n"
        "Заказ: #{order_id}\n"
        "Мастер: {master_name} (#{master_id})\n"
        "Требуется действие."
    ),
    NotificationEvent.UNASSIGNED_ORDERS: (
        "⚠️ <b>Незакрепленные заявки: {count}</b>\n\n"
        "В системе {count} заявок без мастера больше 10 минут."
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
        notifications_outbox.
    
    Args:
        session:  
        master_id: ID 
        event:  
        **kwargs:   
    """
    template = NOTIFICATION_TEMPLATES.get(event)
    if not template:
        template = ": {event}"
    
    try:
        message = template.format(event=event.value, **kwargs)
    except KeyError as exc:
        live_log.push(
            "notifications",
            f"Template error for {event}: missing key {exc}",
            level="ERROR"
        )
        message = f": {event.value}"
    
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
         .
    
    Args:
        bot:  
        alerts_chat_id: ID   
        event:  
        **kwargs:   
    """
    template = NOTIFICATION_TEMPLATES.get(event)
    if not template:
        template = ": {event}"
    
    try:
        message = template.format(event=event.value, **kwargs)
    except KeyError as exc:
        live_log.push(
            "notifications",
            f"Template error for {event}: missing key {exc}",
            level="ERROR"
        )
        message = f": {event.value}"
    
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
       (    ).
    
           .
    """
    #        
    await notify_admin(bot, alerts_chat_id, event=event, **kwargs)


#  :

"""
#    (admin_masters.py):
from field_service.services.push_notifications import notify_master, NotificationEvent

await notify_master(
    session,
    master_id=master_id,
    event=NotificationEvent.MODERATION_APPROVED,
)

#   (distribution_worker.py):
from field_service.services.push_notifications import notify_admin, NotificationEvent

await notify_admin(
    bot,
    alerts_chat_id=env_settings.alerts_chat_id,
    event=NotificationEvent.ESCALATION_LOGIST,
    order_id=order_id,
)

#    (watchdogs.py):
await notify_master(
    session,
    master_id=master_id,
    event=NotificationEvent.ACCOUNT_BLOCKED,
    reason="  ",
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
# print(" P1-05: PUSH- -  ")
# print("    ")
