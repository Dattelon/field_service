import asyncio
from field_service.db.session import SessionLocal
from field_service.db import models as m
from field_service.config import settings
from sqlalchemy import update, select

async def main():
    async with SessionLocal() as s:
        tz = settings.timezone or 'Europe/Moscow'
        await s.execute(update(m.cities).where((m.cities.timezone == None) | (m.cities.timezone == '')).values(timezone=tz))
        await s.commit()
        rows = await s.execute(select(m.cities.id, m.cities.name, m.cities.timezone).order_by(m.cities.id).limit(5))
        print('Sample cities after tz set:', [tuple(r) for r in rows.all()])

asyncio.run(main())
