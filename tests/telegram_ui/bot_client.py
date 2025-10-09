"""
Helper-класс для работы с Telegram-ботами в тестах
Упрощает отправку команд, клики по кнопкам и проверку ответов
"""

import asyncio
from typing import Optional, List
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import Message
from tests.telegram_ui.config import (
    API_ID, API_HASH, SESSION_STRING,
    MESSAGE_TIMEOUT, BUTTON_CLICK_DELAY
)


class BotTestClient:
    """Клиент для тестирования Telegram-ботов"""
    
    def __init__(self):
        self.client: Optional[TelegramClient] = None
        self._last_message: Optional[Message] = None
    
    async def start(self):
        """Запуск клиента"""
        if not SESSION_STRING:
            raise ValueError(
                "SESSION_STRING не указана в config.py\n"
                "Запустите auth_string_session.py для создания сессии"
            )
        
        # Используем StringSession для надежности
        self.client = TelegramClient(
            StringSession(SESSION_STRING), 
            API_ID, 
            API_HASH
        )
        
        # Подключаемся
        await self.client.connect()
        
        # Проверяем что сессия валидна
        if not await self.client.is_user_authorized():
            await self.client.disconnect()
            raise RuntimeError(
                "Сессия не авторизована!\n"
                "Запустите auth_string_session.py для создания новой сессии"
            )
        
        me = await self.client.get_me()
        print(f"OK - Client started: {me.first_name} (@{me.username or 'no_username'}) [ID:{me.id}]")
    
    async def stop(self):
        """Остановка клиента"""
        if self.client:
            await self.client.disconnect()
            print("Client stopped")
    
    async def send_command(self, bot_username: str, command: str) -> Message:
        """Отправить команду боту и получить ответ"""
        if not bot_username.startswith("@"):
            bot_username = f"@{bot_username}"
        
        print(f"Sending: {command} -> {bot_username}")
        
        # Отправляем команду
        await self.client.send_message(bot_username, command)
        
        # Ждем ответ
        message = await self._wait_for_message(bot_username)
        
        if message:
            self._last_message = message
            print(f"Received: {len(message.text)} chars")
            return message
        else:
            raise TimeoutError(f"No response from {bot_username} in {MESSAGE_TIMEOUT}s")
    
    async def _wait_for_message(self, bot_username: str, timeout: int = MESSAGE_TIMEOUT) -> Optional[Message]:
        """Ожидание сообщения от бота"""
        try:
            # Ждём достаточно времени чтобы бот успел обработать
            await asyncio.sleep(3)
            
            # Получаем последнее сообщение
            messages = await self.client.get_messages(bot_username, limit=1)
            if messages:
                return messages[0]
        except Exception as e:
            print(f"WARNING: Error getting message: {e}")
        
        return None
    
    async def click_button(self, text: str, bot_username: Optional[str] = None) -> Message:
        """Нажать кнопку по тексту"""
        if not self._last_message:
            raise ValueError("No last message. Send command first")
        
        message = self._last_message
        
        if not message.buttons:
            raise ValueError("No buttons in last message")
        
        # Ищем кнопку по тексту
        for row in message.buttons:
            for button in row:
                if button.text == text:
                    print(f"Clicking button: {text}")
                    
                    # Кликаем
                    await button.click()
                    
                    # Задержка после клика
                    await asyncio.sleep(BUTTON_CLICK_DELAY)
                    
                    # Получаем ответ
                    if bot_username:
                        if not bot_username.startswith("@"):
                            bot_username = f"@{bot_username}"
                        new_message = await self._wait_for_message(bot_username)
                    else:
                        # Используем того же бота
                        new_message = await self._wait_for_message(
                            message.sender.username or str(message.sender_id)
                        )
                    
                    if new_message:
                        self._last_message = new_message
                        print(f"Received after click: {len(new_message.text)} chars")
                        return new_message
                    else:
                        raise TimeoutError(f"No response after clicking '{text}'")
        
        # Если кнопка не найдена
        available_buttons = []
        for row in message.buttons:
            available_buttons.extend([btn.text for btn in row])
        
        raise ValueError(
            f"Button '{text}' not found. "
            f"Available: {', '.join(available_buttons)}"
        )
    
    async def get_last_message(self, bot_username: str) -> Optional[Message]:
        """Получить последнее сообщение от бота"""
        if not bot_username.startswith("@"):
            bot_username = f"@{bot_username}"
        
        messages = await self.client.get_messages(bot_username, limit=1)
        return messages[0] if messages else None
    
    def assert_text_in_message(self, text: str, message: Optional[Message] = None):
        """Проверить наличие текста в сообщении"""
        msg = message or self._last_message
        
        if not msg:
            raise ValueError("No message to check")
        
        if text not in msg.text:
            raise AssertionError(
                f"Text '{text}' not found in message.\n"
                f"Message: {msg.text[:200]}..."
            )
        
        print(f"OK - Text found: '{text}'")
    
    def assert_has_buttons(self, button_texts: List[str], message: Optional[Message] = None):
        """Проверить наличие кнопок в сообщении"""
        msg = message or self._last_message
        
        if not msg:
            raise ValueError("No message to check")
        
        if not msg.buttons:
            raise AssertionError("No buttons in message")
        
        # Собираем все тексты кнопок
        available_buttons = []
        for row in msg.buttons:
            available_buttons.extend([btn.text for btn in row])
        
        # Проверяем наличие каждой требуемой кнопки
        for text in button_texts:
            if text not in available_buttons:
                raise AssertionError(
                    f"Button '{text}' not found.\n"
                    f"Available: {', '.join(available_buttons)}"
                )
        
        print(f"OK - All buttons found: {', '.join(button_texts)}")
    
    async def __aenter__(self):
        """Context manager support"""
        await self.start()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager support"""
        await self.stop()
