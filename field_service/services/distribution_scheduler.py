from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from aiogram import Bot
from sqlalchemy import insert, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from field_service.config import settings as env_settings
from field_service.db import models as m
from field_service.db.session import SessionLocal
from field_service.services import live_log, time_service, settings_service as settings_store
from field_service.infra.notify import send_alert, send_report
from field_service.services.settings_service import (
    get_int,
)

CATEGORY_TO_SKILL_CODE = {
    "ELECTRICS": "ELEC",
    "PLUMBING": "PLUMB",
    "APPLIANCES": "APPLI",
    "WINDOWS": "WINDOWS",
    "HANDYMAN": "HANDY",
    "ROADSIDE": "AUTOHELP",
}


def _skill_code_for_category(category: Optional[str]) -> Optional[str]:
    if not category:
        return None
    return CATEGORY_TO_SKILL_CODE.get(str(category).upper())


DEFAULT_MAX_ACTIVE_LIMIT = 5


logger = logging.getLogger("distribution")

ADVISORY_LOCK_KEY = 982734
DEFERRED_LOGGED: set[int] = set()
WORKDAY_START_DEFAULT = time_service.parse_time_string(env_settings.workday_start, default=time(10, 0))
WORKDAY_END_DEFAULT = time_service.parse_time_string(env_settings.workday_end, default=time(20, 0))

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
    tick_seconds: int
    sla_seconds: int
    rounds: int
    top_log_n: int
    to_admin_after_min: int



@dataclass
class OrderForDistribution:
    id: int
    city_id: int
    city_name: str
    district_id: Optional[int]
    preferred_master_id: Optional[int]
    status: str
    category: Optional[str]
    order_type: Optional[str]
    no_district: bool
    escalated_logist_at: Optional[datetime]
    escalated_admin_at: Optional[datetime]


async def _load_config() -> DistConfig:
    async with SessionLocal() as s:
        return DistConfig(
            tick_seconds=await get_int("distribution_tick_seconds", 30),
            sla_seconds=await get_int("distribution_sla_seconds", 120),
            rounds=await get_int("distribution_rounds", 2),
            top_log_n=await get_int("distribution_log_topn", 10),
            to_admin_after_min=await get_int("escalate_to_admin_after_min", 10),
        )


async def _try_advisory_lock(session: AsyncSession) -> bool:
    row = await session.execute(
        text("SELECT pg_try_advisory_lock(:k)").bindparams(k=ADVISORY_LOCK_KEY)
    )
    return bool(row.scalar())


async def _db_now(session: AsyncSession):
    row = await session.execute(text("SELECT NOW()"))
    return row.scalar()



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
               o.preferred_master_id,
               o.status,
               o.category,
               o.type AS order_type,
               o.no_district,
               o.dist_escalated_logist_at,
               o.dist_escalated_admin_at
          FROM orders o
          JOIN cities c ON c.id = o.city_id
         WHERE o.status IN ('SEARCHING','GUARANTEE')
           AND o.assigned_master_id IS NULL
         ORDER BY o.created_at
         LIMIT 100
         FOR UPDATE SKIP LOCKED
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
            )
        )
    return orders



async def _expire_overdue_offer(session: AsyncSession, order_id: int) -> Optional[int]:
    """  SENT     EXPIRED,  master_id   timeout;  None."""
    row = await session.execute(
        text(
            """
        UPDATE offers
           SET state='EXPIRED', responded_at=NOW()
         WHERE id = (
             SELECT id FROM offers
              WHERE order_id=:oid AND state='SENT'
              ORDER BY sent_at DESC
              LIMIT 1
         ) AND expires_at <= NOW() AND state='SENT'
        RETURNING master_id
        """
        ).bindparams(oid=order_id)
    )
    t = row.first()
    return int(t[0]) if t else None


async def _current_round(session: AsyncSession, order_id: int) -> int:
    row = await session.execute(
        text(
            "SELECT COALESCE(MAX(round_number),0) FROM offers WHERE order_id=:oid"
        ).bindparams(oid=order_id)
    )
    r = int(row.scalar() or 0)
    return r


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
    district_id: int,
    skill_code: Optional[str],
    preferred_mid: Optional[int],
    fallback_limit: int,
) -> list[dict]:
    if not skill_code:
        return []
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
           m.is_on_shift         AS shift,
           RANDOM()              AS rnd
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
       AND NOT EXISTS (
            SELECT 1 FROM offers o
             WHERE o.order_id = :oid AND o.master_id = m.id
       )
     ORDER BY
       (CASE WHEN :pref > 0 AND m.id = :pref THEN 1 ELSE 0 END) DESC,
       m.has_vehicle DESC,
       COALESCE(a.avg_week_check,0) DESC,
       COALESCE(m.rating,0) DESC,
       rnd ASC
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
    return [
        dict(
            mid=row[0],
            car=bool(row[1]),
            avg_week=float(row[2]),
            rating=float(row[3]),
            shift=bool(row[4]),
            rnd=float(row[5]),
        )
        for row in rs.fetchall()
    ]



async def _send_offer(
    session: AsyncSession, *, oid: int, mid: int, round_number: int, sla_seconds: int
) -> bool:
    ins = await session.execute(
        text(
            """
        INSERT INTO offers(order_id, master_id, round_number, state, sent_at, expires_at)
        VALUES (:oid, :mid, :r, 'SENT', NOW(), NOW() + make_interval(secs => :sla))
        ON CONFLICT ON CONSTRAINT uq_offers__order_master DO NOTHING
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
    row = await session.execute(
        text(
            """
        UPDATE orders
           SET dist_escalated_logist_at = NOW(),
               dist_escalated_admin_at = NULL
         WHERE id = :oid
           AND dist_escalated_logist_at IS NULL
        RETURNING dist_escalated_logist_at
        """
        ).bindparams(oid=order.id)
    )
    value = row.scalar()
    if value is not None:
        order.escalated_logist_at = value
        order.escalated_admin_at = None
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
    return value


async def _reset_escalations(
    session: AsyncSession,
    order: OrderForDistribution,
) -> None:
    """
    Сбрасывает эскалации при появлении нового оффера.
    
    ✅ STEP 1.4: Сбрасываем ВСЕ поля эскалации:
    - dist_escalated_logist_at
    - dist_escalated_admin_at
    - escalation_logist_notified_at (timestamp уведомления логисту)
    - escalation_admin_notified_at (timestamp уведомления админу)
    """
    if order.escalated_logist_at is None and order.escalated_admin_at is None:
        return
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
    bot: Bot | None, 
    alerts_chat_id: Optional[int],
    session: AsyncSession | None = None
) -> None:
    """
    Один тик распределителя заказов.
    
    Args:
        cfg: Конфигурация распределения
        bot: Telegram bot для уведомлений (опционально)
        alerts_chat_id: ID чата для алертов (опционально)
        session: Опциональная существующая сессия БД (для тестов)
                 Если None - создаётся новая сессия
    """
    # Если сессия передана (тесты) - используем её
    # Если нет (продакшен) - создаём новую
    if session is not None:
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
    """Внутренняя реализация tick_once с уже созданной сессией."""
    if not await _try_advisory_lock(session):
        return

    now = await _db_now(session)
    awakened = await _wake_deferred_orders(session, now_utc=now)
    for order_id, target_local in awakened:
        message = f"[dist] deferred->searching order={order_id} at {target_local.isoformat()}"
        logger.info(message)
        _dist_log(message)


    orders = await _fetch_orders_for_distribution(session)

    for order in orders:
        # ✅ STEP 1.4: Эскалация к админу - проверяем что уведомление ещё не отправлено
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
                
                # ✅ КРИТИЧНО: Отмечаем уведомление ПЕРЕД отправкой (независимо от бота)
                notified_at = await _mark_admin_notification_sent(session, order.id)
                order.escalation_admin_notified_at = notified_at
                logger.info("[dist] order=%s admin_notification_sent_at=%s", order.id, notified_at.isoformat())
                
                await _report(bot, admin_message)
                if bot and alerts_chat_id:
                    await push_notify_admin(
                        bot,
                        alerts_chat_id,
                        event=NotificationEvent.ESCALATION_ADMIN,
                        order_id=order.id,
                    )

        # ✅ STEP 1.4: Эскалация к логисту при no_district - проверяем что уведомление ещё не отправлено
        if order.district_id is None or order.no_district:
            message = (
                f"[dist] order={order.id} city={order.city_id} district=null skip_auto: no_district -> escalate=logist_now"
            )
            logger.info(message)
            _dist_log(message)
            newly_marked = False
            if order.escalated_logist_at is None:
                marked = await _set_logist_escalation(session, order)
                newly_marked = marked is not None
            await _escalate_logist(order.id)
            if newly_marked:
                await _report(bot, message)
                await send_alert(
                    bot,
                    f"      {order.city_name}   #{order.id}.   .",
                    chat_id=alerts_chat_id,
                )
            continue

        timed_out_mid = await _expire_overdue_offer(session, order.id)
        if timed_out_mid:
            message = f"[dist] order={order.id} timeout mid={timed_out_mid}"
            logger.info(message)
            _dist_log(message)

        row = await session.execute(
            text(
                "SELECT 1 FROM offers WHERE order_id=:oid AND state='SENT' LIMIT 1"
            ).bindparams(oid=order.id)
        )
        if row.first():
            await _reset_escalations(session, order)
            continue

        current_round = await _current_round(session, order.id)

        # ✅ STEP 1.4: Эскалация к логисту при исчерпании раундов
        if current_round >= cfg.rounds:
            message = f"[dist] order={order.id} round={current_round} rounds_exhausted -> escalate=logist"
            logger.info(message)
            _dist_log(message)
            newly_marked = False
            if order.escalated_logist_at is None:
                marked = await _set_logist_escalation(session, order)
                newly_marked = marked is not None
            await _escalate_logist(order.id)
            # ✅ Отправляем уведомление только если эскалация только что произошла И уведомление ещё не отправлялось
            if newly_marked and order.escalation_logist_notified_at is None:
                # ✅ КРИТИЧНО: Отмечаем уведомление ПЕРЕД отправкой (независимо от бота)
                notified_at = await _mark_logist_notification_sent(session, order.id)
                order.escalation_logist_notified_at = notified_at
                logger.info("[dist] order=%s logist_notification_sent_at=%s", order.id, notified_at.isoformat())
                
                await _report(bot, message)
                if bot and alerts_chat_id:
                    await push_notify_admin(
                        bot,
                        alerts_chat_id,
                        event=NotificationEvent.ESCALATION_LOGIST,
                        order_id=order.id,
                    )
            continue

        # ✅ STEP 1.4: Эскалация к логисту при отсутствии категории
        skill_code = _skill_code_for_category(order.category)
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
            # ✅ Отправляем уведомление только если эскалация только что произошла И уведомление ещё не отправлялось
            if newly_marked and order.escalation_logist_notified_at is None:
                # ✅ КРИТИЧНО: Отмечаем уведомление ПЕРЕД отправкой (независимо от бота)
                notified_at = await _mark_logist_notification_sent(session, order.id)
                order.escalation_logist_notified_at = notified_at
                logger.info("[dist] order=%s logist_notification_sent_at=%s", order.id, notified_at.isoformat())
                
                await _report(bot, message)
                if bot and alerts_chat_id:
                    await push_notify_admin(
                        bot,
                        alerts_chat_id,
                        event=NotificationEvent.ESCALATION_LOGIST,
                        order_id=order.id,
                    )
            continue

        status_value = str(order.status) if order.status is not None else ""

        order_type_value = str(order.order_type) if order.order_type is not None else ""

        order_kind = "GUARANTEE" if order_type_value.upper() == "GUARANTEE" or status_value.upper() == "GUARANTEE" else "NORMAL"
        preferred_id = order.preferred_master_id if order_kind == "GUARANTEE" else None

        ranked = await _candidates(
            session,
            oid=order.id,
            city_id=order.city_id,
            district_id=order.district_id,
            skill_code=skill_code,
            preferred_mid=preferred_id,
            fallback_limit=DEFAULT_MAX_ACTIVE_LIMIT,
        )
        next_round = current_round + 1
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

        # ✅ STEP 1.4: Эскалация к логисту при отсутствии кандидатов
        if not ranked:
            message = f"[dist] order={order.id} round={next_round} no_candidates -> escalate=logist"
            logger.info(message)
            _dist_log(message)
            newly_marked = False
            if order.escalated_logist_at is None:
                marked = await _set_logist_escalation(session, order)
                newly_marked = marked is not None
            await _escalate_logist(order.id)
            # ✅ Отправляем уведомление только если эскалация только что произошла И уведомление ещё не отправлялось
            if newly_marked and order.escalation_logist_notified_at is None:
                # ✅ КРИТИЧНО: Отмечаем уведомление ПЕРЕД отправкой (независимо от бота)
                notified_at = await _mark_logist_notification_sent(session, order.id)
                order.escalation_logist_notified_at = notified_at
                logger.info("[dist] order=%s logist_notification_sent_at=%s", order.id, notified_at.isoformat())
                
                await _report(bot, message)
                if bot and alerts_chat_id:
                    await push_notify_admin(
                        bot,
                        alerts_chat_id,
                        event=NotificationEvent.ESCALATION_LOGIST,
                        order_id=order.id,
                    )
            continue

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


        await session.commit()


async def run_scheduler(bot: Bot | None = None, *, alerts_chat_id: Optional[int] = None) -> None:
    # CR-2025-10-03-009: Отключаем INFO/WARNING в консоли, оставляем только ERROR
    logging.basicConfig(level=logging.WARNING)  # Общий уровень WARNING
    dist_logger = logging.getLogger("distribution")
    dist_logger.setLevel(logging.ERROR)  # Для distribution только ERROR и выше
    
    sleep_for = 30
    while True:
        try:
            cfg = await _load_config()
            sleep_for = max(1, cfg.tick_seconds)
            await tick_once(cfg, bot=bot, alerts_chat_id=alerts_chat_id)
        except Exception as exc:
            logger.exception("[dist] exception: %s", exc)
            _dist_log(f"[dist] exception: {exc}", level="ERROR")
        await asyncio.sleep(sleep_for)
