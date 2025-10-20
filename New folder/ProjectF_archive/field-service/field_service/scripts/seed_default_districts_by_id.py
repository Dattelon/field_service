from __future__ import annotations

import asyncio
import sys

import sqlalchemy as sa
from field_service.db.session import SessionLocal
from field_service.db import models as m

DEFAULTS = [
    "Кировский",
    "Ленинский",
    "Октябрьский",
    "Свердловский",
]


async def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m field_service.scripts.seed_default_districts_by_id <city_id>")
        return
    city_id = int(sys.argv[1])
    async with SessionLocal() as session:
        async with session.begin():
            city = (
                await session.execute(sa.select(m.cities).where(m.cities.id == city_id))
            ).scalars().first()
            if not city:
                print(f"City id {city_id} not found")
                return
            existing = set(
                n for (n,) in (
                    await session.execute(sa.select(m.districts.name).where(m.districts.city_id == city_id))
                ).all()
            )
            to_add = [m.districts(city_id=city_id, name=n) for n in DEFAULTS if n not in existing]
            if to_add:
                session.add_all(to_add)
        await session.commit()
    print(f"Seeded defaults for city_id={city_id}: added={len(to_add)}")


if __name__ == "__main__":
    asyncio.run(main())

