import asyncio
import sqlalchemy as sa
from field_service.db import models as m
from field_service.db.session import SessionLocal
from field_service.services.distribution_scheduler import tick_once, DistConfig

async def main():
    async with SessionLocal() as session:
        city = m.cities(name='CityX', is_active=True)
        district = m.districts(city=city, name='D1')
        session.add_all([city, district])
        await session.flush()
        order = m.orders(status=m.OrderStatus.SEARCHING, city_id=city.id, district_id=district.id, category='ELECTRICS')
        session.add(order)
        await session.commit()
        await session.refresh(order)
        cfg = DistConfig(tick_seconds=30, sla_seconds=120, rounds=2, top_log_n=10, to_admin_after_min=10)
        await tick_once(cfg, bot=None, alerts_chat_id=None, session=session)
        row = await session.execute(sa.text("SELECT dist_escalated_logist_at, escalation_logist_notified_at FROM orders WHERE id=:oid").bindparams(oid=order.id))
        print('DB:', row.fetchone())

asyncio.run(main())
