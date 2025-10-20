from __future__ import annotations

import argparse
import asyncio
import csv
from pathlib import Path
from typing import Optional

from sqlalchemy import select

from field_service.db.session import SessionLocal
from field_service.db import models as m


def _open_csv_guess(path: Path):
    encodings = ("utf-8", "utf-8-sig", "cp1251", "windows-1251", "latin-1")
    last_exc: Optional[Exception] = None
    for enc in encodings:
        try:
            return path.open("r", encoding=enc, newline="")
        except Exception as e:
            last_exc = e
    raise RuntimeError(f"Failed to open CSV {path} with known encodings: {last_exc}")


async def restore_from_csv(csv_path: Path, *, dry_run: bool = False) -> tuple[int, int]:
    added_cities = 0
    added_districts = 0

    async with SessionLocal() as session:
        async with session.begin():
            # Build existing lookups
            city_by_name: dict[str, int] = {}
            res = await session.execute(select(m.cities.id, m.cities.name))
            for cid, cname in res.all():
                city_by_name[str(cname)] = int(cid)

            district_keys: set[tuple[int, str]] = set()
            res = await session.execute(select(m.districts.city_id, m.districts.name))
            for city_id, dname in res.all():
                district_keys.add((int(city_id), str(dname)))

            with _open_csv_guess(csv_path) as f:
                reader = csv.DictReader(f)
                for row in reader:
                    rtype = (row.get("type") or "district").strip().lower()
                    if rtype != "district":
                        # ignore other rows
                        continue
                    city_name = (row.get("city") or row.get("city_name") or "").strip()
                    if not city_name:
                        continue
                    district_name = (row.get("name") or row.get("district") or "").strip()
                    if not district_name:
                        continue
                    try:
                        lat = float(row.get("centroid_lat") or 0) or None
                        lon = float(row.get("centroid_lon") or 0) or None
                    except Exception:
                        lat = None
                        lon = None

                    city_id = city_by_name.get(city_name)
                    if city_id is None:
                        if not dry_run:
                            city_obj = m.cities(name=city_name, is_active=True)
                            session.add(city_obj)
                            await session.flush()
                            city_id = int(city_obj.id)
                        else:
                            city_id = -1
                        city_by_name[city_name] = city_id
                        added_cities += 1

                    key = (city_id, district_name)
                    if key in district_keys:
                        continue
                    if not dry_run and city_id > 0:
                        dist = m.districts(city_id=city_id, name=district_name)
                        # store centroid if provided
                        if lat is not None:
                            dist.centroid_lat = lat
                        if lon is not None:
                            dist.centroid_lon = lon
                        session.add(dist)
                    district_keys.add(key)
                    added_districts += 1

        if not dry_run:
            await session.commit()

    return added_cities, added_districts


async def main() -> None:
    parser = argparse.ArgumentParser(description="Restore cities and districts from CSV")
    parser.add_argument(
        "--csv",
        dest="csv_path",
        default=str(Path(__file__).resolve().parents[2] / "data" / "all_districts_complete.csv"),
        help="Path to CSV file with columns: type,city,district,name,centroid_lat,centroid_lon",
    )
    parser.add_argument("--dry-run", action="store_true", help="Do not write changes, just report counts")
    args = parser.parse_args()

    added_cities, added_districts = await restore_from_csv(Path(args.csv_path), dry_run=args.dry_run)
    print(f"RESTORE DONE: cities_added={added_cities} districts_added={added_districts} dry_run={args.dry_run}")


if __name__ == "__main__":
    asyncio.run(main())

