import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from field_service.db import models as m
from tests.conftest import TEST_DATABASE_URL

async def main():
    engine = create_async_engine(TEST_DATABASE_URL)
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    async with async_session() as session:
        await session.execute(text("TRUNCATE TABLE offers CASCADE"))
        await session.execute(text("TRUNCATE TABLE orders CASCADE"))
        await session.execute(text("TRUNCATE TABLE masters CASCADE"))
        await session.execute(text("TRUNCATE TABLE cities CASCADE"))
        await session.commit()
    async with async_session() as session:
        city = m.cities(id=1, name="Test City", timezone="Europe/Moscow")
        session.add(city)
        master = m.masters(id=100, telegram_id=111, full_name="Test Master", phone="+7999", city_id=1, moderation_status=m.ModerationStatus.APPROVED, is_blocked=False)  # type: ignore[arg-type]
        session.add(master)
        order = m.orders(id=500, city_id=1, category=m.OrderCategory.ELECTRICS, type=m.OrderType.NORMAL, status=m.OrderStatus.SEARCHING)
        session.add(order)
        offer = m.offers(order_id=500, master_id=100, state=m.OfferState.SENT)
        session.add(offer)
        try:
            await session.commit()
        except Exception as exc:
            print("commit failed", type(exc), exc)
            await session.rollback()
        else:
            print("commit ok")

asyncio.run(main())
