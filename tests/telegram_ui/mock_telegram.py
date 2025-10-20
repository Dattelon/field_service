"""
Mock-версия Telegram бота для безопасного тестирования
БЕЗ использования реального Telegram API
"""

from typing import List, Dict, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class MockMessage:
    """Имитация Telegram сообщения"""
    message_id: int
    chat_id: int
    text: str
    date: datetime = field(default_factory=datetime.now)
    buttons: List[List[str]] = field(default_factory=list)
    
    def __repr__(self):
        return f"Message({self.message_id}): {self.text[:50]}..."


@dataclass
class MockUpdate:
    """Имитация Telegram Update"""
    update_id: int
    message: Optional[MockMessage] = None
    callback_query: Optional[Dict] = None


class MockTelegramBot:
    """
    Mock-версия Telegram бота для тестирования
    Имитирует поведение aiogram бота без реального API
    """
    
    def __init__(self):
        self.messages: List[MockMessage] = []
        self.callbacks: List[Dict] = []
        self._message_id_counter = 1
        self._handlers: Dict[str, Callable] = {}
        
    async def send_message(
        self,
        chat_id: int,
        text: str,
        reply_markup: Optional[Dict] = None
    ) -> MockMessage:
        """Отправка сообщения"""
        buttons = self._parse_reply_markup(reply_markup) if reply_markup else []
        
        message = MockMessage(
            message_id=self._message_id_counter,
            chat_id=chat_id,
            text=text,
            buttons=buttons
        )
        
        self._message_id_counter += 1
        self.messages.append(message)
        
        return message
    
    async def edit_message_text(
        self,
        text: str,
        chat_id: int,
        message_id: int,
        reply_markup: Optional[Dict] = None
    ) -> MockMessage:
        """Редактирование сообщения"""
        # Находим существующее сообщение
        for msg in self.messages:
            if msg.message_id == message_id and msg.chat_id == chat_id:
                msg.text = text
                if reply_markup:
                    msg.buttons = self._parse_reply_markup(reply_markup)
                return msg
        
        # Если не нашли, создаём новое
        return await self.send_message(chat_id, text, reply_markup)
    
    async def answer_callback_query(self, callback_query_id: str, text: Optional[str] = None):
        """Ответ на callback query"""
        self.callbacks.append({
            "callback_query_id": callback_query_id,
            "answer_text": text
        })
    
    def get_last_message(self, chat_id: Optional[int] = None) -> Optional[MockMessage]:
        """Получить последнее сообщение"""
        if chat_id is not None:
            chat_messages = [m for m in self.messages if m.chat_id == chat_id]
            return chat_messages[-1] if chat_messages else None
        return self.messages[-1] if self.messages else None
    
    def get_all_messages(self, chat_id: Optional[int] = None) -> List[MockMessage]:
        """Получить все сообщения"""
        if chat_id is not None:
            return [m for m in self.messages if m.chat_id == chat_id]
        return self.messages.copy()
    
    def clear_messages(self):
        """Очистить все сообщения"""
        self.messages.clear()
        self.callbacks.clear()
    
    def _parse_reply_markup(self, reply_markup: Dict) -> List[List[str]]:
        """Парсинг кнопок из reply_markup"""
        buttons = []
        
        if isinstance(reply_markup, dict):
            # InlineKeyboardMarkup
            if "inline_keyboard" in reply_markup:
                for row in reply_markup["inline_keyboard"]:
                    button_row = []
                    for button in row:
                        if "text" in button:
                            button_row.append(button["text"])
                    if button_row:
                        buttons.append(button_row)
            
            # ReplyKeyboardMarkup
            elif "keyboard" in reply_markup:
                for row in reply_markup["keyboard"]:
                    button_row = []
                    for button in row:
                        if isinstance(button, str):
                            button_row.append(button)
                        elif isinstance(button, dict) and "text" in button:
                            button_row.append(button["text"])
                    if button_row:
                        buttons.append(button_row)
        
        return buttons
    
    def register_handler(self, command: str, handler: Callable):
        """Регистрация обработчика команды"""
        self._handlers[command] = handler
    
    async def simulate_command(self, chat_id: int, command: str, **kwargs) -> MockMessage:
        """Симуляция команды от пользователя"""
        if command in self._handlers:
            # Создаём mock update
            message = MockMessage(
                message_id=self._message_id_counter,
                chat_id=chat_id,
                text=command
            )
            self._message_id_counter += 1
            
            update = MockUpdate(
                update_id=len(self.messages),
                message=message
            )
            
            # Вызываем handler
            await self._handlers[command](update, **kwargs)
            
            return self.get_last_message(chat_id)
        else:
            return await self.send_message(chat_id, f"Неизвестная команда: {command}")
    
    async def simulate_button_click(
        self,
        chat_id: int,
        message_id: int,
        button_text: str
    ) -> Optional[MockMessage]:
        """Симуляция нажатия на кнопку"""
        # Находим сообщение с кнопками
        message = None
        for msg in self.messages:
            if msg.message_id == message_id and msg.chat_id == chat_id:
                message = msg
                break
        
        if not message or not message.buttons:
            return None
        
        # Проверяем есть ли такая кнопка
        button_found = False
        for row in message.buttons:
            if button_text in row:
                button_found = True
                break
        
        if not button_found:
            return None
        
        # Создаём callback query
        callback_query_id = f"cbq_{len(self.callbacks)}"
        
        # Если есть зарегистрированный handler для этой кнопки
        handler_key = f"button:{button_text}"
        if handler_key in self._handlers:
            update = MockUpdate(
                update_id=len(self.messages),
                callback_query={
                    "id": callback_query_id,
                    "message": message,
                    "data": button_text,
                    "from": {"id": chat_id}
                }
            )
            
            await self._handlers[handler_key](update)
        
        return self.get_last_message(chat_id)
    
    def assert_last_message_contains(self, text: str, chat_id: Optional[int] = None):
        """Проверка что последнее сообщение содержит текст"""
        message = self.get_last_message(chat_id)
        assert message is not None, "Нет сообщений"
        assert text in message.text, f"Текст '{text}' не найден в сообщении: {message.text}"
    
    def assert_has_buttons(self, button_texts: List[str], chat_id: Optional[int] = None):
        """Проверка наличия кнопок"""
        message = self.get_last_message(chat_id)
        assert message is not None, "Нет сообщений"
        assert message.buttons, "У сообщения нет кнопок"
        
        all_buttons = [btn for row in message.buttons for btn in row]
        for text in button_texts:
            assert text in all_buttons, f"Кнопка '{text}' не найдена. Есть: {all_buttons}"
    
    def print_conversation(self, chat_id: Optional[int] = None):
        """Вывести всю переписку (для отладки)"""
        messages = self.get_all_messages(chat_id)
        print("\n" + "="*60)
        print(f"  CONVERSATION {'(chat_id=' + str(chat_id) + ')' if chat_id else '(all)'}")
        print("="*60)
        
        for msg in messages:
            print(f"\n[{msg.date.strftime('%H:%M:%S')}] Message {msg.message_id} → Chat {msg.chat_id}")
            print(f"  Text: {msg.text}")
            if msg.buttons:
                print(f"  Buttons:")
                for i, row in enumerate(msg.buttons):
                    print(f"    Row {i}: {row}")
        
        print("="*60 + "\n")


# ============================================
# HELPER FUNCTIONS
# ============================================

def create_mock_bot() -> MockTelegramBot:
    """Фабрика для создания mock бота"""
    return MockTelegramBot()


def create_test_chat_id() -> int:
    """Генерация тестового chat_id"""
    import random
    return random.randint(100000, 999999)
