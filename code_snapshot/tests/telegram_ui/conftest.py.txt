"""
Pytest конфигурация для E2E тестов через Telethon
"""
import asyncio
import pytest
from pathlib import Path
import sys

# Добавляем путь к проекту
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import text
from tests.telegram_ui.bot_client import BotTestClient
from tests.telegram_ui.config import MASTER_BOT_USERNAME, ADMIN_BOT_USERNAME


# ==========================================
# DATABASE CONFIGURATION
# ==========================================
DATABASE_URL = "postgresql+asyncpg://fs_user:fs_password@localhost:5439/field_service"

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True
)

SessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)


# ==========================================
# PYTEST CONFIGURATION
# ==========================================
def pytest_configure(config):
    """Регистрация маркеров"""
    config.addinivalue_line("markers", "p0: Priority 0 - Critical tests")
    config.addinivalue_line("markers", "p1: Priority 1 - Important tests")
    config.addinivalue_line("markers", "p2: Priority 2 - Normal tests")
    config.addinivalue_line("markers", "p3: Priority 3 - Optional tests")
    config.addinivalue_line("markers", "slow: Slow tests")


# ==========================================
# DATABASE FIXTURES
# ==========================================
@pytest.fixture(scope="session")
async def db_engine():
    """Database engine for the entire test session"""
    yield engine
    await engine.dispose()


@pytest.fixture
async def db_session():
    """Database session for a single test"""
    async with SessionLocal() as session:
        yield session


@pytest.fixture
async def clean_db(db_session: AsyncSession):
    """
    Очистка БД перед тестом
    Удаляет все тестовые данные, но сохраняет:
    - Города и районы
    - Навыки
    - Админов
    - Настройки
    """
    # Очистка в правильном порядке (из-за FK)
    tables = [
        "attachments",
        "order_status_history",
        "commission_deadline_notifications",
        "commissions",
        "offers",
        "order_autoclose_queue",
        "orders",
        "master_skills",
        "master_districts",
        "master_invite_codes",
        "referral_rewards",
        "referrals",
        "masters",
        "notifications_outbox",
        "distribution_metrics",
    ]
    
    for table in tables:
        await db_session.execute(text(f"DELETE FROM {table}"))
    
    await db_session.commit()
    
    # Сброс автоинкрементов
    sequences = [
        "orders_id_seq",
        "masters_id_seq",
        "offers_id_seq",
        "commissions_id_seq",
    ]
    
    for seq in sequences:
        await db_session.execute(text(f"ALTER SEQUENCE {seq} RESTART WITH 1"))
    
    await db_session.commit()
    
    yield


# ==========================================
# TELETHON FIXTURES
# ==========================================
@pytest.fixture
async def telegram_client():
    """
    Telethon клиент для взаимодействия с ботами
    Автоматически подключается и отключается
    """
    async with BotTestClient() as client:
        yield client


@pytest.fixture
async def admin_session(telegram_client: BotTestClient):
    """
    Сессия админа в админ-боте
    Отправляет /start и возвращает клиент готовый к работе
    """
    # Запускаем бота
    await telegram_client.send_command(ADMIN_BOT_USERNAME, "/start")
    
    # Даем время на загрузку меню
    await asyncio.sleep(1)
    
    yield telegram_client


# ==========================================
# HELPER FIXTURES
# ==========================================
@pytest.fixture
def get_db_now():
    """
    Helper для получения текущего времени БД
    Использовать для синхронизации времени Python и PostgreSQL
    """
    async def _get_now(session: AsyncSession):
        result = await session.execute(text("SELECT NOW()"))
        return result.scalar()
    return _get_now


# ==========================================
# MARKERS FOR TEST ORGANIZATION
# ==========================================
"""
Использование маркеров:

@pytest.mark.p0
async def test_critical_functionality():
    # Критический функционал
    
@pytest.mark.p1
async def test_important_functionality():
    # Важный функционал
    
@pytest.mark.slow
async def test_long_running():
    # Долгий тест
"""


# ==========================================
# CONFIGURATION
# ==========================================
@pytest.fixture(scope="session", autouse=True)
def configure_asyncio():
    """Настройка asyncio для pytest"""
    # Уже настроено в pytest.ini: asyncio_mode = auto
    pass
