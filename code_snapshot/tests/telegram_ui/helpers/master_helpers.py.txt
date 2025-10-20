"""
Helper функции для работы с мастерами через мастер-бот
"""
import asyncio
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, select

from tests.telegram_ui.bot_client import BotTestClient
from tests.telegram_ui.config import MASTER_BOT_USERNAME


async def create_master_via_onboarding(
    client: BotTestClient,
    session: AsyncSession,
    *,
    city: str = "Москва",
    district: str = "ЦАО",
    phone: str = "+79991234567",
    auto_approve: bool = True
) -> int:
    """
    Создать мастера через онбординг в мастер-боте
    
    Args:
        client: Telethon клиент
        session: БД сессия
        city: Город мастера
        district: Округ мастера
        phone: Телефон мастера
        auto_approve: Автоматически одобрить через БД
    
    Returns:
        master_id: ID созданного мастера
    """
    # Начинаем онбординг
    msg = await client.send_command(MASTER_BOT_USERNAME, "/start")
    await asyncio.sleep(1)
    
    # Выбираем город
    msg = await client.click_button(city, MASTER_BOT_USERNAME)
    await asyncio.sleep(1)
    
    # Выбираем округ
    msg = await client.click_button(district, MASTER_BOT_USERNAME)
    await asyncio.sleep(1)
    
    # Отправляем телефон
    msg = await client.send_command(MASTER_BOT_USERNAME, phone)
    await asyncio.sleep(2)
    
    # Получаем telegram_id текущего пользователя
    me = await client.client.get_me()
    telegram_id = me.id
    
    # Ждем создания мастера в БД
    await asyncio.sleep(1)
    
    # Находим созданного мастера
    result = await session.execute(
        text("SELECT id FROM masters WHERE telegram_id = :tg_id ORDER BY id DESC LIMIT 1"),
        {"tg_id": telegram_id}
    )
    master = result.first()
    
    if not master:
        raise ValueError(f"Master not created for telegram_id={telegram_id}")
    
    master_id = master.id
    
    # Автоматически одобряем если нужно
    if auto_approve:
        await session.execute(
            text("UPDATE masters SET is_approved = true WHERE id = :id"),
            {"id": master_id}
        )
        await session.commit()
        
        # Перезапускаем бота чтобы увидеть главное меню
        await client.send_command(MASTER_BOT_USERNAME, "/start")
        await asyncio.sleep(1)
    
    return master_id


async def change_master_status(
    client: BotTestClient,
    status: str,
) -> None:
    """
    Изменить статус мастера (Работаю/Перерыв/Оффлайн)
    
    Args:
        client: Telethon клиент
        status: "working" | "break" | "offline"
    """
    button_map = {
        "working": "🟢 Начать работу",
        "break": "🟡 На перерыв",
        "offline": "🔴 Закончить работу",
    }
    
    if status not in button_map:
        raise ValueError(f"Unknown status: {status}. Use: working, break, offline")
    
    button_text = button_map[status]
    await client.click_button(button_text, MASTER_BOT_USERNAME)
    await asyncio.sleep(1)


async def accept_offer(
    client: BotTestClient,
    order_id: int,
) -> None:
    """
    Принять оффер по заказу
    
    Args:
        client: Telethon клиент
        order_id: ID заказа
    """
    # Ищем сообщение с оффером
    # TODO: Нужно найти последнее сообщение с кнопками и нажать "Принять"
    await client.click_button("✅ Принять заказ", MASTER_BOT_USERNAME)
    await asyncio.sleep(1)


async def decline_offer(
    client: BotTestClient,
    order_id: int,
) -> None:
    """
    Отклонить оффер по заказу
    
    Args:
        client: Telethon клиент
        order_id: ID заказа
    """
    # Нажимаем "Отклонить"
    await client.click_button("❌ Отклонить", MASTER_BOT_USERNAME)
    await asyncio.sleep(0.5)
    
    # Подтверждаем отклонение
    await client.click_button("Да, отклонить", MASTER_BOT_USERNAME)
    await asyncio.sleep(1)


async def start_work(
    client: BotTestClient,
    order_id: int,
) -> None:
    """
    Начать работу по заказу (Приехал на объект)
    
    Args:
        client: Telethon клиент
        order_id: ID заказа
    """
    await client.click_button("🚗 Приехал на объект", MASTER_BOT_USERNAME)
    await asyncio.sleep(1)


async def complete_work(
    client: BotTestClient,
    order_id: int,
) -> None:
    """
    Завершить работу по заказу
    
    Args:
        client: Telethon клиент
        order_id: ID заказа
    """
    await client.click_button("✅ Завершить заказ", MASTER_BOT_USERNAME)
    await asyncio.sleep(1)
