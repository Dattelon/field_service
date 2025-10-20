#!/usr/bin/env python
"""Utility to import geo dictionaries with RapidFuzz-based dedupe.

Usage:
    python -m tools.load_geo_catalog --input geo_catalog.csv [--dry-run]

The CSV is expected to contain the columns:
    type (city|district|street)
    city (mandatory for district/street)
    district (required for street)
    name (value to import)
    centroid_lat (optional)
    centroid_lon (optional)

RapidFuzz thresholds:
    - score >= 93: treated as duplicate and skipped automatically
    - 85 <= score < 93: reported as "questionable" for manual review

The script prints a summary with counts of added, skipped duplicates and
questionable rows. For questionable items no INSERT is performed.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, Optional, Sequence, Tuple

from rapidfuzz import fuzz, process
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from field_service.db import models as m
from field_service.db.session import SessionLocal\nfrom field_service.data import cities as city_catalog

DUP_THRESHOLD = 93
QUESTIONABLE_THRESHOLD = 85


@dataclass
class ImportRow:
    kind: str
    city: Optional[str]
    district: Optional[str]
    name: str


@dataclass
class ImportStats:
    created: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    duplicates: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    questionable: list[tuple[str, str, float, str]] = field(default_factory=list)

    def mark_created(self, kind: str) -> None:
        self.created[kind] += 1

    def mark_duplicate(self, kind: str) -> None:
        self.duplicates[kind] += 1

    def add_questionable(self, kind: str, value: str, match: str, score: float) -> None:
        self.questionable.append((kind, value, score, match))

    def render_summary(self) -> str:
        parts = [
            "Import finished:",
            f"  Cities added: {self.created.get('city', 0)}",
            f"  Districts added: {self.created.get('district', 0)}",
            f"  Streets added: {self.created.get('street', 0)}",
            f"  Duplicates skipped: city={self.duplicates.get('city', 0)}, district={self.duplicates.get('district', 0)}, street={self.duplicates.get('street', 0)}",
            f"  Questionable entries: {len(self.questionable)}",
        ]
        if self.questionable:
            parts.append("  Questionable rows (kind | value ~ match | score):")
            for kind, value, score, match in self.questionable:
                parts.append(f"    - {kind} | {value} ~ {match} | {score:.1f}")
        return "\n".join(parts)


@dataclass
class GeoCache:
    city_by_name: Dict[str, int]
    districts_by_city: Dict[int, Dict[str, int]]
    streets_by_scope: Dict[Tuple[int, Optional[int]], set[str]]

    @classmethod
    async def load(cls, session) -> "GeoCache":
        city_rows = await session.execute(select(m.cities.id, m.cities.name))
        city_map = {row.name.strip(): row.id for row in city_rows}

        district_rows = await session.execute(
            select(m.districts.id, m.districts.city_id, m.districts.name)
        )
        districts: Dict[int, Dict[str, int]] = defaultdict(dict)
        for row in district_rows:
            districts[row.city_id][row.name.strip()] = row.id

        street_rows = await session.execute(
            select(m.streets.city_id, m.streets.district_id, m.streets.name)
        )
        streets: Dict[Tuple[int, Optional[int]], set[str]] = defaultdict(set)
        for row in street_rows:
            streets[(row.city_id, row.district_id)].add(row.name.strip())

        return cls(city_map, districts, streets)

    def get_city_id(self, name: str) -> Optional[int]:
        return self.city_by_name.get(name.strip())

    def get_district_id(self, city_id: int, name: str) -> Optional[int]:
        return self.districts_by_city.get(city_id, {}).get(name.strip())

    def register_city(self, city_id: int, name: str) -> None:
        self.city_by_name[name.strip()] = city_id

    def register_district(self, city_id: int, district_id: int, name: str) -> None:
        self.districts_by_city.setdefault(city_id, {})[name.strip()] = district_id

    def register_street(
        self, city_id: int, district_id: Optional[int], name: str
    ) -> None:
        self.streets_by_scope.setdefault((city_id, district_id), set()).add(name.strip())


def _normalise(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _parse_float(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    candidate = value.strip().replace(',', '.')
    if not candidate:
        return None
    try:
        return float(candidate)
    except ValueError:
        return None


def parse_rows(path: Path, delimiter: str = ";") -> list[ImportRow]:
    rows: list[ImportRow] = []
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh, delimiter=delimiter)
        for line in reader:
            kind = _normalise(line.get("type"))
            name = _normalise(line.get("name"))
            if not kind or not name:
                continue
            city = _normalise(line.get("city"))
            if city:
                resolved_city = city_catalog.resolve_city_name(city)
                if resolved_city:
                    city = resolved_city
            district = _normalise(line.get("district"))
            centroid_lat = _parse_float(line.get("centroid_lat"))
            centroid_lon = _parse_float(line.get("centroid_lon"))
            rows.append(ImportRow(kind=kind.lower(), city=city, district=district, name=name, centroid_lat=centroid_lat, centroid_lon=centroid_lon))
    return rows


def _best_match(candidate: str, population: Iterable[str]) -> Optional[tuple[str, float]]:
    population_list = list(population)
    if not population_list:
        return None
    match = process.extractOne(candidate, population_list, scorer=fuzz.WRatio)
    if match is None:
        return None
    return match[0], match[1]


async def import_rows(rows: Sequence[ImportRow], dry_run: bool = False) -> ImportStats:
    stats = ImportStats()
    async with SessionLocal() as session:
        cache = await GeoCache.load(session)

        async def maybe_flush() -> None:
            if not dry_run:
                await session.flush()

        for row in rows:
            if row.city:
                resolved_city = city_catalog.resolve_city_name(row.city)
                if resolved_city:
                    row.city = resolved_city
                elif not city_catalog.is_allowed_city(row.city):
                    stats.add_questionable(row.kind, row.city, "!city_not_allowed", 0.0)
                    continue
            if row.kind == "city":
                canonical_name = city_catalog.resolve_city_name(row.name) or row.name
                if not city_catalog.is_allowed_city(canonical_name):
                    stats.add_questionable("city", row.name, "!city_not_allowed", 0.0)
                    continue
                row.name = canonical_name
                existing_match = _best_match(row.name, cache.city_by_name.keys())
                if existing_match and existing_match[1] >= DUP_THRESHOLD:
                    stats.mark_duplicate("city")
                    continue
                if existing_match and existing_match[1] >= QUESTIONABLE_THRESHOLD:
                    stats.add_questionable("city", row.name, existing_match[0], existing_match[1])
                    continue
                stmt = (
                    pg_insert(m.cities)
                    .values(name=row.name, is_active=True, centroid_lat=row.centroid_lat, centroid_lon=row.centroid_lon)
                    .on_conflict_do_nothing()
                    .returning(m.cities.id)
                )
                inserted = await session.execute(stmt)
                await maybe_flush()
                city_id = inserted.scalar()
                if city_id is None:
                    city_id = (
                        await session.execute(
                            select(m.cities.id).where(m.cities.name == row.name)
                        )
                    ).scalar_one()
                else:
                    stats.mark_created("city")
                cache.register_city(city_id, row.name)
                continue

            if row.kind == "district":
                if not row.city:
                    continue
                city_id = cache.get_city_id(row.city)
                if city_id is None:
                    continue
                existing_for_city = cache.districts_by_city.get(city_id, {})
                existing_match = _best_match(row.name, existing_for_city.keys())
                if existing_match and existing_match[1] >= DUP_THRESHOLD:
                    stats.mark_duplicate("district")
                    continue
                if existing_match and existing_match[1] >= QUESTIONABLE_THRESHOLD:
                    stats.add_questionable("district", row.name, existing_match[0], existing_match[1])
                    continue
                stmt = (
                    pg_insert(m.districts)
                    .values(city_id=city_id, name=row.name, centroid_lat=row.centroid_lat, centroid_lon=row.centroid_lon)
                    .on_conflict_do_nothing()
                    .returning(m.districts.id)
                )
                inserted = await session.execute(stmt)
                await maybe_flush()
                district_id = inserted.scalar()
                if district_id is None:
                    district_id = (
                        await session.execute(
                            select(m.districts.id).where(
                                (m.districts.city_id == city_id)
                                & (m.districts.name == row.name)
                            )
                        )
                    ).scalar_one()
                else:
                    stats.mark_created("district")
                cache.register_district(city_id, district_id, row.name)
                continue

            if row.kind == "street":
                if not row.city:
                    continue
                city_id = cache.get_city_id(row.city)
                if city_id is None:
                    continue
                district_id: Optional[int] = None
                if row.district:
                    district_id = cache.get_district_id(city_id, row.district)
                    if district_id is None:
                        continue
                existing_streets = cache.streets_by_scope.get((city_id, district_id), set())
                existing_match = _best_match(row.name, existing_streets)
                if existing_match and existing_match[1] >= DUP_THRESHOLD:
                    stats.mark_duplicate("street")
                    continue
                if existing_match and existing_match[1] >= QUESTIONABLE_THRESHOLD:
                    stats.add_questionable("street", row.name, existing_match[0], existing_match[1])
                    continue
                stmt = (
                    pg_insert(m.streets)
                    .values(city_id=city_id, district_id=district_id, name=row.name, centroid_lat=row.centroid_lat, centroid_lon=row.centroid_lon)
                    .on_conflict_do_nothing()
                )
                await session.execute(stmt)
                await maybe_flush()
                cache.register_street(city_id, district_id, row.name)
                stats.mark_created("street")

        if dry_run:
            await session.rollback()
        else:
            await session.commit()

    return stats


async def _main() -> None:
    parser = argparse.ArgumentParser(description="Import geo dictionaries with RapidFuzz dedupe")
    parser.add_argument("--input", required=True, help="Path to CSV file")
    parser.add_argument("--delimiter", default=";", help="CSV delimiter (default ';')")
    parser.add_argument("--dry-run", action="store_true", help="Validate only, without writing to DB")
    args = parser.parse_args()

    path = Path(args.input)
    if not path.exists():
        raise SystemExit(f"Input file not found: {path}")

    rows = parse_rows(path, delimiter=args.delimiter)
    stats = await import_rows(rows, dry_run=args.dry_run)
    print(stats.render_summary())


if __name__ == "__main__":
    asyncio.run(_main())

