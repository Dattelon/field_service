# Фикс для _load_config - универсальная сигнатура
# Вставить этот блок в field_service/services/distribution_scheduler.py
# Заменить существующую функцию _load_config

from contextlib import asynccontextmanager
from typing import Optional
from datetime import datetime, timezone
from dataclasses import dataclass
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class DistConfig:
    """Конфигурация распределения с безопасными дефолтами."""
    tick_seconds: int = 15
    sla_seconds: int = 120
    rounds: int = 2
    top_log_n: int = 10
    to_admin_after_min: int = 10


@asynccontextmanager
async def _maybe_session(session: Optional[AsyncSession]):
    """Context manager для работы с опциональной сессией."""
    if session is not None:
        # Используем переданную сессию, не закрываем её
        yield session
        return
    
    # Создаём временную сессию через SessionLocal
    from field_service.db.session import SessionLocal
    async with SessionLocal() as s:
        yield s


async def _load_config(session: Optional[AsyncSession] = None) -> DistConfig:
    """
    Загружает конфигурацию распределения из БД с кэшированием.
    
    STEP 2.3: Изменён тик с 30 на 15 секунд.
    STEP 3.1: Добавлено кэширование с TTL = 5 минут.
    
    Универсальная сигнатура:
    - Если session передан — используем его
    - Если session=None — создаём временную через SessionLocal
    - Кэш работает независимо от источника сессии
    - Результат кэшируется на 5 минут
    
    Args:
        session: Опциональная сессия БД (для тестов и прямых вызовов)
    """
    global _CONFIG_CACHE, _CONFIG_CACHE_TIMESTAMP

    now = datetime.now(timezone.utc)

    # Проверка кэша
    if (
        _CONFIG_CACHE is not None
        and _CONFIG_CACHE_TIMESTAMP is not None
        and (now - _CONFIG_CACHE_TIMESTAMP).total_seconds() < _CONFIG_CACHE_TTL_SECONDS
    ):
        return _CONFIG_CACHE

    # Загрузка через context manager
    from field_service.services.settings_service import get_int
    
    async with _maybe_session(session) as s:
        config = DistConfig(
            tick_seconds=await get_int("distribution_tick_seconds", 15),
            sla_seconds=await get_int("distribution_sla_seconds", 120),
            rounds=await get_int("distribution_rounds", 2),
            top_log_n=await get_int("distribution_log_topn", 10),
            to_admin_after_min=await get_int("escalate_to_admin_after_min", 10),
        )

    # Обновление кэша
    _CONFIG_CACHE = config
    _CONFIG_CACHE_TIMESTAMP = now

    logger.debug("[dist] config reloaded from DB and cached")
    return config
