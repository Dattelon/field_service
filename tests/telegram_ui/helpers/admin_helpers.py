"""
Helper функции для админских действий
"""
import asyncio
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from tests.telegram_ui.bot_client import BotTestClient
from tests.telegram_ui.config import ADMIN_BOT_USERNAME


async def assign_order_manually(
    client: BotTestClient,
    order_id: int,
    master_id: int,
) -> None:
    """
    Вручную назначить заказ на мастера через админ-бота
    
    Args:
        client: Telethon клиент
        order_id: ID заказа
        master_id: ID мастера
    """
    # Открываем очередь заказов
    await client.click_button("📋 Очередь заказов", ADMIN_BOT_USERNAME)
    await asyncio.sleep(1)
    
    # TODO: Найти заказ по ID
    # Пока упрощенно - нажимаем первый заказ
    
    # Открываем карточку заказа
    msg = await client.get_last_message(ADMIN_BOT_USERNAME)
    # Нажимаем на первый заказ в списке
    # (здесь нужна более точная логика поиска)
    
    # Нажимаем "Назначить мастера"
    await client.click_button("👤 Назначить мастера", ADMIN_BOT_USERNAME)
    await asyncio.sleep(1)
    
    # TODO: Выбрать конкретного мастера из списка
    # Пока упрощенно - нажимаем первого доступного
    msg = await client.get_last_message(ADMIN_BOT_USERNAME)
    if msg and msg.reply_markup:
        buttons = msg.reply_markup.rows[0].buttons
        if buttons:
            await client.click_button(buttons[0].text, ADMIN_BOT_USERNAME)
    
    await asyncio.sleep(1)
    
    # Подтверждаем назначение
    await client.click_button("✅ Подтвердить", ADMIN_BOT_USERNAME)
    await asyncio.sleep(1)


async def moderate_master(
    client: BotTestClient,
    master_id: int,
    action: str = "approve",  # "approve" или "decline"
    reason: Optional[str] = None,
) -> None:
    """
    Модерировать заявку мастера
    
    Args:
        client: Telethon клиент
        master_id: ID мастера
        action: "approve" для одобрения, "decline" для отклонения
        reason: Причина отклонения (только для decline)
    """
    # Открываем модерацию
    await client.click_button("👥 Модерация", ADMIN_BOT_USERNAME)
    await asyncio.sleep(1)
    
    # TODO: Найти заявку конкретного мастера
    # Пока упрощенно - работаем с первой заявкой
    
    if action == "approve":
        await client.click_button("✅ Одобрить", ADMIN_BOT_USERNAME)
        await asyncio.sleep(1)
    elif action == "decline":
        await client.click_button("❌ Отклонить", ADMIN_BOT_USERNAME)
        await asyncio.sleep(0.5)
        
        # Вводим причину
        if reason:
            await client.send_command(ADMIN_BOT_USERNAME, reason)
            await asyncio.sleep(1)
    else:
        raise ValueError(f"Unknown action: {action}")


async def approve_master(
    client: BotTestClient,
    master_id: int,
) -> None:
    """
    Одобрить заявку мастера
    
    Args:
        client: Telethon клиент
        master_id: ID мастера
    """
    await moderate_master(client, master_id, action="approve")


async def decline_master(
    client: BotTestClient,
    master_id: int,
    reason: str = "Не прошел проверку",
) -> None:
    """
    Отклонить заявку мастера
    
    Args:
        client: Telethon клиент
        master_id: ID мастера
        reason: Причина отклонения
    """
    await moderate_master(client, master_id, action="decline", reason=reason)


async def finalize_order(
    client: BotTestClient,
    order_id: int,
) -> None:
    """
    Финализировать заказ (перевести из MASTER_COMPLETED в CLOSED)
    
    Args:
        client: Telethon клиент
        order_id: ID заказа
    """
    # Открываем очередь заказов
    await client.click_button("📋 Очередь заказов", ADMIN_BOT_USERNAME)
    await asyncio.sleep(1)
    
    # TODO: Найти заказ по ID
    
    # Нажимаем "Подтвердить выполнение"
    await client.click_button("✅ Подтвердить выполнение", ADMIN_BOT_USERNAME)
    await asyncio.sleep(1)
