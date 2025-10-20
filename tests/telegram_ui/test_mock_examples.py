"""
Примеры тестов с использованием Mock Telegram Bot
Безопасное тестирование БЕЗ реального Telegram API
"""

import pytest
from tests.telegram_ui.mock_telegram import MockTelegramBot, create_mock_bot, create_test_chat_id


@pytest.mark.asyncio
async def test_mock_bot_send_message():
    """Тест отправки сообщения"""
    bot = create_mock_bot()
    chat_id = create_test_chat_id()
    
    # Отправляем сообщение
    msg = await bot.send_message(chat_id, "Привет!")
    
    # Проверяем
    assert msg.text == "Привет!"
    assert msg.chat_id == chat_id
    assert len(bot.messages) == 1


@pytest.mark.asyncio
async def test_mock_bot_with_buttons():
    """Тест сообщения с кнопками"""
    bot = create_mock_bot()
    chat_id = create_test_chat_id()
    
    # Создаём inline кнопки
    reply_markup = {
        "inline_keyboard": [
            [{"text": "Кнопка 1", "callback_data": "btn1"}],
            [{"text": "Кнопка 2", "callback_data": "btn2"}]
        ]
    }
    
    # Отправляем сообщение с кнопками
    msg = await bot.send_message(
        chat_id,
        "Выберите действие:",
        reply_markup=reply_markup
    )
    
    # Проверяем кнопки
    assert len(msg.buttons) == 2
    assert msg.buttons[0] == ["Кнопка 1"]
    assert msg.buttons[1] == ["Кнопка 2"]
    
    # Используем helper методы
    bot.assert_has_buttons(["Кнопка 1", "Кнопка 2"], chat_id)


@pytest.mark.asyncio
async def test_mock_bot_edit_message():
    """Тест редактирования сообщения"""
    bot = create_mock_bot()
    chat_id = create_test_chat_id()
    
    # Отправляем оригинальное сообщение
    original = await bot.send_message(chat_id, "Оригинальный текст")
    
    # Редактируем
    edited = await bot.edit_message_text(
        "Отредактированный текст",
        chat_id,
        original.message_id
    )
    
    # Проверяем что это то же сообщение
    assert edited.message_id == original.message_id
    assert edited.text == "Отредактированный текст"


@pytest.mark.asyncio
async def test_mock_bot_button_click():
    """Тест нажатия на кнопку"""
    bot = create_mock_bot()
    chat_id = create_test_chat_id()
    
    # Отправляем сообщение с кнопкой
    reply_markup = {
        "inline_keyboard": [
            [{"text": "Нажми меня", "callback_data": "click_me"}]
        ]
    }
    msg = await bot.send_message(chat_id, "Текст", reply_markup=reply_markup)
    
    # Симулируем нажатие кнопки
    result = await bot.simulate_button_click(
        chat_id,
        msg.message_id,
        "Нажми меня"
    )
    
    # Проверяем что кнопка была обработана
    assert result is not None


@pytest.mark.asyncio
async def test_mock_bot_conversation():
    """Тест полного диалога"""
    bot = create_mock_bot()
    chat_id = create_test_chat_id()
    
    # Симуляция диалога
    await bot.send_message(chat_id, "Добро пожаловать!")
    await bot.send_message(chat_id, "Выберите город:")
    
    # Проверяем что сообщений 2
    messages = bot.get_all_messages(chat_id)
    assert len(messages) == 2
    
    # Проверяем последнее сообщение
    bot.assert_last_message_contains("Выберите город", chat_id)
    
    # Печатаем диалог (для отладки)
    # bot.print_conversation(chat_id)


@pytest.mark.asyncio
async def test_mock_bot_clear():
    """Тест очистки сообщений"""
    bot = create_mock_bot()
    chat_id = create_test_chat_id()
    
    # Отправляем несколько сообщений
    await bot.send_message(chat_id, "Сообщение 1")
    await bot.send_message(chat_id, "Сообщение 2")
    
    assert len(bot.messages) == 2
    
    # Очищаем
    bot.clear_messages()
    
    assert len(bot.messages) == 0


# ============================================
# ИНТЕГРАЦИЯ С РЕАЛЬНЫМИ HANDLERS
# ============================================

@pytest.mark.asyncio
async def test_integration_with_real_handler():
    """
    Пример интеграции mock-бота с реальными handlers из проекта
    ВАЖНО: Это требует адаптации реальных handlers под mock-бота
    """
    bot = create_mock_bot()
    chat_id = create_test_chat_id()
    
    # Пример регистрации handler
    async def start_handler(update, **kwargs):
        msg = update.message
        await bot.send_message(
            msg.chat_id,
            "Привет! Я бот для мастеров."
        )
    
    bot.register_handler("/start", start_handler)
    
    # Симулируем команду /start
    result = await bot.simulate_command(chat_id, "/start")
    
    # Проверяем ответ
    assert result is not None
    assert "Привет" in result.text


if __name__ == "__main__":
    # Быстрый запуск без pytest
    import asyncio
    
    async def main():
        print("Running mock bot tests...")
        
        # Тест 1
        await test_mock_bot_send_message()
        print("✅ Test 1: Send message - PASSED")
        
        # Тест 2
        await test_mock_bot_with_buttons()
        print("✅ Test 2: Buttons - PASSED")
        
        # Тест 3
        await test_mock_bot_edit_message()
        print("✅ Test 3: Edit message - PASSED")
        
        # Тест 4
        await test_mock_bot_button_click()
        print("✅ Test 4: Button click - PASSED")
        
        # Тест 5
        await test_mock_bot_conversation()
        print("✅ Test 5: Conversation - PASSED")
        
        # Тест 6
        await test_mock_bot_clear()
        print("✅ Test 6: Clear - PASSED")
        
        print("\n" + "="*60)
        print("  ALL MOCK TESTS PASSED!")
        print("="*60)
    
    asyncio.run(main())
