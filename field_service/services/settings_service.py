from __future__ import annotations
import json
import re
from datetime import time
from time import monotonic
from typing import Iterable, Mapping, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.dialects.postgresql import insert
from field_service.db.session import SessionLocal
from field_service.db import models as m
from field_service.config import settings as env_settings


_WORKING_WINDOW_CACHE: tuple[tuple[time, time], float] | None = None
_WORKING_WINDOW_TTL = 60.0


def get_timezone() -> ZoneInfo:
    """Return project timezone from configuration, defaulting to UTC."""
    try:
        return ZoneInfo(env_settings.timezone)
    except Exception:
        return ZoneInfo("UTC")


_TIME_RE = re.compile(r"^\d{1,2}:\d{2}$")


async def get_raw(key: str) -> Optional[Tuple[str, str]]:
    async with SessionLocal() as session:
        try:
            q = await session.execute(
                select(m.settings.value, m.settings.value_type).where(m.settings.key == key)
            )
        except OperationalError:
            return None
        row = q.first()
        return (row[0], row[1]) if row else None


async def get_int(key: str, default: int) -> int:
    row = await get_raw(key)
    if not row:
        return int(default)
    val, vtype = row
    try:
        return int(val)
    except Exception:
        return int(default)


def _parse_time(s: str) -> Optional[time]:
    if not _TIME_RE.fullmatch(s or ""):
        return None
    hh, mm = map(int, s.split(":"))
    if 0 <= hh < 24 and 0 <= mm < 60:
        return time(hour=hh, minute=mm)
    return None


async def get_time(key: str, default_str: str) -> time:
    row = await get_raw(key)
    s = row[0] if row else default_str
    t = _parse_time(s)
    if t:
        return t
    # fallback к env
    return _parse_time(default_str) or time(10, 0)


async def get_value(key: str, default: Optional[str] = None) -> Optional[str]:
    """Return raw string value for a setting or default if missing."""
    row = await get_raw(key)
    if not row:
        return default
    value, _ = row
    if value is None:
        return default
    return str(value)


async def get_values(keys: Sequence[str]) -> dict[str, tuple[str, str]]:
    """Fetch raw values for multiple settings at once."""
    if not keys:
        return {}
    async with SessionLocal() as session:
        result = await session.execute(
            select(m.settings.key, m.settings.value, m.settings.value_type).where(
                m.settings.key.in_(list(keys))
            )
        )
        return {row[0]: (row[1], row[2]) for row in result}


def _normalize_value_type(value_type: Optional[str]) -> str:
    vt = (value_type or "STR").upper()
    return vt


def _serialize_value(value: object, value_type: str) -> str:
    vt = value_type.upper()
    if vt == "JSON":
        return json.dumps(value, ensure_ascii=False)
    if vt == "BOOL":
        if isinstance(value, str):
            return "true" if value.strip().lower() in {"1", "true", "yes", "on"} else "false"
        return "true" if bool(value) else "false"
    if vt == "TIME" and isinstance(value, time):
        return value.strftime('%H:%M')
    return "" if value is None else str(value)


async def set_value(key: str, value: object, *, value_type: str = "STR") -> None:
    await set_values({key: (value, value_type)})


async def set_values(values: Mapping[str, tuple[object, str]]) -> None:
    """Upsert multiple settings values preserving their declared types."""
    if not values:
        return
    async with SessionLocal() as session:
        async with session.begin():
            for key, (raw_value, raw_type) in values.items():
                vt = _normalize_value_type(raw_type)
                payload = _serialize_value(raw_value, vt)
                stmt = insert(m.settings).values(
                    key=key, value=payload, value_type=vt
                )
                stmt = stmt.on_conflict_do_update(
                    index_elements=[m.settings.key],
                    set_={"value": payload, "value_type": vt},
                )
                await session.execute(stmt)
    invalidate_working_window_cache()


async def get_working_window(*, refresh: bool = False) -> Tuple[time, time]:
    global _WORKING_WINDOW_CACHE
    now = monotonic()
    if (
        not refresh
        and _WORKING_WINDOW_CACHE is not None
        and now - _WORKING_WINDOW_CACHE[1] < _WORKING_WINDOW_TTL
    ):
        return _WORKING_WINDOW_CACHE[0]

    start = await get_time("working_hours_start", env_settings.working_hours_start)
    end = await get_time("working_hours_end", env_settings.working_hours_end)
    _WORKING_WINDOW_CACHE = ((start, end), now)
    return start, end


def invalidate_working_window_cache() -> None:
    """Clear cached working-window values (e.g. after admin update)."""
    global _WORKING_WINDOW_CACHE
    _WORKING_WINDOW_CACHE = None
