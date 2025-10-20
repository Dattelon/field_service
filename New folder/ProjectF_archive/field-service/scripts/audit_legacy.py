#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Iterable

from sqlalchemy import func, or_, select, text

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from field_service.db import models as m
from field_service.db.session import SessionLocal

LEGACY_TERMS = (
    "scheduled_date",
    "time_slot_start",
    "time_slot_end",
    "slot_label",
    "total_price",
    "latitude",
    "longitude",
)

LEGACY_COLUMNS = (
    "scheduled_date",
    "time_slot_start",
    "time_slot_end",
    "slot_label",
    "total_price",
    "latitude",
    "longitude",
)

SKIP_DIRS = {".git", "__pycache__", ".mypy_cache", ".pytest_cache", "node_modules"}
SKIP_SUFFIXES = {
    ".pyc",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".ico",
    ".lock",
    ".log",
    ".gz",
    ".zip",
}


async def _audit_db() -> tuple[int, int, list[str]]:
    async with SessionLocal() as session:
        timeslot_stmt = select(func.count()).where(
            or_(
                m.orders.timeslot_start_utc.is_(None),
                m.orders.timeslot_end_utc.is_(None),
            )
        )
        totals_stmt = select(func.count()).where(m.orders.total_sum.is_(None))

        timeslot_missing = (await session.execute(timeslot_stmt)).scalar_one()
        total_sum_missing = (await session.execute(totals_stmt)).scalar_one()

        columns_sql = """
            SELECT column_name
              FROM information_schema.columns
             WHERE table_name = 'orders'
               AND column_name IN ({columns})
        """.format(columns=", ".join(f"'{col}'" for col in LEGACY_COLUMNS))
        legacy_columns = [row[0] for row in (await session.execute(text(columns_sql))).all()]

    return int(timeslot_missing), int(total_sum_missing), legacy_columns


def _iter_source_files(root: Path) -> Iterable[Path]:
    for current_root, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for filename in filenames:
            path = Path(current_root, filename)
            if path.suffix.lower() in SKIP_SUFFIXES:
                continue
            yield path


def _scan_sources(root: Path) -> dict[str, list[str]]:
    results: dict[str, list[str]] = {term: [] for term in LEGACY_TERMS}
    for path in _iter_source_files(root):
        try:
            text_data = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for term in LEGACY_TERMS:
            if term in text_data:
                results[term].append(str(path.relative_to(root)))
    return results


def main() -> None:
    root = Path(__file__).resolve().parents[1]

    try:
        timeslot_missing, total_sum_missing, legacy_columns = asyncio.run(_audit_db())
    except Exception as exc:  # pragma: no cover - diagnostic output
        print(f"DB audit failed: {exc}", file=sys.stderr)
        sys.exit(1)

    print("DB audit:")
    print(
        "  orders missing timeslot_*_utc: "
        f"{timeslot_missing}"
    )
    print(
        "  orders missing total_sum: "
        f"{total_sum_missing}"
    )
    if legacy_columns:
        print("  legacy columns still present:")
        for column in legacy_columns:
            print(f"    - {column}")
    else:
        print("  legacy columns still present: 0")
    print()

    print("Source scan:")
    scan_results = _scan_sources(root)
    for term, matches in scan_results.items():
        print(f"  {term}: {len(matches)} occurrence(s)")
        for match in matches:
            print(f"    - {match}")

    blockers = (
        timeslot_missing > 0
        or total_sum_missing > 0
        or bool(legacy_columns)
    )
    sys.exit(1 if blockers else 0)


if __name__ == "__main__":
    main()
