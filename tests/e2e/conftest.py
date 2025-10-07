"""
CONFTEST: Фикстуры и моки для E2E тестов
=========================================

Этот файл содержит:
1. Моки ботов (aiogram MockedBot)
2. Моки БД (asyncpg)
3. Тестовые данные (фабрики)
4. Настройки pytest
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import asyncpg


# ============================================================================
# PYTEST CONFIGURATION
# ============================================================================

def pytest_configure(config):
    """Настройка pytest"""
    config.addinivalue_line("markers", "e2e: End-to-end тесты с полным флоу")
    config.addinivalue_line("markers", "critical: Критичные тесты для CI/CD")
    config.addinivalue_line("markers", "slow: Медленные тесты (>30s)")


@pytest.fixture(scope="session")
def event_loop():
    """Создание event loop для async тестов"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# ============================================================================
# DATABASE MOCKS
# ============================================================================

class MockDatabase:
    """Мок PostgreSQL базы данных"""
    
    def __init__(self):
        self.storage = {
            "orders": {},
            "masters": {},
            "clients": {},
            "transactions": {},
            "ratings": {},
            "order_assignment_attempts": {},
            "admin_queue": {},
            "cities": {},
            "master_notifications": {},
            "referrals": {},
            "settings": {}
        }
        self.auto_increment = {
            "orders": 5000,
            "transactions": 1000,
            "ratings": 1,
            "order_assignment_attempts": 1
        }
    
    async def fetchrow(self, query: str, *args) -> Optional[Dict]:
        """Эмуляция SELECT ... LIMIT 1"""
        
        # Простой парсер запросов (можно улучшить)
        if "orders" in query.lower():
            if "ORDER BY id DESC" in query:
                orders = list(self.storage["orders"].values())
                return orders[-1] if orders else None
            
            # WHERE id = $1
            if args and len(args) > 0:
                order_id = args[0]
                return self.storage["orders"].get(order_id)
        
        elif "masters" in query.lower():
            # Топ мастера по рейтингу
            if "ORDER BY rating DESC" in query:
                masters = sorted(
                    self.storage["masters"].values(),
                    key=lambda x: x.get('rating', 0),
                    reverse=True
                )
                return masters[0] if masters else None
        
        elif "cities" in query.lower():
            if "Рига" in query or (args and "Рига" in str(args)):
                return {"id": 1, "name": "Рига", "coordinates": {"lat": 56.9496, "lon": 24.1052}}
        
        return None
    
    async def fetch(self, query: str, *args) -> List[Dict]:
        """Эмуляция SELECT ... (множество строк)"""
        
        if "masters" in query.lower() and "ORDER BY rating" in query:
            # Топ-2 мастера
            masters = sorted(
                self.storage["masters"].values(),
                key=lambda x: x.get('rating', 0),
                reverse=True
            )
            
            # LIMIT 2
            if "LIMIT 2" in query:
                return masters[:2]
            
            return masters
        
        elif "orders" in query.lower():
            return list(self.storage["orders"].values())
        
        return []
    
    async def execute(self, query: str, *args) -> str:
        """Эмуляция INSERT/UPDATE/DELETE"""
        
        query_lower = query.lower()
        
        if "insert into orders" in query_lower:
            # Парсинг INSERT
            order_id = self._get_next_id("orders")
            self.storage["orders"][order_id] = {
                "id": order_id,
                "status": "searching",
                "created_at": datetime.now(),
                **(args[0] if args else {})
            }
            return f"INSERT 0 1"
        
        elif "update orders" in query_lower:
            # UPDATE orders SET ... WHERE id = $1
            if args and len(args) >= 2:
                order_id = args[-1]  # Последний аргумент обычно WHERE id
                if order_id in self.storage["orders"]:
                    self.storage["orders"][order_id].update(args[0] if isinstance(args[0], dict) else {})
            return f"UPDATE 1"
        
        elif "insert into transactions" in query_lower:
            txn_id = self._get_next_id("transactions")
            self.storage["transactions"][txn_id] = {
                "id": txn_id,
                "created_at": datetime.now(),
                **(args[0] if args else {})
            }
            return f"INSERT 0 1"
        
        return "OK"
    
    def _get_next_id(self, table: str) -> int:
        """Автоинкремент ID"""
        current = self.auto_increment.get(table, 1)
        self.auto_increment[table] = current + 1
        return current
    
    def reset(self):
        """Очистка между тестами"""
        self.__init__()
    
    # Утилиты для тестов
    def insert_test_order(self, **kwargs):
        """Вставка тестового заказа"""
        order_id = self._get_next_id("orders")
        default = {
            "id": order_id,
            "client_id": 1000,
            "city_id": 1,
            "status": "searching",
            "address": "Test Address",
            "coordinates": {"lat": 56.9496, "lon": 24.1052},
            "created_at": datetime.now()
        }
        default.update(kwargs)
        self.storage["orders"][order_id] = default
        return default
    
    def insert_test_master(self, **kwargs):
        """Вставка тестового мастера"""
        master_id = kwargs.get('id', self._get_next_id("masters"))
        default = {
            "id": master_id,
            "name": f"Тестовый мастер {master_id}",
            "phone": f"+371{master_id}",
            "city_id": 1,
            "rating": 4.5,
            "is_active": True,
            "on_break": False,
            "is_blocked": False,
            "total_orders": 50,
            "cancellation_count": 0,
            "balance": 0.0
        }
        default.update(kwargs)
        self.storage["masters"][master_id] = default
        return default


@pytest.fixture
async def db():
    """Фикстура мок-БД"""
    database = MockDatabase()
    
    # Предзагрузка тестовых данных
    database.insert_test_master(id=2001, name="Иван", rating=4.9, phone="+371111111")
    database.insert_test_master(id=2002, name="Пётр", rating=4.7, phone="+371222222")
    database.insert_test_master(id=2003, name="Алексей", rating=4.95, phone="+371333333")
    database.insert_test_master(id=2004, name="Дмитрий", rating=4.88, phone="+371444444")
    
    database.storage["cities"][1] = {
        "id": 1,
        "name": "Рига",
        "coordinates": {"lat": 56.9496, "lon": 24.1052}
    }
    
    yield database
    
    # Очистка после теста
    database.reset()


# ============================================================================
# BOT MOCKS
# ============================================================================

class MockMessage:
    """Мок сообщения Telegram"""
    
    def __init__(self, message_id: int, from_user_id: int, text: str, **kwargs):
        self.message_id = message_id
        self.from_user = MockUser(from_user_id)
        self.chat = MockChat(from_user_id)
        self.text = text
        self.photo = kwargs.get('photo')
        self.location = kwargs.get('location')


class MockUser:
    """Мок пользователя Telegram"""
    
    def __init__(self, user_id: int):
        self.id = user_id
        self.is_bot = False
        self.first_name = f"User{user_id}"


class MockChat:
    """Мок чата Telegram"""
    
    def __init__(self, chat_id: int):
        self.id = chat_id
        self.type = "private"


class MockBot:
    """Мок Telegram бота"""
    
    def __init__(self, bot_type: str):
        self.bot_type = bot_type  # "client", "master", "admin"
        self.sent_messages = []
        self.message_counter = 1
    
    async def send_message(
        self,
        chat_id: int,
        text: str,
        reply_markup=None,
        **kwargs
    ):
        """Отправка сообщения"""
        message = {
            "to": chat_id,
            "text": text,
            "has_buttons": reply_markup is not None,
            "timestamp": datetime.now()
        }
        self.sent_messages.append(message)
        return MockMessage(self.message_counter, chat_id, text)
    
    async def send_photo(self, chat_id: int, photo, **kwargs):
        """Отправка фото"""
        message = {
            "to": chat_id,
            "type": "photo",
            "photo": photo,
            "timestamp": datetime.now()
        }
        self.sent_messages.append(message)
    
    async def edit_message_text(self, text: str, chat_id: int, message_id: int, **kwargs):
        """Редактирование сообщения"""
        pass
    
    async def answer_callback_query(self, callback_query_id: str, **kwargs):
        """Ответ на callback"""
        pass
    
    # Утилиты для тестов
    def get_sent_messages(self, to_user_id: Optional[int] = None) -> List[Dict]:
        """Получить отправленные сообщения"""
        if to_user_id is None:
            return self.sent_messages
        return [m for m in self.sent_messages if m['to'] == to_user_id]
    
    def get_last_message(self, user_id: int) -> Optional[Dict]:
        """Последнее сообщение пользователю"""
        messages = self.get_sent_messages(user_id)
        return messages[-1] if messages else None
    
    def reset(self):
        """Очистка между тестами"""
        self.sent_messages = []
        self.message_counter = 1


@pytest.fixture
async def bot_client():
    """Фикстура бота клиента"""
    bot = MockBot("client")
    yield bot
    bot.reset()


@pytest.fixture
async def bot_master():
    """Фикстура бота мастера"""
    bot = MockBot("master")
    yield bot
    bot.reset()


@pytest.fixture
async def bot_admin():
    """Фикстура бота админа"""
    bot = MockBot("admin")
    yield bot
    bot.reset()


# ============================================================================
# FSM MOCKS
# ============================================================================

class MockFSMContext:
    """Мок FSM контекста aiogram"""
    
    def __init__(self):
        self.state = None
        self.data = {}
    
    async def get_state(self) -> Optional[str]:
        return self.state
    
    async def set_state(self, state: str):
        self.state = state
    
    async def get_data(self) -> Dict:
        return self.data
    
    async def update_data(self, **kwargs):
        self.data.update(kwargs)
    
    async def clear(self):
        self.state = None
        self.data = {}


@pytest.fixture
def fsm_context():
    """Фикстура FSM контекста"""
    return MockFSMContext()


# ============================================================================
# TEST DATA FACTORIES
# ============================================================================

class TestDataFactory:
    """Фабрика тестовых данных"""
    
    @staticmethod
    def create_order_data(**overrides) -> Dict:
        """Создать данные заказа"""
        default = {
            "client_id": 1000,
            "city_id": 1,
            "address": "Улица Бривибас 1, Рига",
            "coordinates": {"lat": 56.9496, "lon": 24.1052},
            "visit_time": datetime.now() + timedelta(days=1),
            "description": "Тестовое описание проблемы",
            "status": "searching"
        }
        default.update(overrides)
        return default
    
    @staticmethod
    def create_master_data(**overrides) -> Dict:
        """Создать данные мастера"""
        default = {
            "name": "Тестовый Мастер",
            "phone": "+371000000",
            "city_id": 1,
            "rating": 4.5,
            "is_active": True,
            "on_break": False
        }
        default.update(overrides)
        return default


@pytest.fixture
def test_data():
    """Фикстура фабрики данных"""
    return TestDataFactory()


# ============================================================================
# MOCK HELPERS
# ============================================================================

def create_callback_update(user_id: int, callback_data: str, message_id: int = 1):
    """Создать Update с callback query"""
    # Упрощённо для тестов
    return {
        "callback_query": {
            "id": "test_callback",
            "from": {"id": user_id},
            "data": callback_data,
            "message": {"message_id": message_id, "chat": {"id": user_id}}
        }
    }


def create_message_update(user_id: int, text: str):
    """Создать Update с сообщением"""
    return {
        "message": {
            "message_id": 1,
            "from": {"id": user_id, "is_bot": False, "first_name": f"User{user_id}"},
            "chat": {"id": user_id, "type": "private"},
            "text": text
        }
    }


# ============================================================================
# ASYNC HELPERS
# ============================================================================

async def wait_for_condition(condition, timeout: float = 5.0, interval: float = 0.1):
    """Ждать пока условие станет True"""
    elapsed = 0.0
    while elapsed < timeout:
        if condition():
            return True
        await asyncio.sleep(interval)
        elapsed += interval
    return False


# ============================================================================
# CLEANUP
# ============================================================================

@pytest.fixture(autouse=True)
async def cleanup_after_test():
    """Автоматическая очистка после каждого теста"""
    yield
    # Очистка выполняется в фикстурах через reset()
