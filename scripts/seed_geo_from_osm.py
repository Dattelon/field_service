# scripts/seed_geo_from_osm.py
from __future__ import annotations
import asyncio
import os
from typing import Any, Iterable, Optional

import aiohttp
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

# Читаем URL БД как в проекте
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://fs_user:fs_password@127.0.0.1:5439/field_service",
)
OVERPASS_URL = os.getenv("OVERPASS_URL", "https://overpass-api.de/api/interpreter")

# Минимальный набор highway для улиц
HW_TAGS = ["residential","unclassified","tertiary","secondary","primary","living_street","service"]

# ---- SQLAlchemy session (как в field_service.db.session, но standalone) ----
engine = create_async_engine(DATABASE_URL, future=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

# ---- Helpers ----
def chunked(it: Iterable[Any], size: int):
    buf = []
    for x in it:
        buf.append(x)
        if len(buf) >= size:
            yield buf; buf = []
    if buf:
        yield buf

async def overpass_query(session: aiohttp.ClientSession, q: str) -> dict:
    async with session.post(OVERPASS_URL, data={"data": q}, timeout=120) as resp:
        resp.raise_for_status()
        return await resp.json()

def build_query_city_area(city_name: str) -> str:
    # Ищем "area" соответствующую городу; затем районы и улицы внутри неё.
    # admin_level у городов/районов в РФ разнится (8/9/10/11) — делаем пошире фильтр.
    return f"""
    [out:json][timeout:120];
    area[name="{city_name}"]["boundary"="administrative"];
    // районы (административные сущности внутри города)
    rel(area)["boundary"="administrative"]["admin_level"~"^(8|9|10|11)$"];
    out tags;
    // улицы (ways с name)
    way(area)["highway"]["name"];
    out tags;
    """

def normalize_name(s: Optional[str]) -> Optional[str]:
    if not s: return None
    s = s.strip()
    # Без точек на концах, двойных пробелов и т.п.
    while "  " in s:
        s = s.replace("  ", " ")
    return s

# ---- Main logic ----
async def seed_city(city_name: str):
    print(f"== Город: {city_name}")
    async with SessionLocal() as db, aiohttp.ClientSession() as http:
        # 1) Получим city_id
        row = await db.execute(text("SELECT id FROM cities WHERE name=:n"), {"n": city_name})
        c = row.first()
        if not c:
            print(f"  !! Город не найден в БД: {city_name} — пропуск.")
            return
        city_id = c[0]

        # 2) тянем из Overpass
        q = build_query_city_area(city_name)
        data = await overpass_query(http, q)
        elements = data.get("elements", [])

        # 3) Выделяем районы (rel) и улицы (way)
        districts = []
        streets = []

        for el in elements:
            t = el.get("type")
            tags = el.get("tags", {}) or {}
            name = normalize_name(tags.get("name"))

            if t == "relation":  # district candidate
                # не берём сам город, только вложенные
                if name and name != city_name and tags.get("boundary") == "administrative":
                    districts.append(name)

            elif t == "way":  # street candidate
                if name and tags.get("highway") in HW_TAGS:
                    # Попытка достать подсказку района
                    d_guess = normalize_name(tags.get("addr:district") or tags.get("addr:suburb"))
                    streets.append((name, d_guess))

        # 4) Записываем районы (idempotent)
        inserted_district_ids: dict[str, int] = {}
        for batch in chunked(sorted(set(districts)), 200):
            for dname in batch:
                await db.execute(text("""
                    INSERT INTO districts(city_id, name)
                    VALUES (:cid, :name)
                    ON CONFLICT (city_id, name) DO NOTHING
                """), {"cid": city_id, "name": dname})

        # смапим названия->id
        rows = await db.execute(text("SELECT id, name FROM districts WHERE city_id=:cid"), {"cid": city_id})
        for did, dname in rows.all():
            inserted_district_ids[dname] = did

        # 5) Записываем улицы (idempotent + попытка связать с районом по имени)
        #    У нас уникальность (city_id, district_id, name); если район не распознан — пишем с NULL district_id.
        for nm, d_guess in chunked(streets, 5000):  # типизация подсказки для IDE не критична
            pass  # это трюк, чтобы рендер не завис – фактические вставки ниже циклом

        added = 0
        for sname, d_guess in streets:
            d_id = inserted_district_ids.get(d_guess) if d_guess else None
            await db.execute(text("""
                INSERT INTO streets(city_id, district_id, name)
                VALUES (:cid, :did, :name)
                ON CONFLICT (city_id, district_id, name) DO NOTHING
            """), {"cid": city_id, "did": d_id, "name": sname})
            added += 1

        await db.commit()
        print(f"  ✓ Районов (кандидатов): {len(districts)} | в БД теперь: {len(inserted_district_ids)}")
        print(f"  ✓ Улиц обработано: {len(streets)} (вставки были идемпотентны)")

async def main():
    # Если передан FS_CITY="Москва" — ограничим одним городом.
    only_city = os.getenv("FS_CITY")
    # Если нужно ограничить количеством городов (для теста), задайте FS_CITY_LIMIT
    limit = int(os.getenv("FS_CITY_LIMIT", "0"))

    async with SessionLocal() as db:
        q = await db.execute(text("SELECT name FROM cities WHERE is_active = TRUE ORDER BY name"))
        city_names = [r[0] for r in q.fetchall()]

    if only_city:
        city_names = [only_city] if only_city in city_names else []

    if limit and limit > 0:
        city_names = city_names[:limit]

    for name in city_names:
        try:
            await seed_city(name)
            # Вежливая пауза для Overpass (rate limit)
            await asyncio.sleep(1.2)
        except Exception as e:
            print(f"  !! Ошибка города {name}: {e}")

if __name__ == "__main__":
    asyncio.run(main())
