"""
Helper-класс для работы с Telegram-ботами в тестах
Упрощает отправку команд, клики по кнопкам и проверку ответов
"""

import asyncio
from typing import Optional, List
from telethon import TelegramClient, events
from telethon.tl.types import Message, KeyboardButton, KeyboardButtonCallback
from tests.telegram_ui.config import (
    API_ID, API_HASH, SESSION_FILE,
    MESSAGE_TIMEOUT, BUTTON_CLICK_DELAY
)


class BotTestClient:
    """Клиент для тестирования Telegram-ботов"""
    
    def __init__(self):
        self.client: Optional[TelegramClient] = None
        self._last_message: Optional[Message] = None
    
    async def start(self):
        """Запуск клиента"""
        if not SESSION_FILE.exists():
            raise FileNotFoundError(
                f"Файл сессии не найден: {SESSION_FILE}\n"
                "Запустите setup_client.py для первичной авторизации"
            )
        
        # TelegramClient автоматически добавляет .session, передаём путь БЕЗ расширения
        session_name = str(SESSION_FILE).replace('.session', '')
        self.client = TelegramClient(session_name, API_ID, API_HASH)
        
        # Подключаемся без интерактивного запроса (сессия уже существует)
        await self.client.connect()
        
        # Проверяем что сессия валидна
        if not await self.client.is_user_authorized():
            await self.client.disconnect()
            raise RuntimeError(
                "Сессия не авторизована или устарела!\n"
                "Запустите setup_client.py для создания новой сессии"
            )
        
        me = await self.client.get_me()
        print(f"✅ Клиент запущен: {me.first_name} (@{me.username or 'no_username'})")
    
    async def stop(self):
        """Остановка клиента"""
        if self.client:
            await self.client.disconnect()
            print("🛑 Клиент остановлен")
    
    async def send_command(self, bot_username: str, command: str) -> Message:
        """Отправить команду боту и получить ответ"""
        if not bot_username.startswith("@"):
            bot_username = f"@{bot_username}"
        
        print(f"📤 Отправляем: {command} -> {bot_username}")
        
        # Отправляем команду
        await self.client.send_message(bot_username, command)
        
        # Ждем ответ
        message = await self._wait_for_message(bot_username)
        
        if message:
            self._last_message = message
            print(f"📥 Получен ответ ({len(message.text)} символов)")
            return message
        else:
            raise TimeoutError(f"Не получен ответ от {bot_username} за {MESSAGE_TIMEOUT}с")
    
    async def _wait_for_message(self, bot_username: str, timeout: int = MESSAGE_TIMEOUT) -> Optional[Message]:
        """Ожидание сообщения от бота"""
        try:
            # Сначала ждём достаточно времени чтобы бот успел обработать и ответить
            await asyncio.sleep(3)  # Увеличиваем задержку для надёжности
            
            # Получаем последнее сообщение
            messages = await self.client.get_messages(bot_username, limit=1)
            if messages:
                return messages[0]
        except Exception as e:
            print(f"⚠️ Ошибка при получении сообщения: {e}")
        
        return None
    
    async def click_button(self, text: str, bot_username: Optional[str] = None) -> Message:
        """Нажать кнопку по тексту"""
        if not self._last_message:
            raise ValueError("Нет последнего сообщения. Сначала отправьте команду")
        
        message = self._last_message
        
        if not message.buttons:
            raise ValueError("В последнем сообщении нет кнопок")
        
        # Ищем кнопку по тексту
        for row in message.buttons:
            for button in row:
                if button.text == text:
                    print(f"🔘 Нажимаем кнопку: {text}")
                    
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
                        print(f"📥 Получен ответ после клика ({len(new_message.text)} символов)")
                        return new_message
                    else:
                        raise TimeoutError(f"Не получен ответ после клика по кнопке '{text}'")
        
        # Если кнопка не найдена
        available_buttons = []
        for row in message.buttons:
            available_buttons.extend([btn.text for btn in row])
        
        raise ValueError(
            f"Кнопка '{text}' не найдена. "
            f"Доступные кнопки: {', '.join(available_buttons)}"
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
            raise ValueError("Нет сообщения для проверки")
        
        if text not in msg.text:
            raise AssertionError(
                f"Текст '{text}' не найден в сообщении.\n"
                f"Сообщение: {msg.text[:200]}..."
            )
        
        print(f"✅ Текст найден: '{text}'")
    
    def assert_has_buttons(self, button_texts: List[str], message: Optional[Message] = None):
        """Проверить наличие кнопок в сообщении"""
        msg = message or self._last_message
        
        if not msg:
            raise ValueError("Нет сообщения для проверки")
        
        if not msg.buttons:
            raise AssertionError("В сообщении нет кнопок")
        
        # Собираем все тексты кнопок
        available_buttons = []
        for row in msg.buttons:
            available_buttons.extend([btn.text for btn in row])
        
        # Проверяем наличие каждой требуемой кнопки
        for text in button_texts:
            if text not in available_buttons:
                raise AssertionError(
                    f"Кнопка '{text}' не найдена.\n"
                    f"Доступные кнопки: {', '.join(available_buttons)}"
                )
        
        print(f"✅ Все кнопки найдены: {', '.join(button_texts)}")
    
    async def __aenter__(self):
        """Context manager support"""
        await self.start()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager support"""
        await self.stop()
