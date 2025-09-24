from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Optional

from aiogram import Bot
from sqlalchemy import insert, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from field_service.config import settings as env_settings
from field_service.db import models as m
from field_service.db.session import SessionLocal
from field_service.services import live_log, time_service, settings_service as settings_store
from field_service.infra.logging_utils import send_alert
from field_service.services.settings_service import (
    get_int,
)

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
                escalated_logist_at=row["dist_escalated_logist_at"],
                escalated_admin_at=row["dist_escalated_admin_at"],
            )
        )
    return orders



async def _expire_overdue_offer(session: AsyncSession, order_id: int) -> Optional[int]:
    """Р•СЃР»Рё РµСЃС‚СЊ SENT Рё РѕРЅ РїСЂРѕС‚СѓС… вЂ” EXPIRED, РІРµСЂРЅСѓС‚СЊ master_id РґР»СЏ Р»РѕРіР° timeout; РёРЅР°С‡Рµ None."""
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
    return 1 if r == 0 else r


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
        select(m.orders.id, m.orders.city_id, m.orders.scheduled_date).where(
            m.orders.status == m.OrderStatus.DEFERRED
        )
    )
    records = rows.all()
    if not records:
        return []
    workday_start, _ = await _workday_window()
    awakened: list[tuple[int, ZoneInfo, date]] = []
    tz_cache: dict[int, ZoneInfo] = {}
    for order_id, city_id, scheduled_date in records:
        if city_id in tz_cache:
            tz = tz_cache[city_id]
        else:
            tz = await _city_timezone(session, city_id)
            tz_cache[city_id] = tz
        local_now = now_utc.astimezone(tz)
        target_date = scheduled_date or local_now.date()
        if local_now.date() < target_date:
            continue
        local_time = local_now.timetz()
        if local_time.tzinfo is not None:
            local_time = local_time.replace(tzinfo=None)
        if local_now.date() == target_date and local_time < workday_start:
            if order_id not in DEFERRED_LOGGED:
                target_local = datetime.combine(target_date, workday_start, tzinfo=tz)
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
        target_local = datetime.combine(target_date, workday_start, tzinfo=tz)
        awakened.append((order_id, target_local))
    return awakened




async def _candidates(
    session: AsyncSession,
    *,
    oid: int,
    city_id: int,
    district_id: int,
    round_number: int,
    preferred_mid: Optional[int],
) -> list[dict]:
    # Р°РєС‚РёРІРЅС‹Рµ Р»РёРјРёС‚С‹ (per-master override -> settings.max_active_orders)
    # СЃСЂРµРґРЅРёР№ С‡РµРє Р·Р° 7 РґРЅРµР№
    # С„РёР»СЊС‚СЂС‹ СЃРјРµРЅС‹, Р±Р»РѕРєРёСЂРѕРІРєРё Рё С‚.Рґ.
    sql = text(
        """
    WITH lim AS (
      SELECT m.id AS master_id,
             COALESCE(m.max_active_orders_override,
                      (SELECT CAST(value AS INT) FROM settings WHERE key='max_active_orders' LIMIT 1)
             ) AS max_limit,
             (SELECT COUNT(*) FROM orders o2
               WHERE o2.assigned_master_id = m.id
                 AND o2.status IN ('ASSIGNED','EN_ROUTE','WORKING','PAYMENT')
             ) AS active_cnt
      FROM masters m
    ), avg7 AS (
      SELECT o.assigned_master_id AS mid, AVG(o.total_price)::numeric(10,2) AS avg_week_check
      FROM orders o
      WHERE o.status IN ('PAYMENT','CLOSED')
        AND o.created_at >= (NOW() - INTERVAL '7 days')
      GROUP BY o.assigned_master_id
    )
    SELECT m.id                  AS mid,
           m.has_vehicle         AS car,
           COALESCE(a.avg_week_check,0)::numeric(10,2) AS avg_week,
           COALESCE(m.rating,0)::numeric(3,1) AS rating,
           m.is_on_shift        AS shift,
           RANDOM()              AS rnd
      FROM masters m
      JOIN master_districts md ON md.master_id=m.id AND md.district_id=:did
      -- JOIN master_skills ms  ON ms.master_id=m.id AND ms.skill_id=:skill_id   -- TODO РїРѕСЃР»Рµ РјРёРіСЂР°С†РёРё orders.skill_id
      JOIN lim ON lim.master_id=m.id
      LEFT JOIN avg7 a ON a.mid=m.id
     WHERE m.city_id=:cid
       AND m.is_active=TRUE
       AND m.is_blocked=FALSE
       AND m.verified = TRUE
       AND m.is_on_shift = TRUE
       AND lim.active_cnt < lim.max_limit
       AND m.id NOT IN (
            SELECT ofr.master_id FROM offers ofr
             WHERE ofr.order_id=:oid AND ofr.round_number=:r
       )
     ORDER BY
       (CASE WHEN m.id = :pref THEN 1 ELSE 0 END) DESC,   -- force_first РґР»СЏ РіР°СЂР°РЅС‚РёРё
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
            r=round_number,
            pref=(preferred_mid or -1),
        )
    )
    return [
        dict(
            mid=r[0],
            car=bool(r[1]),
            avg_week=float(r[2]),
            rating=float(r[3]),
            shift=bool(r[4]),
            rnd=float(r[5]),
        )
        for r in rs.fetchall()
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
    if order.escalated_logist_at is None and order.escalated_admin_at is None:
        return
    await session.execute(
        text(
            """
        UPDATE orders
           SET dist_escalated_logist_at = NULL,
               dist_escalated_admin_at = NULL
         WHERE id = :oid
        """
        ).bindparams(oid=order.id)
    )
    order.escalated_logist_at = None
    order.escalated_admin_at = None


async def _escalate_logist(order_id: int):
    message = f"[dist] order={order_id} escalate=logist"
    logger.warning(message)
    _dist_log(message, level="WARN")


async def tick_once(cfg: DistConfig, *, bot: Bot | None, alerts_chat_id: Optional[int]) -> None:
    async with SessionLocal() as session:
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
            if (
                order.escalated_logist_at is not None
                and order.escalated_admin_at is None
                and now - order.escalated_logist_at >= timedelta(minutes=cfg.to_admin_after_min)
            ):
                admin_marked = await _set_admin_escalation(session, order)
                if admin_marked:
                    admin_message = f"[dist] order={order.id} escalate=admin"
                    logger.warning(admin_message)
                    _dist_log(admin_message, level="WARN")
                    await send_alert(
                        bot,
                        f"вЏ± Р—Р°СЏРІРєР° #{order.id} РЅРµ СЂР°СЃРїСЂРµРґРµР»РµРЅР° Р»РѕРіРёСЃС‚РѕРј 10 РјРёРЅ. Р­СЃРєР°Р»Р°С†РёСЏ Р°РґРјРёРЅРёСЃС‚СЂР°С‚РѕСЂСѓ.",
                        chat_id=alerts_chat_id,
                    )

            if order.district_id is None:
                message = (
                    f"[dist] order={order.id} city={order.city_id} district=null skip_auto: no_district -> escalate=logist_now"
                )
                logger.info(message)
                _dist_log(message)
                if order.escalated_logist_at is None:
                    marked = await _set_logist_escalation(session, order)
                    if marked:
                        await send_alert(
                            bot,
                            f"вљ пёЏ Р—Р°СЏРІРєР° #{order.id} Р±РµР· СЂР°Р№РѕРЅР° РІ РіРѕСЂРѕРґРµ {order.city_name}. РўСЂРµР±СѓРµС‚СЃСЏ СЂСѓС‡РЅРѕРµ РЅР°Р·РЅР°С‡РµРЅРёРµ.",
                            chat_id=alerts_chat_id,
                        )
                await _escalate_logist(order.id)
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

            ranked = await _candidates(
                session,
                oid=order.id,
                city_id=order.city_id,
                district_id=order.district_id,
                round_number=current_round,
                preferred_mid=order.preferred_master_id,
            )
            await _log_ranked(
                order.id,
                order.city_id,
                order.district_id,
                None,
                "GUARANTEE" if order.preferred_master_id else "NORMAL",
                current_round,
                cfg.rounds,
                cfg.sla_seconds,
                ranked,
                order.preferred_master_id,
                cfg.top_log_n,
            )

            if not ranked:
                if current_round < cfg.rounds:
                    message = f"[dist] order={order.id} round={current_round} -> next_round"
                    logger.info(message)
                    _dist_log(message)
                else:
                    message = f"[dist] order={order.id} round={current_round} no_candidates -> escalate=logist"
                    logger.info(message)
                    _dist_log(message)
                    newly_marked = False
                    if order.escalated_logist_at is None:
                        marked = await _set_logist_escalation(session, order)
                        newly_marked = marked is not None
                    await _escalate_logist(order.id)
                    if newly_marked:
                        await send_alert(
                            bot,
                            f"вљ пёЏ РќРµС‚ СЃРІРѕР±РѕРґРЅС‹С… РјР°СЃС‚РµСЂРѕРІ РІ РіРѕСЂРѕРґРµ {order.city_name} РїРѕ Р·Р°СЏРІРєРµ #{order.id}. Р­СЃРєР°Р»Р°С†РёСЏ Р»РѕРіРёСЃС‚Сѓ.",
                            chat_id=alerts_chat_id,
                        )
                continue

            first_mid = ranked[0]["mid"]
            await _reset_escalations(session, order)
            ok = await _send_offer(
                session,
                oid=order.id,
                mid=first_mid,
                round_number=current_round,
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
    logging.basicConfig(level=logging.INFO)
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
