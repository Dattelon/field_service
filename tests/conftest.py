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
    m.masters.__table__,
    m.master_invite_codes.__table__,
    m.orders.__table__,
    m.commissions.__table__,
]


@pytest_asyncio.fixture()
async def async_session() -> AsyncIterator[AsyncSession]:
    engine: AsyncEngine = create_async_engine(
        "sqlite+aiosqlite:///:memory:", future=True
    )
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: sync_conn.execute(
                sa.text("CREATE TABLE staff_users (id INTEGER PRIMARY KEY)")
            )
        )
        await conn.run_sync(
            lambda sync_conn: metadata.create_all(sync_conn, tables=TABLES)
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()
    await engine.dispose()
