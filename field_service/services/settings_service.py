from __future__ import annotations
import re
from datetime import time
from typing import Optional, Tuple
from sqlalchemy import select, text
from field_service.db.session import SessionLocal
from field_service.db import models as m
from field_service.config import settings as env_settings

_TIME_RE = re.compile(r"^\d{1,2}:\d{2}$")

async def get_raw(key: str) -> Optional[Tuple[str, str]]:
    async with SessionLocal() as session:
        q = await session.execute(select(m.settings.value, m.settings.value_type).where(m.settings.key == key))
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

async def get_working_window() -> Tuple[time, time]:
    start = await get_time("working_hours_start", env_settings.working_hours_start)
    end = await get_time("working_hours_end", env_settings.working_hours_end)
    return start, end
