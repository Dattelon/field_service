from __future__ import annotations

import asyncio
from typing import Optional

import sqlalchemy as sa
from field_service.db.session import engine, SessionLocal
from field_service.db import models as m


async def print_city_info(name: Optional[str] = None) -> None:
    async with SessionLocal() as session:
        if name:
            row = await session.execute(sa.select(m.cities).where(m.cities.name == name))
            city = row.scalars().first()
            if not city:
                print(f"city '{name}': not found")
                return
            cnt = await session.scalar(
                sa.select(sa.func.count()).select_from(m.districts).where(m.districts.city_id == city.id)
            )
            print(f"city='{city.name}' id={city.id} districts={cnt}")
            if cnt:
                rows = (
                    await session.execute(
                        sa.select(m.districts.name).where(m.districts.city_id == city.id).order_by(m.districts.name)
                    )
                ).all()
                for (dname,) in rows:
                    print(f" - {dname}")
            return

        rows = (
            await session.execute(
                sa.select(m.cities.id, m.cities.name).order_by(m.cities.name)
            )
        ).all()
        def _norm(s: str) -> str:
            import re
            s = (s or '').strip().lower().replace('ё','е')
            s = re.sub(r"[\u2010-\u2015-]", " ", s)
            s = s.replace("(", " ").replace(")", " ")
            s = re.sub(r"\s+", " ", s)
            return s
        for cid, cname in rows:
            cnt = await session.scalar(
                sa.select(sa.func.count()).select_from(m.districts).where(m.districts.city_id == cid)
            )
            print(f"{cid:5d}  {cname}  districts={cnt}  norm='{_norm(str(cname))}'")


async def main() -> None:
    import sys
    name = sys.argv[1] if len(sys.argv) > 1 else None
    await print_city_info(name)


if __name__ == "__main__":
    asyncio.run(main())
