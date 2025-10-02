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
