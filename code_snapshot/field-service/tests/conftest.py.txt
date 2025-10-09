from __future__ import annotations

import os
from collections.abc import AsyncIterator

import sqlalchemy as sa
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from field_service.db import models as m
from field_service.db.base import metadata


# ✅ STEP 2: Используем PostgreSQL вместо SQLite для тестов
# Это обеспечивает полную совместимость и точность тестирования

# Читаем DATABASE_URL из переменной окружения или используем дефолтный
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://fs_user:fs_password@localhost:5439/field_service_test"
)

TABLES = [
    m.cities.__table__,
    m.districts.__table__,
    m.streets.__table__,
    m.staff_cities.__table__,
    m.staff_access_codes.__table__,
    m.staff_access_code_cities.__table__,
    m.masters.__table__,
    m.master_invite_codes.__table__,
    m.skills.__table__,
    m.master_skills.__table__,
    m.master_districts.__table__,
    m.offers.__table__,
    m.orders.__table__,
    m.attachments.__table__,
    m.commissions.__table__,
    m.commission_deadline_notifications.__table__,
    m.referrals.__table__,
    m.referral_rewards.__table__,
    m.order_status_history.__table__,
    m.settings.__table__,
    m.geocache.__table__,
    m.admin_audit_log.__table__,
    m.notifications_outbox.__table__,
    m.order_autoclose_queue.__table__,
    m.distribution_metrics.__table__,
]


@pytest_asyncio.fixture(scope="session")
async def engine() -> AsyncIterator[AsyncEngine]:
    """
    ✅ Session-scoped engine для PostgreSQL.
    
    Создаётся один раз на всю сессию тестов.
    """
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
    )
    
    # Создаём все таблицы один раз
    async with engine.begin() as conn:
        # Создаём ENUM types
        await conn.execute(sa.text("DROP TYPE IF EXISTS staff_role CASCADE"))
        await conn.execute(sa.text("""
            CREATE TYPE staff_role AS ENUM ('GLOBAL_ADMIN', 'CITY_ADMIN', 'LOGIST')
        """))
        
        # Пересоздаём staff_users вручную (не через metadata)
        await conn.execute(sa.text("DROP TABLE IF EXISTS staff_users CASCADE"))
        await conn.execute(sa.text("""
            CREATE TABLE staff_users (
                id SERIAL PRIMARY KEY,
                tg_user_id BIGINT UNIQUE,
                username VARCHAR(64),
                full_name VARCHAR(160),
                phone VARCHAR(32),
                role staff_role NOT NULL,
                is_active BOOLEAN DEFAULT TRUE NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                commission_requisites TEXT DEFAULT '{}'
            )
        """))
        
        # Создаём остальные таблицы через metadata
        await conn.run_sync(metadata.create_all, tables=TABLES)
    
    yield engine
    
    # Очищаем после всех тестов
    async with engine.begin() as conn:
        await conn.execute(sa.text("DROP TABLE IF EXISTS staff_users CASCADE"))
        await conn.run_sync(metadata.drop_all, tables=TABLES)
    
    await engine.dispose()


@pytest_asyncio.fixture()
async def async_session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """
    ✅ Function-scoped сессия для каждого теста.
    
    Каждый тест получает чистую БД благодаря TRUNCATE CASCADE.
    """
    session_factory = async_sessionmaker(
        engine,
        expire_on_commit=False,
        class_=AsyncSession
    )
    
    async with session_factory() as session:
        # Очищаем все таблицы перед тестом
        await _clean_database(session)
        
        yield session
        
        # Откатываем после теста
        await session.rollback()


async def _clean_database(session: AsyncSession) -> None:
    """
    ✅ Очищает все таблицы с TRUNCATE CASCADE.
    
    Быстрее чем DROP/CREATE и сохраняет структуру.
    """
    tables_to_clean = [
        "commission_deadline_notifications",
        "order_status_history",
        "attachments", 
        "offers",
        "commissions",
        "referrals",
        "referral_rewards",
        "notifications_outbox",
        "order_autoclose_queue",
        "distribution_metrics",
        "orders",
        "master_districts",
        "master_skills",
        "master_invite_codes",
        "masters",
        "staff_access_code_cities",
        "staff_access_codes",
        "staff_cities",
        "staff_users",
        "streets",
        "districts",
        "cities",
        "skills",
        "settings",
        "geocache",
        "admin_audit_log",
    ]
    
    try:
        for table in tables_to_clean:
            await session.execute(sa.text(f"TRUNCATE TABLE {table} CASCADE"))
        await session.commit()
    except Exception:
        await session.rollback()
        # Fallback на DELETE если TRUNCATE не сработал
        for table in tables_to_clean:
            try:
                await session.execute(sa.text(f"DELETE FROM {table}"))
            except Exception:
                pass
        await session.commit()


# ===== Алиасы для совместимости =====

@pytest_asyncio.fixture()
async def session(async_session: AsyncSession) -> AsyncSession:
    """Alias для совместимости с существующими тестами"""
    return async_session


# ===== Стандартные фикстуры для тестов =====

@pytest_asyncio.fixture()
async def sample_city(async_session: AsyncSession) -> m.cities:
    """Создаёт тестовый город"""
    city = m.cities(
        id=1,
        name="Test City",
        timezone="Europe/Moscow"
    )
    async_session.add(city)
    await async_session.commit()
    await async_session.refresh(city)
    return city


@pytest_asyncio.fixture()
async def sample_district(async_session: AsyncSession, sample_city: m.cities) -> m.districts:
    """Создаёт тестовый район"""
    district = m.districts(
        id=1,
        city_id=sample_city.id,
        name="Test District"
    )
    async_session.add(district)
    await async_session.commit()
    await async_session.refresh(district)
    return district


@pytest_asyncio.fixture()
async def sample_skill(async_session: AsyncSession) -> m.skills:
    """Создаёт тестовый навык"""
    skill = m.skills(
        id=1,
        code="ELEC",
        name="Electrician",
        is_active=True
    )
    async_session.add(skill)
    await async_session.commit()
    await async_session.refresh(skill)
    return skill


@pytest_asyncio.fixture()
async def sample_master(
    async_session: AsyncSession,
    sample_city: m.cities,
    sample_district: m.districts,
    sample_skill: m.skills
) -> m.masters:
    """Создаёт тестового мастера с навыком и районом"""
    master = m.masters(
        tg_user_id=123456789,
        full_name="Test Master",
        city_id=sample_city.id,
        is_active=True,
        is_blocked=False,
        verified=True,
        is_on_shift=True,
        has_vehicle=True,
        rating=4.5,
    )
    async_session.add(master)
    await async_session.flush()
    
    # Привязываем навык
    master_skill = m.master_skills(master_id=master.id, skill_id=sample_skill.id)
    async_session.add(master_skill)
    
    # Привязываем район
    master_district = m.master_districts(
        master_id=master.id,
        district_id=sample_district.id
    )
    async_session.add(master_district)
    
    await async_session.commit()
    await async_session.refresh(master)
    return master
