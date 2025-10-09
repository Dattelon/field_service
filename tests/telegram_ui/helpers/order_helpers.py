"""
Helper функции для работы с заказами
"""
import asyncio
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from tests.telegram_ui.bot_client import BotTestClient
from tests.telegram_ui.config import ADMIN_BOT_USERNAME


async def create_order_via_admin(
    client: BotTestClient,
    session: AsyncSession,
    *,
    service: str = "Ремонт iPhone",
    city: str = "Москва",
    district: str = "ЦАО",
    address: str = "ул. Тверская, 1",
    client_phone: str = "+79991234567",
    cost: int = 3000,
    slot: str = "nearest",  # "nearest" или "12:00-14:00"
) -> int:
    """
    Создать заказ через админ-бота
    
    Args:
        client: Telethon клиент
        session: БД сессия
        service: Название услуги
        city: Город
        district: Район
        address: Адрес клиента
        client_phone: Телефон клиента
        cost: Стоимость заказа
        slot: Временной слот
    
    Returns:
        order_id: ID созданного заказа
    """
    # Открываем админ-бот
    await client.send_command(ADMIN_BOT_USERNAME, "/start")
    await asyncio.sleep(1)
    
    # Нажимаем "Новый заказ"
    await client.click_button("➕ Новый заказ", ADMIN_BOT_USERNAME)
    await asyncio.sleep(1)
    
    # Выбираем город
    await client.click_button(city, ADMIN_BOT_USERNAME)
    await asyncio.sleep(1)
    
    # Выбираем район
    await client.click_button(district, ADMIN_BOT_USERNAME)
    await asyncio.sleep(1)
    
    # Вводим адрес
    await client.send_command(ADMIN_BOT_USERNAME, address)
    await asyncio.sleep(1)
    
    # Выбираем услугу
    await client.click_button(service, ADMIN_BOT_USERNAME)
    await asyncio.sleep(1)
    
    # Вводим стоимость
    await client.send_command(ADMIN_BOT_USERNAME, str(cost))
    await asyncio.sleep(1)
    
    # Вводим телефон клиента
    await client.send_command(ADMIN_BOT_USERNAME, client_phone)
    await asyncio.sleep(1)
    
    # Выбираем слот
    if slot == "nearest":
        # Нажимаем на ближайший доступный слот (первая кнопка)
        msg = await client.get_last_message(ADMIN_BOT_USERNAME)
        if msg and msg.reply_markup:
            buttons = msg.reply_markup.rows[0].buttons
            if buttons:
                await client.click_button(buttons[0].text, ADMIN_BOT_USERNAME)
    else:
        await client.click_button(slot, ADMIN_BOT_USERNAME)
    
    await asyncio.sleep(2)
    
    # Находим созданный заказ в БД (последний созданный)
    result = await session.execute(
        text("SELECT id FROM orders ORDER BY id DESC LIMIT 1")
    )
    order = result.first()
    
    if not order:
        raise ValueError("Order not created")
    
    return order.id


async def wait_for_offer(
    session: AsyncSession,
    order_id: int,
    master_id: int,
    timeout: int = 30,
) -> bool:
    """
    Ожидать появления оффера для мастера
    
    Args:
        session: БД сессия
        order_id: ID заказа
        master_id: ID мастера
        timeout: Таймаут ожидания в секундах
    
    Returns:
        True если оффер появился, False если таймаут
    """
    for _ in range(timeout):
        result = await session.execute(
            text("""
                SELECT id FROM offers 
                WHERE order_id = :order_id 
                AND master_id = :master_id
                LIMIT 1
            """),
            {"order_id": order_id, "master_id": master_id}
        )
        offer = result.first()
        
        if offer:
            return True
        
        await asyncio.sleep(1)
    
    return False


async def get_order_status(
    session: AsyncSession,
    order_id: int,
) -> str:
    """
    Получить текущий статус заказа
    
    Args:
        session: БД сессия
        order_id: ID заказа
    
    Returns:
        Статус заказа (NEW, IN_QUEUE, ASSIGNED, STARTED, etc.)
    """
    result = await session.execute(
        text("SELECT status FROM orders WHERE id = :id"),
        {"id": order_id}
    )
    row = result.first()
    
    if not row:
        raise ValueError(f"Order {order_id} not found")
    
    return row.status


async def cancel_order(
    client: BotTestClient,
    order_id: int,
    reason: str = "Клиент отказался",
) -> None:
    """
    Отменить заказ через админ-бота
    
    Args:
        client: Telethon клиент
        order_id: ID заказа
        reason: Причина отмены
    """
    # Открываем очередь заказов
    await client.click_button("📋 Очередь заказов", ADMIN_BOT_USERNAME)
    await asyncio.sleep(1)
    
    # TODO: Найти конкретный заказ и открыть его карточку
    # Пока просто нажимаем первый заказ
    # В реальности нужно искать по ID
    
    # Нажимаем "Отменить заказ"
    await client.click_button("❌ Отменить заказ", ADMIN_BOT_USERNAME)
    await asyncio.sleep(0.5)
    
    # Вводим причину
    await client.send_command(ADMIN_BOT_USERNAME, reason)
    await asyncio.sleep(1)
    
    # Подтверждаем
    await client.click_button("Да, отменить", ADMIN_BOT_USERNAME)
    await asyncio.sleep(1)
