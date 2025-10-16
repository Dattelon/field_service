from __future__ import annotations

import asyncio
import csv
from pathlib import Path
from typing import Dict, List

import sqlalchemy as sa
from field_service.db.session import SessionLocal
from field_service.db import models as m


def _norm(s: str) -> str:
    import re

    s = s.strip().lower().replace("ё", "е")
    s = re.sub(r"[\u2010-\u2015-]", " ", s)
    s = s.replace("(", " ").replace(")", " ")
    s = re.sub(r"\s+", " ", s)
    return s


def _open_csv_guess(path: Path):
    for enc in ("utf-8", "utf-8-sig", "cp1251", "windows-1251", "latin-1"):
        try:
            return path.open("r", encoding=enc, newline="")
        except Exception:
            continue
    return None


async def main() -> None:
    base = Path(__file__).resolve().parents[2] / 'data'
    csv_path = base / 'all_districts_complete.csv'
    if not csv_path.exists():
        print(f"CSV not found: {csv_path}")
        return

    f = _open_csv_guess(csv_path)
    if not f:
        print("Failed to open CSV with known encodings")
        return

    by_city: Dict[str, List[str]] = {}
    try:
        reader = csv.DictReader(f)
        for row in reader:
            if (row.get('type') or '').strip().lower() != 'district':
                continue
            city = (row.get('city') or row.get('city_name') or '').strip()
            name = (row.get('name') or row.get('district') or '').strip()
            if not city or not name:
                continue
            by_city.setdefault(_norm(city), []).append(name)
    finally:
        try:
            f.close()
        except Exception:
            pass

    async with SessionLocal() as session:
        async with session.begin():
            cities = (await session.execute(sa.select(m.cities.id, m.cities.name))).all()
            added_total = 0
            for cid, cname in cities:
                key = _norm(cname)
                names = by_city.get(key)
                if not names:
                    continue
                existing = set(
                    n for (n,) in (
                        await session.execute(sa.select(m.districts.name).where(m.districts.city_id == cid))
                    ).all()
                )
                to_add = [m.districts(city_id=cid, name=n) for n in names if n not in existing]
                if to_add:
                    session.add_all(to_add)
                    added_total += len(to_add)
        await session.commit()
    print("Seeded districts added:", added_total)


if __name__ == '__main__':
    asyncio.run(main())

