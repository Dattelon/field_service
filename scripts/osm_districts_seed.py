from __future__ import annotations
import asyncio
import json
import os
from typing import Iterable
from urllib import parse, request
from pathlib import Path
import sys

# Ensure project root on sys.path
BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from sqlalchemy import select, text

from field_service.db.session import SessionLocal
from field_service.db import models as m

# Ordered list of Overpass endpoints (first can be overridden by OVERPASS_URL)
OVERPASS_URLS = (
    os.getenv("OVERPASS_URL", "https://overpass-api.de/api/interpreter"),
    "https://overpass.kumi.systems/api/interpreter",
)


def _overpass_fetch(query: str) -> dict:
    data = parse.urlencode({"data": query}).encode("utf-8")
    last_err: Exception | None = None
    for url in OVERPASS_URLS:
        try:
            req = request.Request(url, data=data, method="POST")
            req.add_header("Content-Type", "application/x-www-form-urlencoded")
            with request.urlopen(req, timeout=120) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                return json.loads(raw)
        except Exception as e:
            last_err = e
            continue
    raise RuntimeError(f"Overpass error: {last_err}")


def build_osm_districts_query(city_name_ru: str) -> str:
    safe = city_name_ru.replace('"', '\\"')
    return f"""
    [out:json][timeout:120];
    rel["name"~"{safe}",i]["boundary"="administrative"]->.r1;
    rel["name:ru"~"{safe}",i]["boundary"="administrative"]->.r2;
    (.r1;.r2;);
    map_to_area -> .search;
    (
      // keep only official admin districts/okrugs (районы/округа города)
      rel(area.search)["boundary"="administrative"]["admin_level"~"^(9|10)$"];
    );
    out tags;
    """


def parse_names(js: dict) -> list[str]:
    names: list[str] = []
    for el in js.get("elements", []) or []:
        tags = el.get("tags", {}) or {}
        nm = (tags.get("name:ru") or tags.get("name") or "").strip()
        if not nm:
            continue
        low = nm.lower()
        if any(
            x in low
            for x in ("микрорай", "мкр", "квартал", "кв-", "жк ", "жилой комплекс")
        ):
            continue
        names.append(nm)
    # unique case-insensitively
    seen: set[str] = set()
    out: list[str] = []
    for nm in names:
        key = nm.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(nm)
    return out


async def ensure_city(session, name: str) -> int:
    q = await session.execute(select(m.cities).where(m.cities.name == name))
    inst = q.scalar_one_or_none()
    if inst:
        return inst.id
    session.add(m.cities(name=name, is_active=True))
    await session.commit()
    q = await session.execute(select(m.cities).where(m.cities.name == name))
    return q.scalar_one().id


async def upsert_districts(session, city_id: int, names: Iterable[str]) -> int:
    inserted = 0
    for nm in names:
        await session.execute(
            text(
                """
                INSERT INTO districts(city_id, name) VALUES (:cid, :name)
                ON CONFLICT ON CONSTRAINT uq_districts__city_name DO NOTHING
                """
            ),
            {"cid": city_id, "name": nm},
        )
        inserted += 1
    await session.commit()
    return inserted


async def seed_one_city(session, city_name: str) -> None:
    cid = await ensure_city(session, city_name)
    try:
        js = await asyncio.to_thread(
            _overpass_fetch, build_osm_districts_query(city_name)
        )
        names = parse_names(js)
    except Exception as e:
        print(f"[{city_name}] Overpass error: {e}")
        return
    if not names:
        print(f"[{city_name}] Overpass returned no districts")
        return
    ins = await upsert_districts(session, cid, names)
    print(f"[{city_name}] добавлено/обновлено: {ins} районов")


async def main():
    only_city = os.getenv("FS_CITY")
    limit = int(os.getenv("FS_CITY_LIMIT", "0"))
    async with SessionLocal() as session:
        if only_city:
            city_names = [only_city]
        else:
            rows = await session.execute(
                text("SELECT name FROM cities WHERE is_active = TRUE ORDER BY name")
            )
            city_names = [r[0] for r in rows.fetchall()]
            if limit > 0:
                city_names = city_names[:limit]
        for name in city_names:
            await seed_one_city(session, name)
            await asyncio.sleep(1.0)


if __name__ == "__main__":
    asyncio.run(main())
