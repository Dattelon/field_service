import asyncio
from datetime import timedelta

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from field_service.db import models as m
from field_service.db.base import metadata

DATABASE_URL = "postgresql+asyncpg://fs_user:fs_password@localhost:5439/field_service_test"

TABLES = [
    m.cities.__table__,
    m.masters.__table__,
    m.orders.__table__,
    m.offers.__table__,
    m.distribution_metrics.__table__,
]

async def create_schema(engine):
    async with engine.begin() as conn:
        await conn.run_sync(metadata.create_all, tables=TABLES)

async def main():
    engine = create_async_engine(DATABASE_URL, echo=False)
    await create_schema(engine)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with session_factory() as session:
        db_now = await session.scalar(sa.text("SELECT now()"))
        city = m.cities(id=1, name="Test City", is_active=True, timezone="Europe/Moscow")
        session.add(city)

        master = m.masters(
            id=100,
            tg_user_id=111,
            full_name="Test Master",
            phone="+79991234567",
            city_id=1,
            moderation_status=m.ModerationStatus.APPROVED,
            is_blocked=False,
        )
        session.add(master)

        order = m.orders(
            id=500,
            city_id=1,
            category=m.OrderCategory.ELECTRICS,
            type=m.OrderType.NORMAL,
            status=m.OrderStatus.SEARCHING,
            created_at=db_now - timedelta(minutes=5),
        )
        session.add(order)

        offer = m.offers(
            order_id=500,
            master_id=100,
            state=m.OfferState.SENT,
            round_number=1,
            sent_at=db_now,
            expires_at=db_now + timedelta(minutes=2),
        )
        session.add(offer)

        try:
            await session.commit()
        except Exception as exc:
            print("commit failed:", type(exc), exc)
            await session.rollback()
        else:
            print("commit succeeded")

    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(main())
