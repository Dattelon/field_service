import asyncio
from datetime import timedelta

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from field_service.db import models as m
from field_service.db.base import metadata

DATABASE_URL = "postgresql+asyncpg://fs_user:fs_password@localhost:5439/field_service_test"

async def main():
    engine = create_async_engine(DATABASE_URL, echo=True)
    async with engine.begin() as conn:
        await conn.run_sync(metadata.drop_all)
        await conn.run_sync(metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with Session() as session:
        db_now = await session.scalar(sa.text("select now()"))
        city = m.cities(name="Test", timezone="UTC", is_active=True)
        session.add(city)
        await session.flush()
        master = m.masters(city_id=city.id, full_name="Master", moderation_status=m.ModerationStatus.APPROVED)
        session.add(master)
        await session.flush()
        order = m.orders(city_id=city.id, category=m.OrderCategory.ELECTRICS, type=m.OrderType.NORMAL, status=m.OrderStatus.SEARCHING)
        session.add(order)
        await session.flush()
        offer = m.offers(order_id=order.id, master_id=master.id, state=m.OfferState.SENT)
        session.add(offer)
        try:
            await session.commit()
            print("commit ok")
        except Exception as exc:
            print("commit failed", exc.__class__.__name__, exc)
            raise
    await engine.dispose()

asyncio.run(main())
