from __future__ import annotations

import asyncio
import logging
import random
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from typing import Iterable, Optional
from zoneinfo import ZoneInfo

from aiogram import Bot
from sqlalchemy import insert, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from field_service.config import settings as env_settings
from field_service.db import models as m
from field_service.db.session import SessionLocal
from field_service.services import live_log, time_service, settings_service as settings_store
from field_service.services.distribution_worker import expire_sent_offers
from field_service.infra.notify import send_alert, send_report
from field_service.services.settings_service import (
    get_int,
)
from field_service.infra.structured_logging import (
    DistributionEvent,
    log_distribution_event,
)
from field_service.services.push_notifications import (
    NOTIFICATION_TEMPLATES,
    NotificationEvent,
    notify_admin,
    notify_master,
)
from field_service.services.skills_map import get_skill_code

DEFAULT_MAX_ACTIVE_LIMIT = 5


# Обратная совместимость для candidates.py
def _skill_code_for_category(category: str | None) -> str | None:
    """Алиас для get_skill_code из skills_map.py (обратная совместимость)."""
    return get_skill_code(category)


logger = logging.getLogger("distribution")

ADVISORY_LOCK_KEY = 982734
DEFERRED_LOGGED: set[int] = set()
WORKDAY_START_DEFAULT = time_service.parse_time_string(env_settings.workday_start, default=time(10, 0))
WORKDAY_END_DEFAULT = time_service.parse_time_string(env_settings.workday_end, default=time(20, 0))

# Escalation reason constants
ESC_REASON_LOGIST = "distribution_escalate_logist"
ESC_REASON_ADMIN = "distribution_escalate_admin"

#  STEP 3.1:   
_CONFIG_CACHE: Optional[DistConfig] = None
_CONFIG_CACHE_TIMESTAMP: Optional[datetime] = None
_CONFIG_CACHE_TTL_SECONDS = 300  # 5 

def _dist_log(message: str, *, level: str = "INFO") -> None:
    try:
        live_log.push("dist", message, level=level)
    except Exception:
        pass


async def _report(bot: Bot | None, message: str) -> None:
    if bot is None:
        return
    await send_report(bot, message)


@dataclass
class DistConfig:
    """Конфигурация распределения с безопасными дефолтами."""
    tick_seconds: int = 15
    sla_seconds: int = 120
    rounds: int = 2
    top_log_n: int = 10
    to_admin_after_min: int = 10



@dataclass
class OrderForDistribution:
    id: int
    city_id: int
    city_name: str
    district_id: Optional[int]
    district_name: Optional[str]
    preferred_master_id: Optional[int]
    status: str
    category: Optional[str]
    order_type: Optional[str]
    no_district: bool
    escalated_logist_at: Optional[datetime]
    escalated_admin_at: Optional[datetime]
    escalation_logist_notified_at: Optional[datetime]
    escalation_admin_notified_at: Optional[datetime]


@dataclass(slots=True)
class CityDistributionContext:
    """Prepared distribution context for a particular city."""

    city_id: int
    city_name: str
    timezone: ZoneInfo
    logist_chat_ids: tuple[int, ...]
    admin_chat_ids: tuple[int, ...]


def _build_city_contexts(
    *,
    cities: Iterable[tuple[int, str, Optional[str]]],
    staff_rows: Iterable[tuple[int, m.StaffRole, Optional[int]]],
    default_timezone: str,
) -> dict[int, CityDistributionContext]:
    """Prepare city distribution contexts from raw DB rows."""

    tz_cache: dict[str, ZoneInfo] = {}
    contexts: dict[int, dict[str, object]] = {}

    for city_id, city_name, tz_name in cities:
        tz_key = tz_name or default_timezone
        tz = tz_cache.get(tz_key)
        if tz is None:
            tz = time_service.resolve_timezone(tz_key)
            tz_cache[tz_key] = tz
        contexts[int(city_id)] = {
            "city_id": int(city_id),
            "city_name": city_name,
            "timezone": tz,
            "logist_ids": set(),
            "admin_ids": set(),
        }

    if not contexts:
        return {}

    global_admins: set[int] = set()
    global_logists: set[int] = set()

    for telegram_id, role, assigned_city_id in staff_rows:
        if telegram_id is None:
            continue
        try:
            role_value = m.StaffRole(role)
        except (ValueError, TypeError):
            continue

        chat_id = int(telegram_id)
        city_id = int(assigned_city_id) if assigned_city_id is not None else None

        if role_value == m.StaffRole.LOGIST:
            if city_id and city_id in contexts:
                contexts[city_id]["logist_ids"].add(chat_id)
            else:
                global_logists.add(chat_id)
        elif role_value in (m.StaffRole.CITY_ADMIN, m.StaffRole.GLOBAL_ADMIN):
            if city_id and city_id in contexts:
                contexts[city_id]["admin_ids"].add(chat_id)
            if role_value == m.StaffRole.GLOBAL_ADMIN and city_id is None:
                global_admins.add(chat_id)

    for ctx in contexts.values():
        logist_ids: set[int] = ctx["logist_ids"]  # type: ignore[assignment]
        admin_ids: set[int] = ctx["admin_ids"]  # type: ignore[assignment]
        admin_ids.update(global_admins)
        logist_ids.update(global_logists)
        #        
        logist_ids.update(admin_ids)

    return {
        city_id: CityDistributionContext(
            city_id=data["city_id"],
            city_name=data["city_name"],
            timezone=data["timezone"],
            logist_chat_ids=tuple(sorted(data["logist_ids"])),
            admin_chat_ids=tuple(sorted(data["admin_ids"])),
        )
        for city_id, data in contexts.items()
    }


async def _fetch_city_contexts(
    session: AsyncSession,
    city_ids: set[int],
) -> dict[int, CityDistributionContext]:
    """Fetch city distribution context (timezone and staff recipients)."""

    if not city_ids:
        return {}

    city_rows = await session.execute(
        select(m.cities.id, m.cities.name, m.cities.timezone).where(m.cities.id.in_(city_ids))
    )
    staff_rows = await session.execute(
        select(
            m.staff_users.tg_user_id,
            m.staff_users.role,
            m.staff_cities.city_id,
        )
        .select_from(m.staff_users)
        .outerjoin(m.staff_cities, m.staff_cities.staff_user_id == m.staff_users.id)
        .where(
            m.staff_users.is_active.is_(True),
            m.staff_users.tg_user_id.is_not(None),
            m.staff_users.role.in_(
                (
                    m.StaffRole.LOGIST,
                    m.StaffRole.CITY_ADMIN,
                    m.StaffRole.GLOBAL_ADMIN,
                )
            ),
            or_(
                m.staff_cities.city_id.is_(None),
                m.staff_cities.city_id.in_(city_ids),
            ),
        )
    )

    city_records = city_rows.all()
    staff_records = staff_rows.all()

    return _build_city_contexts(
        cities=[(int(rec.id), str(rec.name), rec.timezone) for rec in city_records],
        staff_rows=[(rec.tg_user_id, rec.role, rec.city_id) for rec in staff_records],
        default_timezone=env_settings.timezone,
    )


def _compose_staff_escalation_message(
    event: NotificationEvent,
    *,
    order_id: int,
    city: str,
    district: str,
    timeslot: str,
    category: str,
    reason: Optional[str] = None,
) -> str:
    template = NOTIFICATION_TEMPLATES.get(event)
    if template:
        try:
            return template.format(
                order_id=order_id,
                city=city,
                district=district,
                timeslot=timeslot,
                category=category,
                reason=reason or "",
            )
        except KeyError:
            pass

    if event == NotificationEvent.ESCALATION_ADMIN:
        prefix = "🚨 <b>Критичная эскалация</b>"
        suffix = "Требуется срочное вмешательство администратора. Заявка долго без мастера."
    else:
        prefix = "⚠️ <b>Эскалация заявки</b>"
        suffix = "Заявка долго не назначена. Требуется вмешательство логиста."

    lines = [
        prefix,
        "",
        f"ID заявки: #{order_id}",
        f"Город: {city}",
        f"Район: {district}",
    ]
    if timeslot:
        lines.append(f"Время: {timeslot}")
    if category:
        lines.append(f"Категория: {category}")
    if reason:
        lines.append("")
        lines.append(f"Причина: {reason}")
    lines.append("")
    lines.append(suffix)
    return "\n".join(lines)


async def _notify_city_staff(
    bot: Bot | None,
    chat_ids: Iterable[int],
    *,
    text: str,
) -> None:
    if bot is None:
        return

    delivered: set[int] = set()
    for chat_id in chat_ids:
        if chat_id in delivered:
            continue
        delivered.add(chat_id)
        try:
            await bot.send_message(chat_id, text, parse_mode="HTML")
        except Exception:
            logger.warning("[dist] failed to notify staff chat=%s", chat_id, exc_info=True)


async def _notify_logist_escalation(
    session: AsyncSession,
    order: OrderForDistribution,
    *,
    bot: Bot | None,
    alerts_chat_id: Optional[int],
    city_ctx: Optional[CityDistributionContext],
    message: str,
    reason: str,
) -> None:
    if order.escalation_logist_notified_at is not None:
        return

    notified_at = await _mark_logist_notification_sent(session, order.id)
    order.escalation_logist_notified_at = notified_at
    logger.info("[dist] order=%s logist_notification_sent_at=%s", order.id, notified_at.isoformat())

    order_data = {}
    if city_ctx is not None:
        order_data = await _get_order_notification_data(
            session,
            order.id,
            timezone=city_ctx.timezone,
        )

    await _report(bot, message)
    if bot and alerts_chat_id:
        await notify_admin(
            bot,
            alerts_chat_id,
            event=NotificationEvent.ESCALATION_LOGIST,
            order_id=order.id,
        )

    if city_ctx and city_ctx.logist_chat_ids:
        text = _compose_staff_escalation_message(
            NotificationEvent.ESCALATION_LOGIST,
            order_id=order.id,
            city=order_data.get("city") or city_ctx.city_name,
            district=order_data.get("district") or (order.district_name or " "),
            timeslot=order_data.get("timeslot") or " ",
            category=order_data.get("category") or " ",
            reason=reason,
        )
        await _notify_city_staff(bot, city_ctx.logist_chat_ids, text=text)


async def _notify_admin_escalation(
    session: AsyncSession,
    order: OrderForDistribution,
    *,
    bot: Bot | None,
    alerts_chat_id: Optional[int],
    city_ctx: Optional[CityDistributionContext],
    message: str,
    reason: str,
) -> None:
    if order.escalation_admin_notified_at is not None:
        return

    notified_at = await _mark_admin_notification_sent(session, order.id)
    order.escalation_admin_notified_at = notified_at
    logger.info("[dist] order=%s admin_notification_sent_at=%s", order.id, notified_at.isoformat())

    order_data = {}
    if city_ctx is not None:
        order_data = await _get_order_notification_data(
            session,
            order.id,
            timezone=city_ctx.timezone,
        )

    await _report(bot, message)
    if bot and alerts_chat_id:
        await notify_admin(
            bot,
            alerts_chat_id,
            event=NotificationEvent.ESCALATION_ADMIN,
            order_id=order.id,
        )

    if city_ctx and city_ctx.admin_chat_ids:
        text = _compose_staff_escalation_message(
            NotificationEvent.ESCALATION_ADMIN,
            order_id=order.id,
            city=order_data.get("city") or city_ctx.city_name,
            district=order_data.get("district") or (order.district_name or " "),
            timeslot=order_data.get("timeslot") or " ",
            category=order_data.get("category") or " ",
            reason=reason,
        )
        await _notify_city_staff(bot, city_ctx.admin_chat_ids, text=text)


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
    async with _maybe_session(session) as s:
        # Читаем настройки напрямую из БД, обходя get_int
        # т.к. get_int всегда создаёт свою сессию через SessionLocal
        settings_query = await s.execute(
            select(m.settings.key, m.settings.value).where(
                m.settings.key.in_([
                    "distribution_tick_seconds",
                    "distribution_sla_seconds",
                    "distribution_rounds",
                    "distribution_log_topn",
                    "escalate_to_admin_after_min",
                ])
            )
        )
        settings_dict = {row.key: row.value for row in settings_query}
        
        def get_setting_int(key: str, default: int) -> int:
            """Получить int значение настройки с fallback на дефолт."""
            value = settings_dict.get(key)
            if value is None:
                return default
            try:
                return int(value)
            except (ValueError, TypeError):
                return default
        
        config = DistConfig(
            tick_seconds=get_setting_int("distribution_tick_seconds", 15),
            sla_seconds=get_setting_int("distribution_sla_seconds", 120),
            rounds=get_setting_int("distribution_rounds", 2),
            top_log_n=get_setting_int("distribution_log_topn", 10),
            to_admin_after_min=get_setting_int("escalate_to_admin_after_min", 10),
        )

    # Обновление кэша
    _CONFIG_CACHE = config
    _CONFIG_CACHE_TIMESTAMP = now

    logger.debug("[dist] config reloaded from DB and cached")
    return config


async def _try_advisory_lock(session: AsyncSession) -> bool:
    row = await session.execute(
        text("SELECT pg_try_advisory_lock(:k)").bindparams(k=ADVISORY_LOCK_KEY)
    )
    return bool(row.scalar())


async def _db_now(session: AsyncSession):
    row = await session.execute(text("SELECT NOW()"))
    return row.scalar()


async def _get_order_notification_data(
    session: AsyncSession,
    order_id: int,
    *,
    timezone: ZoneInfo | None = None,
) -> dict:
    """    push- ."""
    from typing import Any
    
    result = await session.execute(
        text("""
            SELECT 
                o.id,
                c.name AS city_name,
                d.name AS district_name,
                o.timeslot_start_utc,
                o.timeslot_end_utc,
                o.category,
                o.description
            FROM orders o
            JOIN cities c ON c.id = o.city_id
            LEFT JOIN districts d ON d.id = o.district_id
            WHERE o.id = :order_id
        """).bindparams(order_id=order_id)
    )
    row = result.mappings().first()
    if not row:
        return {}
    
    #  timeslot
    timeslot = " "
    if row["timeslot_start_utc"] and row["timeslot_end_utc"]:
        start = row["timeslot_start_utc"]
        end = row["timeslot_end_utc"]
        #    
        tz = timezone or time_service.resolve_timezone(env_settings.timezone)
        start_local = start.astimezone(tz)
        end_local = end.astimezone(tz)
        timeslot = f"{start_local.strftime('%H:%M')}-{end_local.strftime('%H:%M')}"
    
    #  
    category_labels = {
        "ELECTRICS": " ",
        "PLUMBING": " ",
        "APPLIANCES": "  ",
        "WINDOWS": " ",
        "HANDYMAN": "  ",
        "ROADSIDE": "   ",
    }
    category = category_labels.get(row["category"], row["category"] or " ")
    
    return {
        "order_id": order_id,
        "city": row["city_name"] or " ",
        "district": row["district_name"] or " ",
        "timeslot": timeslot,
        "category": category,
        "description": row.get("description") or "",
    }


async def _fetch_orders_for_distribution(
    session: AsyncSession,
) -> list[OrderForDistribution]:
    result = await session.execute(
        text(
            """
        SELECT o.id,
               o.city_id,
               c.name AS city_name,
               o.district_id,
               d.name AS district_name,
               o.preferred_master_id,
               o.status,
               o.category,
               o.type AS order_type,
               o.no_district,
               o.dist_escalated_logist_at,
               o.dist_escalated_admin_at,
               o.escalation_logist_notified_at,
               o.escalation_admin_notified_at
         FROM orders o
          JOIN cities c ON c.id = o.city_id
          LEFT JOIN districts d ON d.id = o.district_id
         WHERE (
                  o.status IN ('SEARCHING','GUARANTEE')
               OR (
                    o.status = 'DEFERRED'
                AND EXISTS (
                      SELECT 1 FROM offers off
                       WHERE off.order_id = o.id
                         AND off.state IN ('SENT','VIEWED','ACCEPTED')
                )
               )
           )
           AND o.assigned_master_id IS NULL
         ORDER BY
           -- 1.    ( )
           (o.dist_escalated_admin_at IS NOT NULL) DESC,
           -- 2.  
           (o.type = 'GUARANTEE' OR o.status = 'GUARANTEE') DESC,
           -- 3.  
           (o.timeslot_start_utc IS NOT NULL AND o.timeslot_start_utc < NOW()) DESC,
           -- 4.   
           (o.dist_escalated_logist_at IS NOT NULL) DESC,
           -- 5.   (oldest first)
           o.created_at ASC
         LIMIT 100
        """
        )
    )
    rows = result.mappings().all()
    orders: list[OrderForDistribution] = []
    for row in rows:
        orders.append(
            OrderForDistribution(
                id=int(row["id"]),
                city_id=int(row["city_id"]),
                city_name=str(row["city_name"]),
                district_id=row["district_id"],
                district_name=row.get("district_name"),
                preferred_master_id=row["preferred_master_id"],
                status=str(row["status"]),
                category=row["category"],
                order_type=row["order_type"],
                no_district=(
                    bool(row["no_district"])
                    if isinstance(row["no_district"], bool)
                    else str(row["no_district"]).lower() in {"1", "true", "t", "yes"}
                ),
                escalated_logist_at=row["dist_escalated_logist_at"],
                escalated_admin_at=row["dist_escalated_admin_at"],
                escalation_logist_notified_at=row["escalation_logist_notified_at"],
                escalation_admin_notified_at=row["escalation_admin_notified_at"],
            )
        )
    return orders



async def _expire_overdue_offer(session: AsyncSession, order_id: int, sla_seconds: int) -> Optional[int]:
    """  SENT  EXPIRED,  master_id  None."""
    #       SENT  
    from sqlalchemy import update, func
    row = await session.execute(
        update(m.offers)
        .where(
            m.offers.order_id == order_id,
            m.offers.state == m.OfferState.SENT,
            m.offers.expires_at <= func.clock_timestamp(),
        )
        .values(state=m.OfferState.EXPIRED, responded_at=func.now())
        .returning(m.offers.master_id)
    )
    t = row.first()
    if not t:
        # Fallback: expires_at is NULL, expire by sent_at and SLA (raw SQL for Postgres make_interval named arg)
        from sqlalchemy import text
        row2 = await session.execute(
            text(
                """
            UPDATE offers
               SET state='EXPIRED', responded_at=NOW()
             WHERE order_id=:oid
               AND state='SENT'
               AND (
                    sent_at <= clock_timestamp() - make_interval(secs => :sla)
                 OR (expires_at IS NOT NULL AND expires_at <= clock_timestamp())
               )
             RETURNING master_id
            """
            ).bindparams(oid=order_id, sla=sla_seconds)
        )
        t = row2.first()
    return int(t[0]) if t else None


async def _current_round(session: AsyncSession, order_id: int) -> int:
    row = await session.execute(
        text(
            "SELECT COALESCE(MAX(round_number),0) FROM offers WHERE order_id=:oid"
        ).bindparams(oid=order_id)
    )
    r = int(row.scalar() or 0)
    return r


async def _was_logist_escalated_before(session: AsyncSession, order_id: int) -> bool:
    """Return True if the order has evidence of previous logist escalation.

    Uses order_status_history with reason ESC_REASON_LOGIST as an audit trail.
    This survives resets of escalation timestamps performed when active offers exist.
    """
    try:
        row = await session.execute(
            text(
                "SELECT 1 FROM order_status_history"
                " WHERE order_id=:oid AND reason=:reason"
                " LIMIT 1"
            ).bindparams(oid=order_id, reason=ESC_REASON_LOGIST)
        )
        return row.first() is not None
    except Exception:
        return False


current_round = _current_round


async def _max_active_limit_for(session: AsyncSession) -> int:
    """Return the global default max active orders (fallback 5)."""
    value = await get_int("max_active_orders", DEFAULT_MAX_ACTIVE_LIMIT)
    # Safety guard: at least 1 active order allowed.
    return max(1, int(value))


# ===== Logging helpers =====


def fmt_rank_item(row: dict) -> str:
    """Format a ranked candidate item for logging."""
    shift_flag = 1 if row.get("shift") else 0
    car_flag = 1 if row.get("car") else 0
    avg_val = float(row.get("avg_week") or 0)
    rating_val = float(row.get("rating", 0) or 0)
    rnd_val = float(row.get("rnd", 0) or 0)
    return (
        f"{{mid={row['mid']} shift={shift_flag} car={car_flag} "
        f"avg_week={avg_val:.0f} rating={rating_val:.1f} "
        f"score=car({car_flag})>avg({avg_val:.0f})>rat({rating_val:.1f})>rnd({rnd_val:.2f})}}"
    )


def log_tick_header(order_row, round_num: int, rounds_total: int, sla: int, candidates_cnt: int) -> str:
    """Format header for distribution tick."""
    order_type = (
        "GUARANTEE"
        if str(getattr(order_row, "status", "")) == m.OrderStatus.GUARANTEE.value
        else "NORMAL"
    )
    district = getattr(order_row, "district_id", None)
    cat = (
        getattr(order_row, "category", None)
        or getattr(order_row, "category_code", None)
        or "-"
    )
    order_id = getattr(order_row, "id", None)
    city_id = getattr(order_row, "city_id", None)
    return (
        f"[dist] order={order_id} city={city_id} "
        f"district={district if district is not None else '-'} cat={cat} type={order_type}\n"
        f"round={round_num}/{rounds_total} sla={sla}s candidates={candidates_cnt}"
    )


def log_decision_offer(mid: int, until: datetime) -> str:
    """Log offer decision."""
    return f"decision=offer mid={mid} until={until.isoformat()}"


def log_force_first(mid: int) -> str:
    """Log forcing preferred master as first candidate."""
    return f"force_first=preferred_master mid={mid}"


def log_skip_no_district(order_id: int) -> str:
    """Log skipping order due to missing district."""
    return f"[dist] order={order_id} skip_auto: no_district  escalate=logist_now"


def log_skip_no_category(order_id: int, category = None) -> str:
    """Log skipping order due to missing/invalid category."""
    value = category if category not in (None, "") else "-"
    return (
        f"[dist] order={order_id} skip_auto: no_category_filter "
        f"category={value} -> escalate=logist_now"
    )


def log_escalate(order_id: int) -> str:
    """Log escalation due to no candidates."""
    return f"[dist] order={order_id} candidates=0  escalate=logist"


def log_escalate_admin(order_id: int) -> str:
    """Log escalation to admin."""
    return f"[dist] order={order_id} escalate=admin"


async def _transition_orders(
    session: AsyncSession,
    *,
    old_status: str,
    new_status: str,
    reason: str,
) -> int:
    result = await session.execute(
        text(
            """
            UPDATE orders
               SET status=:new_status,
                   updated_at=NOW(),
                   version=version+1
             WHERE status=:old_status
               AND assigned_master_id IS NULL
             RETURNING id
            """
        ),
        {"old_status": old_status, "new_status": new_status},
    )
    order_ids = [row[0] for row in result.fetchall()]
    if not order_ids:
        return 0
    await session.execute(
        insert(m.order_status_history),
        [
            {
                "order_id": oid,
                "from_status": old_status,
                "to_status": new_status,
                "reason": reason,
                "actor_type": m.ActorType.SYSTEM,
            }
            for oid in order_ids
        ],
    )
    return len(order_ids)


async def _workday_window() -> tuple[time, time]:
    try:
        return await settings_store.get_working_window()
    except Exception:
        return WORKDAY_START_DEFAULT, WORKDAY_END_DEFAULT


async def _city_timezone(session: AsyncSession, city_id: Optional[int]) -> ZoneInfo:
    if not city_id:
        return time_service.resolve_timezone(env_settings.timezone)
    if hasattr(m.cities, "timezone"):
        row = await session.execute(
            select(m.cities.timezone).where(m.cities.id == int(city_id))
        )
        value = row.scalar_one_or_none()
        if value:
            return time_service.resolve_timezone(str(value))
    return time_service.resolve_timezone(env_settings.timezone)



async def _check_preferred_master_availability(
    session: AsyncSession,
    *,
    master_id: int,
    order_id: int,
    district_id: Optional[int],
    skill_code: Optional[str],
    now: Optional[datetime] = None,
) -> dict:
    """Diagnostics for preferred master availability (used by tests)."""
    reasons: list[str] = []
    now = now or datetime.now(timezone.utc)

    mm = await session.get(m.masters, master_id)
    if mm is None:
        return {"available": False, "reasons": ["not_found"]}

    if getattr(mm, "is_blocked", False):
        reasons.append("blocked")
    bu = getattr(mm, "break_until", None)
    if bu and bu > now:
        reasons.append("on_break_until")
    if not getattr(mm, "is_on_shift", False):
        reasons.append("not_on_shift")

    if skill_code:
        has_skill = await session.scalar(
            select(m.func.count())
            .select_from(m.master_skills)
            .join(m.skills, m.skills.id == m.master_skills.skill_id)
            .where(
                (m.master_skills.master_id == master_id)
                & (m.skills.code == skill_code)
                & (m.skills.is_active.is_(True))
            )
        )
        if not has_skill:
            reasons.append("not_have_skill")

    if district_id is not None:
        in_district = await session.scalar(
            select(m.func.count())
            .select_from(m.master_districts)
            .where(
                (m.master_districts.master_id == master_id)
                & (m.master_districts.district_id == district_id)
            )
        )
        if not in_district:
            reasons.append("not_in_district")

    # Active orders limit
    try:
        base_limit = await get_int("max_active_orders", DEFAULT_MAX_ACTIVE_LIMIT)
    except Exception:
        base_limit = DEFAULT_MAX_ACTIVE_LIMIT
    max_limit = getattr(mm, "max_active_orders_override", None) or base_limit
    active_cnt = await session.scalar(
        select(m.func.count())
        .select_from(m.orders)
        .where(
            (m.orders.assigned_master_id == master_id)
            & (m.orders.status.in_([
                m.OrderStatus.ASSIGNED,
                m.OrderStatus.EN_ROUTE,
                m.OrderStatus.WORKING,
                m.OrderStatus.PAYMENT,
            ]))
        )
    ) or 0
    if active_cnt >= max_limit:
        reasons.append(f"at_limit_{active_cnt}/{max_limit}")

    return {
        "available": len(reasons) == 0,
        "reasons": reasons,
        "active_orders": int(active_cnt),
        "max_limit": int(max_limit),
    }


async def _wake_deferred_orders(
    session: AsyncSession,
    *,
    now_utc: datetime,
) -> list[tuple[int, datetime]]:
    rows = await session.execute(
        select(
            m.orders.id,
            m.orders.city_id,
            m.orders.timeslot_start_utc,
        ).where(
            m.orders.status == m.OrderStatus.DEFERRED
        )
    )
    records = rows.all()
    if not records:
        return []
    workday_start, _ = await _workday_window()
    awakened: list[tuple[int, datetime]] = []
    tz_cache: dict[int, ZoneInfo] = {}
    for order_id, city_id, start_utc in records:
        tz = tz_cache.get(city_id)
        if tz is None:
            tz = await _city_timezone(session, city_id)
            tz_cache[city_id] = tz
        local_now = now_utc.astimezone(tz)
        if start_utc is not None:
            target_local = start_utc.astimezone(tz)
        else:
            target_local = datetime.combine(local_now.date(), workday_start, tzinfo=tz)
        if target_local > local_now:
            if order_id not in DEFERRED_LOGGED:
                message = f"[dist] order={order_id} deferred until {target_local.isoformat()}"
                logger.info(message)
                _dist_log(message)
                DEFERRED_LOGGED.add(order_id)
            continue
        await session.execute(
            update(m.orders)
            .where(m.orders.id == order_id)
            .values(
                status=m.OrderStatus.SEARCHING,
                updated_at=now_utc,
                dist_escalated_logist_at=None,
                dist_escalated_admin_at=None,
            )
        )
        await session.execute(
            insert(m.order_status_history).values(
                order_id=order_id,
                from_status=m.OrderStatus.DEFERRED,
                to_status=m.OrderStatus.SEARCHING,
                reason='deferred_wakeup',
                actor_type=m.ActorType.SYSTEM,  #  FIX:   
                changed_by_staff_id=None,
                changed_by_master_id=None,
            )
        )
        DEFERRED_LOGGED.discard(order_id)
        awakened.append((order_id, target_local))
    return awakened


async def _candidates(
    session: AsyncSession,
    *,
    oid: int,
    city_id: int,
    district_id: Optional[int],
    skill_code: Optional[str],
    preferred_mid: Optional[int],
    fallback_limit: int,
) -> list[dict]:
    """
     STEP 2.2:    fallback    .
    
     district_id == None:
      -     ( )
      - LEFT JOIN master_districts  JOIN
    
     district_id :
      -      ( )
    """
    if not skill_code:
        return []
    
    #   district_id  -    
    if district_id is None:
        sql = text(
            """
        WITH lim AS (
          SELECT m.id AS master_id,
                 COALESCE(
                     m.max_active_orders_override,
                     (SELECT CAST(value AS INT) FROM settings WHERE key='max_active_orders' LIMIT 1),
                     :fallback
                 ) AS max_limit,
                 (SELECT COUNT(*) FROM orders o2
                   WHERE o2.assigned_master_id = m.id
                     AND o2.status IN ('ASSIGNED','EN_ROUTE','WORKING','PAYMENT')
                 ) AS active_cnt
          FROM masters m
        ), avg7 AS (
          SELECT o.assigned_master_id AS mid, AVG(o.total_sum)::numeric(10,2) AS avg_week_check
          FROM orders o
          WHERE o.status IN ('PAYMENT','CLOSED')
            AND o.created_at >= (NOW() - INTERVAL '7 days')
          GROUP BY o.assigned_master_id
        )
        SELECT m.id                  AS mid,
               m.has_vehicle         AS car,
               COALESCE(a.avg_week_check,0)::numeric(10,2) AS avg_week,
               COALESCE(m.rating,0)::numeric(3,1) AS rating,
               m.is_on_shift         AS shift
          FROM masters m
          --  LEFT JOIN .. district_id=NULL -    
          LEFT JOIN master_districts md ON md.master_id = m.id
          JOIN master_skills ms ON ms.master_id = m.id
          JOIN skills s ON s.id = ms.skill_id AND s.code = :skill_code AND s.is_active = TRUE
          JOIN lim ON lim.master_id = m.id
          LEFT JOIN avg7 a ON a.mid = m.id
         WHERE m.city_id = :cid
           AND m.is_active = TRUE
           AND m.is_blocked = FALSE
           AND m.verified = TRUE
           AND m.is_on_shift = TRUE
           AND (m.break_until IS NULL OR m.break_until <= NOW())
           AND lim.active_cnt < lim.max_limit
           AND NOT EXISTS (SELECT 1 FROM offers o WHERE o.order_id = :oid AND o.master_id = m.id)
         ORDER BY
           (CASE WHEN :pref > 0 AND m.id = :pref THEN 1 ELSE 0 END) DESC,
           m.has_vehicle DESC,
           COALESCE(a.avg_week_check,0) DESC,
           COALESCE(m.rating,0) DESC,
           m.id ASC
        """
        )
        rs = await session.execute(
            sql.bindparams(
                oid=oid,
                cid=city_id,
                pref=(preferred_mid or -1),
                skill_code=skill_code,
                fallback=fallback_limit,
            )
        )
    else:
        #  District  -    (  )
        sql = text(
            """
        WITH lim AS (
          SELECT m.id AS master_id,
                 COALESCE(
                     m.max_active_orders_override,
                     (SELECT CAST(value AS INT) FROM settings WHERE key='max_active_orders' LIMIT 1),
                     :fallback
                 ) AS max_limit,
                 (SELECT COUNT(*) FROM orders o2
                   WHERE o2.assigned_master_id = m.id
                     AND o2.status IN ('ASSIGNED','EN_ROUTE','WORKING','PAYMENT')
                 ) AS active_cnt
          FROM masters m
        ), avg7 AS (
          SELECT o.assigned_master_id AS mid, AVG(o.total_sum)::numeric(10,2) AS avg_week_check
          FROM orders o
          WHERE o.status IN ('PAYMENT','CLOSED')
            AND o.created_at >= (NOW() - INTERVAL '7 days')
          GROUP BY o.assigned_master_id
        )
        SELECT m.id                  AS mid,
               m.has_vehicle         AS car,
               COALESCE(a.avg_week_check,0)::numeric(10,2) AS avg_week,
               COALESCE(m.rating,0)::numeric(3,1) AS rating,
               m.is_on_shift         AS shift
          FROM masters m
          JOIN master_districts md ON md.master_id = m.id AND md.district_id = :did
          JOIN master_skills ms ON ms.master_id = m.id
          JOIN skills s ON s.id = ms.skill_id AND s.code = :skill_code AND s.is_active = TRUE
          JOIN lim ON lim.master_id = m.id
          LEFT JOIN avg7 a ON a.mid = m.id
         WHERE m.city_id = :cid
           AND m.is_active = TRUE
           AND m.is_blocked = FALSE
           AND m.verified = TRUE
           AND m.is_on_shift = TRUE
           AND (m.break_until IS NULL OR m.break_until <= NOW())
           AND lim.active_cnt < lim.max_limit
           AND NOT EXISTS (SELECT 1 FROM offers o WHERE o.order_id = :oid AND o.master_id = m.id)
         ORDER BY
           (CASE WHEN :pref > 0 AND m.id = :pref THEN 1 ELSE 0 END) DESC,
           m.has_vehicle DESC,
           COALESCE(a.avg_week_check,0) DESC,
           COALESCE(m.rating,0) DESC,
           m.id ASC
        """
        )
        rs = await session.execute(
            sql.bindparams(
                oid=oid,
                cid=city_id,
                did=district_id,
                pref=(preferred_mid or -1),
                skill_code=skill_code,
                fallback=fallback_limit,
            )
        )
    
    #  STEP 3.2:    Python  RANDOM()  SQL
    #     
    candidates = [
        dict(
            mid=row[0],
            car=bool(row[1]),
            avg_week=float(row[2]),
            rating=float(row[3]),
            shift=bool(row[4]),
            rnd=random.random(),  #     
        )
        for row in rs.fetchall()
    ]
    
    #   preferred  -     ORDER BY  SQL
    #        
    #    (car > avg_week > rating)   
    
    #  preferred  ( )
    if candidates and preferred_mid and candidates[0]["mid"] == preferred_mid:
        preferred = [candidates[0]]
        rest = candidates[1:]
    else:
        preferred = []
        rest = candidates
        #       preferred:
        #  preferred ,    ( fallback).
        if preferred_mid:
            return []
    
    #    (car, avg_week, rating)    
    from itertools import groupby
    from operator import itemgetter
    
    grouped = []
    for key, group in groupby(rest, key=itemgetter("car", "avg_week", "rating")):
        group_list = list(group)
        random.shuffle(group_list)  #      
        grouped.extend(group_list)
    
    return preferred + grouped



async def _send_offer(
    session: AsyncSession, *, oid: int, mid: int, round_number: int, sla_seconds: int
) -> bool:
    #         ( EXPIRED/DECLINED)
    existing = await session.execute(
        text("""
            SELECT 1 FROM offers 
            WHERE order_id = :oid 
              AND master_id = :mid 
              AND state NOT IN ('EXPIRED', 'DECLINED')
            LIMIT 1
        """).bindparams(oid=oid, mid=mid)
    )
    if existing.scalar_one_or_none():
        logger.info(f"[dist] order={oid} mid={mid} offer already exists, skipping")
        return False  #    
    
    #         ( EXPIRED, DECLINED)
    #      UNIQUE constraint
        
    #   
    ins = await session.execute(
        text(
            """
        INSERT INTO offers(order_id, master_id, round_number, state, sent_at, expires_at)
        VALUES (:oid, :mid, :r, 'SENT', clock_timestamp(), clock_timestamp() + make_interval(secs => :sla))
        RETURNING id
        """
        ).bindparams(oid=oid, mid=mid, r=round_number, sla=sla_seconds)
    )
    return bool(ins.scalar_one_or_none())



async def _log_ranked(
    order_id: int,
    city_id: int,
    district_id: Optional[int],
    cat: Optional[str],
    typ: str,
    rnd: int,
    rounds_total: int,
    sla: int,
    ranked: list[dict],
    preferred_mid: Optional[int],
    top_n: int,
) -> None:
    parts = [
        f"[dist] order={order_id} city={city_id} district={district_id if district_id is not None else 'null'} "
        f"cat={cat or '-'} type={typ}",
    ]
    if preferred_mid:
        parts.append(f"force_first=preferred_master mid={preferred_mid}")
    parts.append(f"round={rnd}/{rounds_total} sla={sla}s candidates={len(ranked)}")
    top_lines: list[str] = []
    for candidate in ranked[:top_n]:
        shift_flag = "on" if candidate.get("shift", True) else "off"
        top_lines.append(
            "  {"
            f"mid={candidate['mid']} "
            f"shift={shift_flag} "
            f"car={1 if candidate['car'] else 0} "
            f"avg_week={candidate['avg_week']:.0f} "
            f"rating={candidate['rating']:.1f} "
            f"score=car({1 if candidate['car'] else 0})"
            f">avg({candidate['avg_week']:.0f})"
            f">rat({candidate['rating']:.1f})"
            f">rnd({candidate.get('rnd', 0.0):.2f})"
            "}"
        )
    if top_lines:
        parts.append("ranked=[\n" + "\n".join(top_lines) + "\n]")
    logger.info("\n".join(parts))

    district_label = district_id if district_id is not None else "null"
    summary = (
        f"[dist] order={order_id} type={typ} round={rnd}/{rounds_total} "
        f"city={city_id} district={district_label} candidates={len(ranked)}"
    )
    if ranked:
        summary += f" top_mid={ranked[0]['mid']}"
    if preferred_mid:
        summary += f" preferred={preferred_mid}"
    _dist_log(summary)


async def _set_logist_escalation(
    session: AsyncSession,
    order: OrderForDistribution,
) -> datetime | None:
    # Set logist escalation timestamp if not already set, and reset admin
    # escalation to keep a single active escalation path. Avoid ORM lazy loads
    # to work reliably under AsyncSession.
    row = await session.execute(
        text(
            """
        UPDATE orders
           SET dist_escalated_logist_at = COALESCE(dist_escalated_logist_at, NOW()),
               dist_escalated_admin_at = NULL
         WHERE id = :oid
        RETURNING dist_escalated_logist_at, dist_escalated_admin_at
        """
        ).bindparams(oid=order.id)
    )
    rec = row.first()
    if not rec:
        return None
    value = rec[0]
    logger.info("[dist] order=%s logist_escalated_at=%s", order.id, getattr(value, 'isoformat', lambda: value)())
    # Persist audit trail that logist escalation happened at least once
    try:
        await session.execute(
            insert(m.order_status_history).values(
                order_id=order.id,
                from_status=order.status,
                to_status=order.status,
                reason=ESC_REASON_LOGIST,
                actor_type=m.ActorType.SYSTEM,
            )
        )
    except Exception:
        # Best-effort: do not fail tick on history insert problems
        pass
    order.escalated_logist_at = value
    order.escalated_admin_at = None
    try:
        obj = await session.get(m.orders, order.id)
        if obj is not None:
            obj.dist_escalated_logist_at = value
            obj.dist_escalated_admin_at = None
    except Exception:
        pass
    return value


async def _set_admin_escalation(
    session: AsyncSession,
    order: OrderForDistribution,
) -> datetime | None:
    row = await session.execute(
        text(
            """
        UPDATE orders
           SET dist_escalated_admin_at = NOW()
         WHERE id = :oid
           AND dist_escalated_admin_at IS NULL
        RETURNING dist_escalated_admin_at
        """
        ).bindparams(oid=order.id)
    )
    value = row.scalar()
    if value is not None:
        order.escalated_admin_at = value
        obj = await session.get(m.orders, order.id)
        if obj is not None:
            obj.dist_escalated_admin_at = value
    return value


async def _mark_logist_notification_sent(session: AsyncSession, order_id: int) -> datetime:
    """
     timestamp   .
      timestamp.
    """
    row = await session.execute(
        text("""
        UPDATE orders 
           SET escalation_logist_notified_at = NOW()
         WHERE id = :oid
        RETURNING escalation_logist_notified_at
        """).bindparams(oid=order_id)
    )
    return row.scalar()


async def _mark_admin_notification_sent(session: AsyncSession, order_id: int) -> datetime:
    """
     timestamp   .
      timestamp.
    """
    row = await session.execute(
        text("""
        UPDATE orders 
           SET escalation_admin_notified_at = NOW()
         WHERE id = :oid
        RETURNING escalation_admin_notified_at
        """).bindparams(oid=order_id)
    )
    return row.scalar()


async def _reset_escalations(
    session: AsyncSession,
    order: OrderForDistribution,
) -> None:
    """
         .
    
     STEP 1.4:    :
    - dist_escalated_logist_at
    - dist_escalated_admin_at
    - escalation_logist_notified_at (timestamp  )
    - escalation_admin_notified_at (timestamp  )
    """
    if order.escalated_logist_at is None and order.escalated_admin_at is None:
        return
    # Record that escalation existed before being reset due to active offer
    try:
        await session.execute(
            insert(m.order_status_history).values(
                order_id=order.id,
                from_status=order.status,
                to_status=order.status,
                reason=ESC_REASON_LOGIST,
                actor_type=m.ActorType.SYSTEM,
            )
        )
    except Exception:
        pass
    await session.execute(
        text(
            """
        UPDATE orders
           SET dist_escalated_logist_at = NULL,
               dist_escalated_admin_at = NULL,
               escalation_logist_notified_at = NULL,
               escalation_admin_notified_at = NULL
         WHERE id = :oid
        """
        ).bindparams(oid=order.id)
    )
    order.escalated_logist_at = None
    order.escalated_admin_at = None
    order.escalation_logist_notified_at = None
    order.escalation_admin_notified_at = None


async def _escalate_logist(order_id: int):
    message = f"[dist] order={order_id} escalate=logist"
    logger.warning(message)
    _dist_log(message, level="WARN")


async def tick_once(
    cfg: DistConfig, 
    *, 
    bot: Bot | None = None, 
    alerts_chat_id: Optional[int] = None,
    session: AsyncSession | None = None
) -> None:
    """
       .
    
    Args:
        cfg:  
        bot: Telegram bot   ()
        alerts_chat_id: ID    ()
        session:     ( )
                  None -   
    """
    #    () -  
    #   () -  
    if session is not None:
        #       bind, 
        #   identity map   .
        await _tick_once_impl(session, cfg, bot, alerts_chat_id)
    else:
        async with SessionLocal() as session:
            await _tick_once_impl(session, cfg, bot, alerts_chat_id)


async def _tick_once_impl(
    session: AsyncSession,
    cfg: DistConfig,
    bot: Bot | None,
    alerts_chat_id: Optional[int]
) -> None:
    """  tick_once    ."""
    #  STEP 4.2: Structured logging - tick start
    log_distribution_event(
        DistributionEvent.TICK_START,
        details={
            "tick_seconds": cfg.tick_seconds,
            "sla_seconds": cfg.sla_seconds,
            "rounds": cfg.rounds,
        }
    )
    
    if not await _try_advisory_lock(session):
        return

    now = await _db_now(session)
    try:
        # Proactively expire overdue offers by SLA
        await expire_sent_offers(session, now)
    except Exception:
        pass
    awakened = await _wake_deferred_orders(session, now_utc=now)
    for order_id, target_local in awakened:
        message = f"[dist] deferred->searching order={order_id} at {target_local.isoformat()}"
        logger.info(message)
        _dist_log(message)
        
        #  STEP 4.2: Structured logging - deferred wake
        log_distribution_event(
            DistributionEvent.DEFERRED_WAKE,
            order_id=order_id,
            details={"target_time": target_local.isoformat()},
        )


    orders = await _fetch_orders_for_distribution(session)

    #  STEP 4.2: Structured logging - orders fetched
    log_distribution_event(
        DistributionEvent.ORDER_FETCHED,
        details={"orders_count": len(orders)},
    )

    # Debug: log any active SENT offers timing for fetched orders
    try:
        for ord_obj in orders:
            rows = await session.execute(
                text(
                    "SELECT state, sent_at, expires_at, NOW() AS now_ts, clock_timestamp() AS clk_ts "
                    "FROM offers WHERE order_id=:oid AND state='SENT'"
                ).bindparams(oid=ord_obj.id)
            )
            for r in rows:
                logger.warning(
                    "[dist] debug order=%s offer_state=%s sent_at=%s expires_at=%s now=%s clock=%s",
                    ord_obj.id, r[0], getattr(r[1], 'isoformat', lambda: r[1])(), getattr(r[2], 'isoformat', lambda: r[2])(), getattr(r[3], 'isoformat', lambda: r[3])(), getattr(r[4], 'isoformat', lambda: r[4])(),
                )
    except Exception:
        pass

    city_contexts = await _fetch_city_contexts(
        session,
        {order.city_id for order in orders},
    )

    for order in orders:
        city_ctx = city_contexts.get(order.city_id)
        #  STEP 1.4:    -      
        if (
            order.escalated_logist_at is not None
            and order.escalated_admin_at is None
            and now - order.escalated_logist_at >= timedelta(minutes=cfg.to_admin_after_min)
        ):
            admin_marked = await _set_admin_escalation(session, order)
            if admin_marked and order.escalation_admin_notified_at is None:
                admin_message = f"[dist] order={order.id} escalate=admin"
                logger.warning(admin_message)
                _dist_log(admin_message, level="WARN")

                #  STEP 4.2: Structured logging - escalation to admin
                log_distribution_event(
                    DistributionEvent.ESCALATION_ADMIN,
                    order_id=order.id,
                    city_id=order.city_id,
                    district_id=order.district_id,
                    escalated_to="admin",
                    notification_type="escalation_admin_notified",
                    level="WARNING",
                )

                await _notify_admin_escalation(
                    session,
                    order,
                    bot=bot,
                    alerts_chat_id=alerts_chat_id,
                    city_ctx=city_ctx,
                    message=admin_message,
                    reason=" SLA  ",
                )

        #  STEP 2.2:       
        #       
        #       
        #     no_district   ,    .
        if order.no_district:
            district_label = "null" if order.district_id is None else f"{order.district_id}(no_district)"
            message = log_skip_no_district(order.id)
            logger.info(message)
            _dist_log(message)
            newly_marked = False
            if order.escalated_logist_at is None:
                marked = await _set_logist_escalation(session, order)
                newly_marked = marked is not None
            await _escalate_logist(order.id)
            if newly_marked and order.escalation_logist_notified_at is None:
                await _notify_logist_escalation(
                    session,
                    order,
                    bot=bot,
                    alerts_chat_id=alerts_chat_id,
                    city_ctx=city_ctx,
                    message=message,
                    reason="no_district",
                )
            await session.commit()
            obj = await session.get(m.orders, order.id)
            if obj is not None:
                session.expire(obj)
            continue
        #   ,   no_district     ,    
        if order.district_id is None:
            district_label = "null"
            message = (
                f"[dist] order={order.id} city={order.city_id} district={district_label} "
                f"will_search_citywide: fallback to city search"
            )
            logger.info(message)
            _dist_log(message)

        timed_out_mid = await _expire_overdue_offer(session, order.id, cfg.sla_seconds)
        if timed_out_mid:
            message = f"[dist] order={order.id} timeout mid={timed_out_mid}"
            logger.info(message)
            _dist_log(message)
            
            #  STEP 4.2: Structured logging - offer expired
            log_distribution_event(
                DistributionEvent.OFFER_EXPIRED,
                order_id=order.id,
                master_id=timed_out_mid,
                reason="sla_timeout",
            )

        row = await session.execute(
            text(
                "SELECT 1 FROM offers WHERE order_id=:oid AND state='SENT' AND (expires_at IS NULL OR expires_at > clock_timestamp()) LIMIT 1"
            ).bindparams(oid=order.id)
        )
        if row.first():
            await _reset_escalations(session, order)
            await session.commit()
            obj = await session.get(m.orders, order.id)
            if obj is not None:
                session.expire(obj)
            continue

        current_round = await _current_round(session, order.id)

        # If there were previous offers and now no active SENT remains,
        # escalate to logist before attempting a new round IFF the order had
        # been escalated before (even if timestamps were reset due to a SENT
        # offer). This preserves e2e expectations and keeps faster retry case.
        previously_escalated = (
            order.escalated_logist_at is not None
            or await _was_logist_escalated_before(session, order.id)
        )
        if current_round > 0 and previously_escalated:
            message = f"[dist] order={order.id} prev_offers_expired -> escalate=logist"
            logger.info(message)
            _dist_log(message)
            newly_marked = False
            if order.escalated_logist_at is None:
                marked = await _set_logist_escalation(session, order)
                newly_marked = marked is not None
            await _escalate_logist(order.id)
            if newly_marked and order.escalation_logist_notified_at is None:
                log_distribution_event(
                    DistributionEvent.ESCALATION_LOGIST,
                    order_id=order.id,
                    city_id=order.city_id,
                    district_id=order.district_id,
                    round_number=current_round,
                    escalated_to="logist",
                    reason="prev_offers_expired",
                    notification_type="escalation_logist_notified",
                    level="WARNING",
                )
                await _notify_logist_escalation(
                    session,
                    order,
                    bot=bot,
                    alerts_chat_id=alerts_chat_id,
                    city_ctx=city_ctx,
                    message=message,
                    reason="prev_offers_expired",
                )
            await session.commit()
            obj = await session.get(m.orders, order.id)
            if obj is not None:
                session.expire(obj)
            continue

        #  STEP 1.4:      
        if current_round >= cfg.rounds:
            message = f"[dist] order={order.id} round={current_round} rounds_exhausted -> escalate=logist"
            logger.info(message)
            _dist_log(message)
            newly_marked = False
            if order.escalated_logist_at is None:
                marked = await _set_logist_escalation(session, order)
                newly_marked = marked is not None
            await _escalate_logist(order.id)
            #              
            if newly_marked and order.escalation_logist_notified_at is None:
                #  STEP 4.2: Structured logging - escalation to logist (rounds exhausted)
                log_distribution_event(
                    DistributionEvent.ESCALATION_LOGIST,
                    order_id=order.id,
                    city_id=order.city_id,
                    district_id=order.district_id,
                    round_number=current_round,
                    escalated_to="logist",
                    reason="rounds_exhausted",
                    notification_type="escalation_logist_notified",
                    level="WARNING",
                )

                await _notify_logist_escalation(
                    session,
                    order,
                    bot=bot,
                    alerts_chat_id=alerts_chat_id,
                    city_ctx=city_ctx,
                    message=message,
                    reason=f"  (#{current_round})",
                )
            await session.commit()
            obj = await session.get(m.orders, order.id)
            if obj is not None:
                session.expire(obj)
            continue

        #  STEP 1.4:      
        skill_code = get_skill_code(order.category)
        if not skill_code:
            category_label = order.category if order.category else "-"
            message = (
                f"[dist] order={order.id} skip_auto: no_category_filter category={category_label} -> escalate=logist_now"
            )
            logger.info(message)
            _dist_log(message)
            newly_marked = False
            if order.escalated_logist_at is None:
                marked = await _set_logist_escalation(session, order)
                newly_marked = marked is not None
            await _escalate_logist(order.id)
            #              
            if newly_marked and order.escalation_logist_notified_at is None:
                #  STEP 4.2: Structured logging - escalation to logist (no category)
                log_distribution_event(
                    DistributionEvent.ESCALATION_LOGIST,
                    order_id=order.id,
                    city_id=order.city_id,
                    district_id=order.district_id,
                    escalated_to="logist",
                    reason="no_category",
                    category=category_label,
                    notification_type="escalation_logist_notified",
                    level="WARNING",
                )

                await _notify_logist_escalation(
                    session,
                    order,
                    bot=bot,
                    alerts_chat_id=alerts_chat_id,
                    city_ctx=city_ctx,
                    message=message,
                    reason="  ",
                )
            await session.commit()
            continue

        status_value = str(order.status) if order.status is not None else ""

        order_type_value = str(order.order_type) if order.order_type is not None else ""

        order_kind = "GUARANTEE" if order_type_value.upper() == "GUARANTEE" or status_value.upper() == "GUARANTEE" else "NORMAL"
        preferred_id = order.preferred_master_id if order_kind == "GUARANTEE" else None

        #  STEP 4.2: Structured logging - round start
        next_round = current_round + 1
        log_distribution_event(
            DistributionEvent.ROUND_START,
            order_id=order.id,
            city_id=order.city_id,
            district_id=order.district_id,
            round_number=next_round,
            total_rounds=cfg.rounds,
            category=order.category,
            order_type=order_kind,
            preferred_master_id=preferred_id,
        )

        ranked = await _candidates(
            session,
            oid=order.id,
            city_id=order.city_id,
            district_id=order.district_id,
            skill_code=skill_code,
            preferred_mid=preferred_id,
            fallback_limit=DEFAULT_MAX_ACTIVE_LIMIT,
        )
        # Fallback: if district-specific search returns no candidates, try citywide
        if not ranked and order.district_id is not None:
            ranked = await _candidates(
                session,
                oid=order.id,
                city_id=order.city_id,
                district_id=None,
                skill_code=skill_code,
                preferred_mid=preferred_id,
                fallback_limit=DEFAULT_MAX_ACTIVE_LIMIT,
            )
        
        await _log_ranked(
            order.id,
            order.city_id,
            order.district_id,
            order.category,
            order_kind,
            next_round,
            cfg.rounds,
            cfg.sla_seconds,
            ranked,
            preferred_id,
            cfg.top_log_n,
        )

        #  STEP 2.2:      
        #           
        if not ranked:
            search_scope = "citywide" if order.district_id is None else f"district={order.district_id}"
            message = f"[dist] order={order.id} round={next_round} no_candidates search_scope={search_scope} -> escalate=logist"
            logger.info(message)
            _dist_log(message)
            
            #  STEP 4.2: Structured logging - no candidates found
            log_distribution_event(
                DistributionEvent.NO_CANDIDATES,
                order_id=order.id,
                city_id=order.city_id,
                district_id=order.district_id,
                round_number=next_round,
                candidates_count=0,
                search_scope=search_scope,
                reason="escalate_to_logist",
                level="WARNING",
            )
            
            newly_marked = False
            if order.escalated_logist_at is None:
                marked = await _set_logist_escalation(session, order)
                newly_marked = marked is not None
            await _escalate_logist(order.id)
            #              
            if newly_marked and order.escalation_logist_notified_at is None:
                #  STEP 4.2: Structured logging - escalation to logist (no candidates)
                log_distribution_event(
                    DistributionEvent.ESCALATION_LOGIST,
                    order_id=order.id,
                    city_id=order.city_id,
                    district_id=order.district_id,
                    round_number=next_round,
                    escalated_to="logist",
                    reason="no_candidates",
                    search_scope=search_scope,
                    notification_type="escalation_logist_notified",
                    level="WARNING",
                )

                reason = (
                    "  "
                    if search_scope == "citywide"
                    else f"   ({search_scope})"
                )
                await _notify_logist_escalation(
                    session,
                    order,
                    bot=bot,
                    alerts_chat_id=alerts_chat_id,
                    city_ctx=city_ctx,
                    message=message,
                    reason=reason,
                )
            await session.commit()
            continue

        #  STEP 4.2: Structured logging - candidates found
        log_distribution_event(
            DistributionEvent.CANDIDATES_FOUND,
            order_id=order.id,
            city_id=order.city_id,
            district_id=order.district_id,
            round_number=next_round,
            candidates_count=len(ranked),
            master_id=ranked[0]["mid"],
            details={
                "top_master": {
                    "mid": ranked[0]["mid"],
                    "car": ranked[0]["car"],
                    "avg_week": ranked[0]["avg_week"],
                    "rating": ranked[0]["rating"],
                },
            },
        )

        first_mid = ranked[0]["mid"]
        await _reset_escalations(session, order)
        ok = await _send_offer(
            session,
            oid=order.id,
            mid=first_mid,
            round_number=next_round,
            sla_seconds=cfg.sla_seconds,
        )

        if ok:
            until_row = await session.execute(
                text("SELECT NOW() + make_interval(secs => :sla)").bindparams(
                    sla=cfg.sla_seconds
                )
            )
            until = until_row.scalar()
            message = f"[dist] order={order.id} decision=offer mid={first_mid} until={until.isoformat()}"
            logger.info(message)
            _dist_log(message)
            
            #  STEP 4.2: Structured logging - offer sent
            log_distribution_event(
                DistributionEvent.OFFER_SENT,
                order_id=order.id,
                master_id=first_mid,
                round_number=next_round,
                sla_seconds=cfg.sla_seconds,
                expires_at=until,
            )
            
            #  P1-10:  push-    
            try:
                order_data = await _get_order_notification_data(
                    session,
                    order.id,
                    timezone=city_ctx.timezone if city_ctx else None,
                )
                if order_data:
                    await notify_master(
                        session,
                        master_id=first_mid,
                        event=NotificationEvent.NEW_OFFER,
                        **order_data,
                    )
                    logger.info(f"[dist] Push notification queued for master#{first_mid} about order#{order.id}")
            except Exception as e:
                logger.error(f"[dist] Failed to queue notification for master#{first_mid}: {e}")


        # Commit changes for this tick. Avoid expiring the whole identity map here:
        # test code may access freshly loaded ORM objects (e.g., offers) right after
        # tick_once() returns, and a blanket expire_all() would trigger implicit
        # IO on attribute access under AsyncSession, causing MissingGreenlet.
        await session.commit()


async def run_scheduler(bot: Bot | None = None, *, alerts_chat_id: Optional[int] = None) -> None:
    # CR-2025-10-03-009:  INFO/WARNING  ,   ERROR
    logging.basicConfig(level=logging.WARNING)  #   WARNING
    dist_logger = logging.getLogger("distribution")
    dist_logger.setLevel(logging.ERROR)  #  distribution  ERROR  

    sleep_for = 15  #  STEP 2.3: 30 -> 15 
    while True:
        try:
            cfg = await _load_config(session=None)  #     
            sleep_for = max(1, cfg.tick_seconds)
            await tick_once(cfg, bot=bot, alerts_chat_id=alerts_chat_id)
        except Exception as exc:
            logger.exception("[dist] exception: %s", exc)
            _dist_log(f"[dist] exception: {exc}", level="ERROR")
        await asyncio.sleep(sleep_for)









