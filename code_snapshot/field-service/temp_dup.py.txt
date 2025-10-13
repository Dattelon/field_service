import asyncio
from datetime import timedelta

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from field_service.db import models as m
from field_service.db.base import metadata

DATABASE_URL = "postgresql+asyncpg://fs_user:fs_password@localhost:5439/field_service_test"

async def main():
    engine = create_async_engine(DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(metadata.drop_all)
        await conn.run_sync(metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with Session() as session:
        city = m.cities(id=1, name="City1", timezone="UTC", is_active=True)
        session.add(city)
        await session.commit()
    async with Session() as session:
        city = m.cities(id=1, name="City2", timezone="UTC", is_active=True)
        session.add(city)
        try:
            await session.commit()
        except Exception as exc:
            import traceback
            traceback.print_exception(exc)
    await engine.dispose()

asyncio.run(main())
