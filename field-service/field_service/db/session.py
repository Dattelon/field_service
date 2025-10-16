from __future__ import annotations
import os
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import text
import asyncio

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://fs_user:fs_password@127.0.0.1:5439/field_service",
)

engine = create_async_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=10,  # ✅ FIX: Размер пула для параллельных тестов
    max_overflow=20,  # ✅ FIX: Максимум дополнительных соединений
    future=True,
)

# Best-effort: ensure optional compatibility columns exist in test DB
async def _ensure_testing_ddl() -> None:
    stmts = (
        "ALTER TABLE IF EXISTS masters ADD COLUMN IF NOT EXISTS telegram_username VARCHAR(64)",
        "ALTER TABLE IF EXISTS masters ADD COLUMN IF NOT EXISTS first_name VARCHAR(80)",
        "ALTER TABLE IF EXISTS masters ADD COLUMN IF NOT EXISTS last_name VARCHAR(120)",
    )
    async with engine.begin() as conn:
        for sql in stmts:
            try:
                await conn.execute(text(sql))
            except Exception:
                # ignore if cannot alter (permissions, etc.)
                pass

# ❌ УДАЛЕНО: автоматический запуск DDL при импорте вызывает конфликт event loop
# Если нужно выполнить DDL, вызывайте _ensure_testing_ddl() явно в тестах

SessionLocal = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
    class_=AsyncSession,
)
