from __future__ import annotations

from collections.abc import AsyncIterator

import sqlalchemy as sa
import pytest_asyncio
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from field_service.db import models as m
from field_service.db.base import metadata


if not hasattr(SQLiteTypeCompiler, "visit_JSONB"):

    def visit_jsonb(self, type_, **kw):  # type: ignore[override]
        return "JSON"

    SQLiteTypeCompiler.visit_JSONB = visit_jsonb  # type: ignore[attr-defined]


TABLES = [
    m.cities.__table__,
    m.districts.__table__,
    m.streets.__table__,
    m.staff_cities.__table__,
    m.staff_access_codes.__table__,
    m.staff_access_code_cities.__table__,
    m.masters.__table__,
    m.master_invite_codes.__table__,
    m.skills.__table__,  # ✅ Добавлено для test_fixes_stage_1
    m.master_skills.__table__,  # ✅ Добавлено для test_fixes_stage_1
    m.master_districts.__table__,  # ✅ Добавлено для test_fixes_stage_1
    m.offers.__table__,
    m.orders.__table__,
    m.attachments.__table__,
    m.commissions.__table__,
    m.referrals.__table__,
    m.referral_rewards.__table__,
    m.order_status_history.__table__,
    m.settings.__table__,
    m.geocache.__table__,
]


@pytest_asyncio.fixture()
async def async_session() -> AsyncIterator[AsyncSession]:
    engine: AsyncEngine = create_async_engine(
        "sqlite+aiosqlite:///:memory:", future=True
    )
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: sync_conn.execute(
                sa.text("""
                CREATE TABLE IF NOT EXISTS staff_users (
                    id INTEGER PRIMARY KEY,
                    tg_user_id BIGINT,
                    username VARCHAR(64),
                    full_name VARCHAR(160),
                    phone VARCHAR(32),
                    role VARCHAR(10) NOT NULL,
                    is_active BOOLEAN DEFAULT 1 NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    commission_requisites TEXT DEFAULT '{}'
                )
                """)
            )
        )
        await conn.run_sync(
            lambda sync_conn: metadata.create_all(sync_conn, tables=TABLES)
        )
        await conn.execute(sa.text("DROP INDEX IF EXISTS uix_offers__order_accepted_once"))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()
    await engine.dispose()



# ===== Дополнительные фикстуры для E2E тестов =====

@pytest_asyncio.fixture()
async def session(async_session: AsyncSession) -> AsyncSession:
    """Alias для совместимости с test_e2e_escalation_notifications"""
    return async_session


@pytest_asyncio.fixture()
async def sample_city(async_session: AsyncSession) -> m.cities:
    """Создаёт тестовый город"""
    city = m.cities(
        id=1,
        name="Test City",
        timezone="Europe/Moscow",
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
        name="Test District",
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
        name_ru="Электрика",
        name_en="Electrics",
        category="ELECTRICS",
        is_active=True,
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
    sample_skill: m.skills,
) -> m.masters:
    """Создаёт тестового мастера"""
    master = m.masters(
        id=1,
        tg_user_id=123456789,
        city_id=sample_city.id,
        username="test_master",
        full_name="Test Master",
        phone="+7 900 000 00 00",
        is_active=True,
        is_blocked=False,
        verified=True,
        is_on_shift=True,
        has_vehicle=True,
        rating=4.5,
    )
    async_session.add(master)
    await async_session.flush()

    # Привязываем мастера к району
    master_district = m.master_districts(
        master_id=master.id,
        district_id=sample_district.id,
    )
    async_session.add(master_district)

    # Привязываем навык к мастеру
    master_skill = m.master_skills(
        master_id=master.id,
        skill_id=sample_skill.id,
    )
    async_session.add(master_skill)

    await async_session.commit()
    await async_session.refresh(master)
    return master
