from __future__ import annotations

import asyncio
import re

import sqlalchemy as sa
from field_service.db.session import SessionLocal
from field_service.db import models as m


def _norm(s: str) -> str:
    s = s.strip().lower().replace("ё", "е")
    s = re.sub(r"[\u2010-\u2015-]", " ", s)
    s = s.replace("(", " ").replace(")", " ")
    s = re.sub(r"\s+", " ", s)
    return s


async def main() -> None:
    target = _norm("Иркутск")
    async with SessionLocal() as session:
        rows = (await session.execute(sa.select(m.cities.id, m.cities.name))).all()
        match = None
        for cid, cname in rows:
            if _norm(cname) == target:
                match = (cid, cname)
                break
        if not match:
            print("Иркутск не найден в таблице cities")
            return
        cid, cname = match
        print(f"city: {cname} (id={cid})")
        names = (
            await session.execute(
                sa.select(m.districts.name).where(m.districts.city_id == cid).order_by(m.districts.name)
            )
        ).all()
        print("districts:")
        for (dname,) in names:
            print(f" - {dname}")
        print(f"total={len(names)}")


if __name__ == "__main__":
    asyncio.run(main())

