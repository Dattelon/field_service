# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import AsyncIterator

import sqlalchemy as sa
import pytest_asyncio
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm.attributes import set_committed_value
from sqlalchemy.pool import NullPool

from field_service.db import models as m
from field_service.db.base import metadata
from field_service.db import session as session_module

# --- Windows совместимость вывода и цикла ---
if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
try:
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    if hasattr(sys.stdout, "reconfigure"):
        try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception: pass
    if hasattr(sys.stderr, "reconfigure"):
        try: sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception: pass
except Exception:
    pass

# --- Настройки БД тестов ---
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://fs_user:fs_password@localhost:5439/field_service_test",
)

# --- Патченая AsyncSession для предотвращения устаревания объектов ---
class PatchedAsyncSession(AsyncSession):
    """AsyncSession variant that preserves PK on expire_all and refreshes sensitive rows."""

    def expire_all(self) -> None:
        snapshot: list[tuple[object, tuple, tuple]] = []
        for obj in list(self.identity_map.values()):
            state = sa.inspect(obj)
            if state.identity is None:
                continue
            snapshot.append((obj, state.mapper.primary_key, state.identity))
        super().expire_all()
        for obj, pk_cols, identity in snapshot:
            for column, value in zip(pk_cols, identity):
                set_committed_value(obj, column.key, value)

    async def get(self, entity, ident, **kw):  # type: ignore[override]
        obj = await super().get(entity, ident, **kw)
        # свежие данные для часто изменяемых сущностей
        try:
            if obj is not None and (entity is m.notifications_outbox or entity is m.orders):
                await super().refresh(obj)
        except Exception:
            pass
        return obj


# --- Единый engine на сессию тестов + патч SessionLocal на тестовый engine ---
_patched_engine: AsyncEngine = create_async_engine(
    TEST_DATABASE_URL,
    echo=False,
    future=True,
    poolclass=NullPool,  # избегаем перекрёстного переиспользования коннектов между тестами
)

# ВАЖНО: прямо тут перенаправляем приложение на тестовый engine/SessionLocal,
# чтобы код, который импортирует SessionLocal напрямую, уже смотрел в тестовую БД.
session_module.engine = _patched_engine
session_module.SessionLocal = async_sessionmaker(
    bind=_patched_engine,
    expire_on_commit=False,
    autoflush=False,
    class_=PatchedAsyncSession,
)

# Таблицы, которые должны существовать (включая служебные, часто встречаются в тестах)
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

_DB_INITIALIZED = False


@pytest_asyncio.fixture(scope="session")
async def engine() -> AsyncIterator[AsyncEngine]:
    """
    Session-scoped engine. Схема БД должна быть уже создана миграциями Alembic.
    Никаких DDL операций не выполняем - используем механизм ROLLBACK для очистки.
    """
    # Создаём совместимые колонки для тестов
    from field_service.db.session import _ensure_testing_ddl
    await _ensure_testing_ddl()
    
    yield _patched_engine


# -------- ГЛАВНОЕ: Функциональная фикстура с полной транзакционной изоляцией --------
@pytest_asyncio.fixture(scope="function")
async def async_session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """
    Выдаём AsyncSession, связанный с ОДНИМ соединением и большим транзактом,
    внутри которого автоперезапускаем SAVEPOINT после каждого commit().
    Ни TRUNCATE, ни DELETE не используются.
    """
    async with engine.connect() as conn:
        # Большая транзакция уровня соединения
        outer = await conn.begin()

        # Делаем factory, привязанный именно к ЭТОМУ соединению
        Session = async_sessionmaker(
            bind=conn,
            expire_on_commit=False,
            autoflush=False,
            class_=PatchedAsyncSession,
        )

        # Переопределяем SessionLocal приложения на "сессионный" фабричный метод,
        # чтобы весь код приложения (и фоновые куски), который создаёт сессии,
        # попадал в тот же коннект/транзакцию.
        old_SessionLocal = session_module.SessionLocal
        session_module.SessionLocal = Session

        async with Session() as session:
            # Инициализируем первый SAVEPOINT (nested)
            # Событие ниже будет перезапускать его после каждого commit() внутри кода.
            def _restart_savepoint(sess, trans):
                # Этот event синхронный и приходит на sync_session.
                if trans.nested and not trans._parent.nested:
                    sess.begin_nested()

            # Подписываемся на событие sync-части сессии
            event.listen(session.sync_session, "after_transaction_end", _restart_savepoint)

            # Стартуем первый nested
            session.sync_session.begin_nested()

            # Дополнительно уменьшим таймауты, чтобы зависания не тянулись:
            await session.execute(text("SET LOCAL lock_timeout = '2s'"))
            await session.execute(text("SET LOCAL statement_timeout = '30s'"))
            await session.execute(text("SET CONSTRAINTS ALL DEFERRED"))

            try:
                yield session
            finally:
                # Снимаем подписку, восстанавливаем фабрику
                event.remove(session.sync_session, "after_transaction_end", _restart_savepoint)

        # ROLLBACK большого транзакта — мгновенная очистка БД после теста
        await outer.rollback()
        session_module.SessionLocal = old_SessionLocal


# Иногда тесты ожидают фикстуру 'session' — дадим алиас
@pytest_asyncio.fixture(scope="function")
async def session(async_session: AsyncSession) -> AsyncIterator[AsyncSession]:
    yield async_session


# ===== ФИКС 2: Минимальный сид для FK (autouse) =====
@pytest_asyncio.fixture(autouse=True)
async def _minimal_seed(async_session: AsyncSession):
    """
    Автоматически создаёт минимальные справочные данные для предотвращения FK-ошибок.
    Срабатывает для КАЖДОГО теста перед его выполнением.
    Не заменяет фабрики, но страхует тесты, которые создают сущности без связанных записей.
    
    Создаёт базовые сущности с уникальными именами, чтобы не конфликтовать с тестами.
    """
    # Город по умолчанию - с уникальным именем чтобы не конфликтовать с тестами
    # Используем имя которое вряд ли будет использоваться в тестах
    seed_city_result = await async_session.execute(
        sa.select(m.cities).where(m.cities.name == "__SeedCity__")
    )
    seed_city = seed_city_result.scalar_one_or_none()
    
    if seed_city is None:
        # Используем timezone, который важен для планировщика
        seed_city = m.cities(name="__SeedCity__", timezone="Europe/Moscow")
        async_session.add(seed_city)
        await async_session.flush()  # без commit! Всё внутри транзакции теста

    # Район по умолчанию - создаём только если нет ни одного для этого города
    seed_district_result = await async_session.execute(
        sa.select(m.districts).where(
            m.districts.city_id == seed_city.id,
            m.districts.name == "__SeedDistrict__"
        )
    )
    seed_district = seed_district_result.scalar_one_or_none()
    
    if seed_district is None:
        seed_district = m.districts(city_id=seed_city.id, name="__SeedDistrict__")
        async_session.add(seed_district)
        await async_session.flush()


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


@pytest_asyncio.fixture(autouse=True)
async def _patch_distribution_tick(async_session: AsyncSession, monkeypatch):
    """Патчим tick_once чтобы он использовал фикстурную сессию"""
    from field_service.services import distribution_scheduler

    original_tick_once = distribution_scheduler.tick_once

    async def tick_once_proxy(cfg, *, bot=None, alerts_chat_id=None, session=None):
        if session is None:
            session = async_session
        return await original_tick_once(cfg, bot=bot, alerts_chat_id=alerts_chat_id, session=session)

    monkeypatch.setattr(distribution_scheduler, "tick_once", tick_once_proxy)
    yield


# Seed minimal reference data for tests that explicitly need it
@pytest_asyncio.fixture()
async def seed_minimal_data(async_session: AsyncSession) -> None:
    """
    Создаём минимальные справочные данные для тестов.
    Тесты должны явно запрашивать эту фикстуру, если им нужны данные.
    """
    # Seed a default city if none exists
    res = await async_session.execute(sa.select(sa.func.count()).select_from(m.cities))
    if (res.scalar_one() or 0) == 0:
        city = m.cities(id=999999, name="ZZZ Seed City", timezone="Europe/Moscow")
        async_session.add(city)
        await async_session.flush()

        # Seed a default district bound to the city
        district = m.districts(id=999999, city_id=city.id, name="ZZZ Seed District")
        async_session.add(district)
        await async_session.commit()
    
    # Provide a generic city with id=1 for tests that reference it directly
    existing1 = await async_session.get(m.cities, 1)
    if existing1 is None:
        async_session.add(m.cities(id=1, name="City #1", timezone="Europe/Moscow"))
        await async_session.commit()
