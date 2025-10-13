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
        db_now = await session.scalar(sa.text("select now()"))
        city = m.cities(id=1, name="Test City", timezone="UTC", is_active=True)
        session.add(city)
        master = m.masters(id=100, telegram_id=111, full_name="Master", city_id=1, moderation_status=m.ModerationStatus.APPROVED)
        session.add(master)
        order = m.orders(id=500, city_id=1, category=m.OrderCategory.ELECTRICS, type=m.OrderType.NORMAL, status=m.OrderStatus.SEARCHING, created_at=db_now)
        session.add(order)
        offer = m.offers(order_id=500, master_id=100, state=m.OfferState.SENT)
        session.add(offer)
        try:
            await session.commit()
            print("commit ok")
        except Exception as exc:
            print("commit failed", type(exc), exc)
            raise
    await engine.dispose()

asyncio.run(main())
