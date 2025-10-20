"""
P1-05: PUSH-  

     .
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
    """  ."""
    #  
    MODERATION_APPROVED = "moderation_approved"
    MODERATION_REJECTED = "moderation_rejected"
    ACCOUNT_BLOCKED = "account_blocked"
    ACCOUNT_UNBLOCKED = "account_unblocked"
    NEW_OFFER = "new_offer"
    LIMIT_CHANGED = "limit_changed"
    
    #  
    ESCALATION_LOGIST = "escalation_logist"
    ESCALATION_ADMIN = "escalation_admin"
    COMMISSION_OVERDUE = "commission_overdue"
    
    #  
    UNASSIGNED_ORDERS = "unassigned_orders"


#  
NOTIFICATION_TEMPLATES = {
    NotificationEvent.MODERATION_APPROVED: (
        " <b> !</b>\n\n"
        "    . "
        "   ."
    ),
    NotificationEvent.MODERATION_REJECTED: (
        " <b> </b>\n\n"
        ": {reason}\n\n"
        "    ."
    ),
    NotificationEvent.ACCOUNT_BLOCKED: (
        " <b> </b>\n\n"
        ": {reason}\n\n"
        "    ."
    ),
    NotificationEvent.ACCOUNT_UNBLOCKED: (
        " <b> </b>\n\n"
        "    ."
    ),
    NotificationEvent.NEW_OFFER: (
        " <b>  #{order_id}</b>\n\n"
        " {city}, {district}\n"
        " {timeslot}\n"
        " {category}\n\n"
        "    ."
    ),
    NotificationEvent.LIMIT_CHANGED: (
        " <b>   </b>\n\n"
        " : {limit}"
    ),
    NotificationEvent.ESCALATION_LOGIST: (
        " <b>  #{order_id}</b>\n\n"
        "  .   ."
    ),
    NotificationEvent.ESCALATION_ADMIN: (
        " <b>  #{order_id}</b>\n\n"
        "    .  !"
    ),
    NotificationEvent.COMMISSION_OVERDUE: (
        " <b>  #{commission_id}</b>\n\n"
        ": #{order_id}\n"
        ": {master_name} (#{master_id})\n"
        "  ."
    ),
    NotificationEvent.UNASSIGNED_ORDERS: (
        " <b> : {count}</b>\n\n"
        "  {count}   10 ."
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
