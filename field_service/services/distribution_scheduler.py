from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, time
from typing import Optional

from sqlalchemy import insert, text
from sqlalchemy.ext.asyncio import AsyncSession

from field_service.config import settings as env_settings
from field_service.db import models as m
from field_service.db.session import SessionLocal
from field_service.services import live_log
from field_service.services.settings_service import (
    get_int,
    get_working_window,
    get_timezone,
)

logger = logging.getLogger("distribution")
ADVISORY_LOCK_KEY = 982734

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
) -> list[tuple[int, int, Optional[int], Optional[int]]]:
    # Возвращаем (id, city_id, district_id, preferred_master_id)
    q = await session.execute(
        text(
            """
        SELECT o.id, o.city_id, o.district_id, o.preferred_master_id
          FROM orders o
         WHERE o.status IN ('SEARCHING','GUARANTEE')
           AND o.assigned_master_id IS NULL
         ORDER BY o.created_at
         LIMIT 100
         FOR UPDATE SKIP LOCKED
        """
        )
    )
    return [(r[0], r[1], r[2], r[3]) for r in q.all()]


async def _expire_overdue_offer(session: AsyncSession, order_id: int) -> Optional[int]:
    """Если есть SENT и он протух — EXPIRED, вернуть master_id для лога timeout; иначе None."""
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


async def _sync_working_window(
    session: AsyncSession,
    *,
    now_local: datetime,
    work_start: time,
    work_end: time,
) -> tuple[int, int]:
    local_time = now_local.timetz()
    if local_time.tzinfo is not None:
        local_time = local_time.replace(tzinfo=None)
    reopened = deferred = 0
    if work_start <= local_time < work_end:
        reopened = await _transition_orders(
            session,
            old_status=m.OrderStatus.DEFERRED.value,
            new_status=m.OrderStatus.SEARCHING.value,
            reason="working_window_open",
        )
    else:
        deferred = await _transition_orders(
            session,
            old_status=m.OrderStatus.SEARCHING.value,
            new_status=m.OrderStatus.DEFERRED.value,
            reason="working_window_closed",
        )
    return reopened, deferred


async def _candidates(
    session: AsyncSession,
    *,
    oid: int,
    city_id: int,
    district_id: int,
    round_number: int,
    preferred_mid: Optional[int],
) -> list[dict]:
    # активные лимиты (per-master override -> settings.max_active_orders)
    # средний чек за 7 дней
    # фильтры смены, блокировки и т.д.
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
      -- JOIN master_skills ms  ON ms.master_id=m.id AND ms.skill_id=:skill_id   -- TODO после миграции orders.skill_id
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
       (CASE WHEN m.id = :pref THEN 1 ELSE 0 END) DESC,   -- force_first для гарантии
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
        parts.append("ranked=[
" + "
".join(top_lines) + "
]")
    logger.info("
".join(parts))

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


async def _escalate_logist(order_id: int):
    message = f"[dist] order={order_id} escalate=logist"
    logger.warning(message)
    _dist_log(message, level="WARN")


async def tick_once(cfg: DistConfig) -> None:
    async with SessionLocal() as session:
        if not await _try_advisory_lock(session):
            return

        now = await _db_now(session)
        tz = get_timezone()
        now_local = now.astimezone(tz)
        work_start, work_end = await get_working_window()
        reopened, deferred = await _sync_working_window(
            session,
            now_local=now_local,
            work_start=work_start,
            work_end=work_end,
        )
        if reopened:
            message = f"[dist] window_open reopened={reopened} at {now_local.isoformat()}"
            logger.info(message)
            _dist_log(message)
        if deferred:
            message = f"[dist] window_closed deferred={deferred} at {now_local.isoformat()}"
            logger.info(message)
            _dist_log(message)

        orders = await _fetch_orders_for_distribution(session)

        for oid, city_id, district_id, preferred_mid in orders:
            if district_id is None:
                message = (
                    f"[dist] order={oid} city={city_id} district=null skip_auto: no_district -> escalate=logist_now"
                )
                logger.info(message)
                _dist_log(message)
                await _escalate_logist(oid)
                continue

            timed_out_mid = await _expire_overdue_offer(session, oid)
            if timed_out_mid:
                message = f"[dist] order={oid} timeout mid={timed_out_mid}"
                logger.info(message)
                _dist_log(message)

            row = await session.execute(
                text(
                    "SELECT 1 FROM offers WHERE order_id=:oid AND state='SENT' LIMIT 1"
                ).bindparams(oid=oid)
            )
            if row.first():
                continue

            current_round = await _current_round(session, oid)

            ranked = await _candidates(
                session,
                oid=oid,
                city_id=city_id,
                district_id=district_id,
                round_number=current_round,
                preferred_mid=preferred_mid,
            )
            await _log_ranked(
                oid,
                city_id,
                district_id,
                None,
                "GUARANTEE" if preferred_mid else "NORMAL",
                current_round,
                cfg.rounds,
                cfg.sla_seconds,
                ranked,
                preferred_mid,
                cfg.top_log_n,
            )

            if not ranked:
                if current_round < cfg.rounds:
                    message = f"[dist] order={oid} round={current_round} -> next_round"
                    logger.info(message)
                    _dist_log(message)
                else:
                    await _escalate_logist(oid)
                continue

            first_mid = ranked[0]["mid"]
            ok = await _send_offer(
                session,
                oid=oid,
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
                message = f"[dist] order={oid} decision=offer mid={first_mid} until={until.isoformat()}"
                logger.info(message)
                _dist_log(message)

        await session.commit()


async def run_scheduler() -> None:
    logging.basicConfig(level=logging.INFO)
    sleep_for = 30
    while True:
        try:
            cfg = await _load_config()
            sleep_for = max(1, cfg.tick_seconds)
            await tick_once(cfg)
        except Exception as exc:
            logger.exception("[dist] exception: %s", exc)
            _dist_log(f"[dist] exception: {exc}", level="ERROR")
        await asyncio.sleep(sleep_for)