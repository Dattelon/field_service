from __future__ import annotations
import asyncio
import os
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

SQL = (
    "INSERT INTO staff_users (tg_user_id, username, full_name, role, is_active) "
    "VALUES (332786197, 'admin_demo', 'Админ Демо', 'ADMIN', TRUE) "
    "ON CONFLICT (tg_user_id) DO UPDATE SET role='ADMIN', is_active=TRUE, username=EXCLUDED.username, full_name=EXCLUDED.full_name;"
)

SELECT_SQL = (
    "SELECT id, tg_user_id, username, full_name, role, is_active "
    "FROM staff_users WHERE tg_user_id=332786197"
)


async def main() -> None:
    dsn = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://fs_user:fs_password@127.0.0.1:5439/field_service",
    )
    engine = create_async_engine(dsn, future=True)
    try:
        async with engine.begin() as conn:
            await conn.execute(text(SQL))
        async with engine.connect() as conn:
            res = await conn.execute(text(SELECT_SQL))
            row = res.first()
            if row:
                print(dict(row._mapping))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
