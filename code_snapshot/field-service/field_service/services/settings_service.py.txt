from __future__ import annotations
import json
import re
from contextlib import asynccontextmanager
from datetime import time
from time import monotonic
from typing import Iterable, Mapping, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession
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


@asynccontextmanager
async def _maybe_session(session: Optional[AsyncSession]):
    """Context manager для работы с опциональной сессией."""
    if session is not None:
        # Используем переданную сессию, не закрываем её
        yield session
        return
    # Создаём временную сессию через SessionLocal
    async with SessionLocal() as s:
        yield s


async def get_raw(key: str, *, session: Optional[AsyncSession] = None) -> Optional[Tuple[str, str]]:
    """Получить raw значение настройки.
    
    Args:
        key: Ключ настройки
        session: Опциональная тестовая сессия
        
    Returns:
        Кортеж (value, value_type) или None
    """
    async with _maybe_session(session) as s:
        try:
            q = await s.execute(
                select(m.settings.value, m.settings.value_type).where(m.settings.key == key)
            )
        except OperationalError:
            return None
        row = q.first()
        return (row[0], row[1]) if row else None


async def get_int(key: str, default: int, *, session: Optional[AsyncSession] = None) -> int:
    """Получить целочисленное значение настройки.
    
    Args:
        key: Ключ настройки
        default: Значение по умолчанию
        session: Опциональная тестовая сессия
        
    Returns:
        Целочисленное значение или default
    """
    row = await get_raw(key, session=session)
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


async def get_time(key: str, default_str: str, *, session: Optional[AsyncSession] = None) -> time:
    """Получить значение времени из настроек.
    
    Args:
        key: Ключ настройки
        default_str: Значение по умолчанию в формате "HH:MM"
        session: Опциональная тестовая сессия
        
    Returns:
        Объект time
    """
    row = await get_raw(key, session=session)
    s = row[0] if row else default_str
    t = _parse_time(s)
    if t:
        return t
    # fallback к env
    return _parse_time(default_str) or time(10, 0)


async def get_value(
    key: str, 
    default: Optional[str] = None,
    *,
    session: Optional[AsyncSession] = None
) -> Optional[str]:
    """Return raw string value for a setting or default if missing.
    
    Args:
        key: Ключ настройки
        default: Значение по умолчанию
        session: Опциональная тестовая сессия
        
    Returns:
        Строковое значение или default
    """
    row = await get_raw(key, session=session)
    if not row:
        return default
    value, _ = row
    if value is None:
        return default
    return str(value)


async def get_values(
    keys: Sequence[str],
    *,
    session: Optional[AsyncSession] = None
) -> dict[str, tuple[str, str]]:
    """Fetch raw values for multiple settings at once.
    
    Args:
        keys: Список ключей настроек
        session: Опциональная тестовая сессия
        
    Returns:
        Словарь {key: (value, value_type)}
    """
    if not keys:
        return {}
    async with _maybe_session(session) as s:
        result = await s.execute(
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


async def set_value(
    key: str, 
    value: object, 
    *, 
    value_type: str = "STR",
    session: Optional[AsyncSession] = None
) -> None:
    """Установить одно значение настройки.
    
    Args:
        key: Ключ настройки
        value: Значение
        value_type: Тип значения
        session: Опциональная тестовая сессия
    """
    await set_values({key: (value, value_type)}, session=session)


async def set_values(
    values: Mapping[str, tuple[object, str]],
    *,
    session: Optional[AsyncSession] = None
) -> None:
    """Upsert multiple settings values preserving their declared types.
    
    Args:
        values: Словарь {key: (value, value_type)}
        session: Опциональная тестовая сессия
    """
    if not values:
        return
    async with _maybe_session(session) as s:
        async with s.begin():
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
                await s.execute(stmt)
    invalidate_working_window_cache()


async def get_working_window(
    *, 
    refresh: bool = False,
    session: Optional[AsyncSession] = None
) -> Tuple[time, time]:
    """Получить рабочее окно (start, end) времени.
    
    Args:
        refresh: Принудительно обновить кэш
        session: Опциональная тестовая сессия
        
    Returns:
        Кортеж (start_time, end_time)
    """
    global _WORKING_WINDOW_CACHE
    now = monotonic()
    if (
        not refresh
        and _WORKING_WINDOW_CACHE is not None
        and now - _WORKING_WINDOW_CACHE[1] < _WORKING_WINDOW_TTL
    ):
        return _WORKING_WINDOW_CACHE[0]

    start = await get_time("working_hours_start", env_settings.working_hours_start, session=session)
    end = await get_time("working_hours_end", env_settings.working_hours_end, session=session)
    _WORKING_WINDOW_CACHE = ((start, end), now)
    return start, end


def invalidate_working_window_cache() -> None:
    """Clear cached working-window values (e.g. after admin update)."""
    global _WORKING_WINDOW_CACHE
    _WORKING_WINDOW_CACHE = None
