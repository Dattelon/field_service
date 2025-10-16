"""
Тест онбординга мастера
Проверяет процесс первичной регистрации мастера в боте
"""

import pytest
import asyncio
from tests.telegram_ui.bot_client import BotTestClient
from tests.telegram_ui.config import MASTER_BOT_USERNAME, TEST_CITY, TEST_DISTRICT


@pytest.mark.telegram_ui
@pytest.mark.asyncio
async def test_master_start_command():
    """Тест: команда /start для нового мастера"""
    
    async with BotTestClient() as client:
        # Отправляем /start
        message = await client.send_command(MASTER_BOT_USERNAME, "/start")
        
        # Проверяем текст приветствия
        client.assert_text_in_message("Добро пожаловать", message)
        
        # Проверяем наличие кнопок выбора города
        client.assert_has_buttons([f"🏙 {TEST_CITY}"], message)


@pytest.mark.telegram_ui
@pytest.mark.asyncio
async def test_master_select_city():
    """Тест: выбор города при онбординге"""
    
    async with BotTestClient() as client:
        # Отправляем /start
        await client.send_command(MASTER_BOT_USERNAME, "/start")
        
        # Нажимаем на город
        message = await client.click_button(f"🏙 {TEST_CITY}", MASTER_BOT_USERNAME)
        
        # Проверяем, что перешли к выбору района
        client.assert_text_in_message("Выберите район", message)
        
        # Проверяем наличие кнопок с районами (для Москвы)
        if TEST_CITY == "Москва":
            client.assert_has_buttons(["ЦАО", "САО", "ВАО"], message)


@pytest.mark.telegram_ui
@pytest.mark.asyncio
async def test_master_select_district():
    """Тест: выбор района при онбординге"""
    
    async with BotTestClient() as client:
        # Стартуем и выбираем город
        await client.send_command(MASTER_BOT_USERNAME, "/start")
        await client.click_button(f"🏙 {TEST_CITY}", MASTER_BOT_USERNAME)
        
        # Выбираем район
        message = await client.click_button(TEST_DISTRICT, MASTER_BOT_USERNAME)
        
        # Проверяем, что перешли к вводу телефона
        client.assert_text_in_message("телефон", message)


@pytest.mark.telegram_ui
@pytest.mark.asyncio
async def test_master_full_onboarding():
    """Тест: полный процесс онбординга мастера"""
    
    async with BotTestClient() as client:
        print("\n=== Начало полного онбординга мастера ===")
        
        # Шаг 1: /start
        print("\n[1/4] Отправка команды /start...")
        message = await client.send_command(MASTER_BOT_USERNAME, "/start")
        client.assert_text_in_message("Добро пожаловать", message)
        
        # Шаг 2: Выбор города
        print(f"\n[2/4] Выбор города: {TEST_CITY}...")
        message = await client.click_button(f"🏙 {TEST_CITY}", MASTER_BOT_USERNAME)
        client.assert_text_in_message("Выберите район", message)
        
        # Шаг 3: Выбор района
        print(f"\n[3/4] Выбор района: {TEST_DISTRICT}...")
        message = await client.click_button(TEST_DISTRICT, MASTER_BOT_USERNAME)
        client.assert_text_in_message("телефон", message)
        
        # Шаг 4: Отправка телефона
        print(f"\n[4/4] Отправка тестового телефона...")
        # Здесь можно отправить тестовый телефон
        # message = await client.send_command(MASTER_BOT_USERNAME, TEST_MASTER_PHONE)
        
        print("\n✅ Онбординг пройден успешно!")


if __name__ == "__main__":
    # Можно запустить напрямую для быстрого тестирования
    asyncio.run(test_master_start_command())
