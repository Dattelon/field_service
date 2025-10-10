# field_service/services/distribution_worker.py
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from typing import Any, Optional, Sequence, cast

from sqlalchemy import insert, select, text, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from field_service.db.session import SessionLocal
from field_service.db import models as m
from field_service.services import live_log
from field_service.services.settings_service import get_timezone, get_working_window

UTC = timezone.utc

CATEGORY_TO_SKILL_CODE = {
    "ELECTRICS": "ELEC",
    "PLUMBING": "PLUMB",
    "APPLIANCES": "APPLI",
    "WINDOWS": "WINDOWS",
    "HANDYMAN": "HANDY",
    "ROADSIDE": "AUTOHELP",
}

LEGACY_STATUS_ALIASES = {
    "DISTRIBUTION": m.OrderStatus.SEARCHING,
    "SCHEDULED": m.OrderStatus.EN_ROUTE,
    "IN_PROGRESS": m.OrderStatus.WORKING,
    "INPROGRESS": m.OrderStatus.WORKING,
    "DONE": m.OrderStatus.PAYMENT,
}

def _skill_code_for_category(category: str | None) -> str | None:
    if not category:
        return None
    return CATEGORY_TO_SKILL_CODE.get(str(category).upper())

# ---------- helpers ----------


async def _get_int_setting(session: AsyncSession, key: str, default: int) -> int:
    row = await session.execute(select(m.settings.value).where(m.settings.key == key))
    v = row.scalar_one_or_none()
    try:
        return int(v) if v is not None else int(default)
    except Exception:
        return int(default)


async def _max_active_limit_for(session: AsyncSession) -> int:
    """Return the global default max active orders (fallback 5)."""
    value = await _get_int_setting(session, "max_active_orders", 5)
    # Safety guard: at least 1 active order allowed.
    return max(1, int(value))


@dataclass
class DistConfig:
    sla_seconds: int
    rounds: int
    escalate_to_admin_after_min: int


async def _load_config(session: AsyncSession) -> DistConfig:
    sla = await _get_int_setting(session, "distribution_sla_seconds", 120)
    rnd = await _get_int_setting(session, "distribution_rounds", 2)
    esc = await _get_int_setting(session, "escalate_to_admin_after_min", 10)
    return DistConfig(sla_seconds=sla, rounds=rnd, escalate_to_admin_after_min=esc)



def _now() -> datetime:
    return datetime.now(UTC)


ESC_REASON_LOGIST = "distribution_escalate_logist"
ESC_REASON_ADMIN = "distribution_escalate_admin"


def _status_enum(value: Any) -> m.OrderStatus:
    if isinstance(value, m.OrderStatus):
        return value
    raw = str(value).strip().upper()
    alias = LEGACY_STATUS_ALIASES.get(raw)
    if alias:
        return alias
    try:
        return m.OrderStatus(raw)
    except Exception:
        return m.OrderStatus.SEARCHING


def _coerce_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    try:
        parsed = datetime.fromisoformat(str(value))
    except Exception:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


async def _set_order_fields(
    session: Optional[AsyncSession],
    order_id: int,
    **values: Any,
) -> None:
    if session is None or not values:
        return
    await session.execute(
        update(m.orders).where(m.orders.id == order_id).values(**values)
    )


async def _append_history(
    session: Optional[AsyncSession],
    order: Any,
    reason: str,
) -> None:
    if session is None:
        return
    status = _status_enum(getattr(order, "status", m.OrderStatus.SEARCHING))
    await session.execute(
        insert(m.order_status_history).values(
            order_id=order.id,
            from_status=status,
            to_status=status,
            reason=reason,
            actor_type=m.ActorType.AUTO_DISTRIBUTION,
        )
    )


async def _latest_offer_sent_at(
    session: Optional[AsyncSession], order_id: int
) -> datetime | None:
    if session is None:
        return None
    row = await session.execute(
        text(
            "SELECT MAX(sent_at) FROM offers WHERE order_id=:oid"
        ).bindparams(oid=order_id)
    )
    return row.scalar_one_or_none()


async def _reset_escalations(
    session: Optional[AsyncSession], order: Any
) -> None:
    if (
        getattr(order, "dist_escalated_logist_at", None) is None
        and getattr(order, "dist_escalated_admin_at", None) is None
    ):
        return
    setattr(order, "dist_escalated_logist_at", None)
    setattr(order, "dist_escalated_admin_at", None)
    await _set_order_fields(
        session,
        order.id,
        dist_escalated_logist_at=None,
        dist_escalated_admin_at=None,
    )


async def _mark_logist_escalation(
    session: Optional[AsyncSession],
    order: Any,
    reason_suffix: str,
) -> None:
    now = _now()
    current = _coerce_dt(getattr(order, "dist_escalated_logist_at", None))
    if current is None:
        setattr(order, "dist_escalated_logist_at", now)
        setattr(order, "dist_escalated_admin_at", None)
        await _set_order_fields(
            session,
            order.id,
            dist_escalated_logist_at=now,
            dist_escalated_admin_at=None,
        )
        await _append_history(session, order, f"{ESC_REASON_LOGIST}:{reason_suffix}")
        message = log_escalate(order.id)
        print(message)
        try:
            live_log.push("dist", message, level="WARN")
        except Exception:
            pass
    else:
        setattr(order, "dist_escalated_logist_at", current)


async def _maybe_escalate_admin(
    session: Optional[AsyncSession],
    cfg: DistConfig,
    order: Any,
) -> None:
    logistic_at = _coerce_dt(getattr(order, "dist_escalated_logist_at", None))
    if logistic_at is None:
        return
    setattr(order, "dist_escalated_logist_at", logistic_at)

    admin_at = _coerce_dt(getattr(order, "dist_escalated_admin_at", None))
    if admin_at is not None:
        return

    last_offer = await _latest_offer_sent_at(session, order.id)
    last_offer_at = _coerce_dt(last_offer)
    if last_offer_at and logistic_at < last_offer_at:
        await _reset_escalations(session, order)
        return

    if _now() - logistic_at >= timedelta(minutes=cfg.escalate_to_admin_after_min):
        now = _now()
        setattr(order, "dist_escalated_admin_at", now)
        await _set_order_fields(
            session,
            order.id,
            dist_escalated_admin_at=now,
        )
        await _append_history(session, order, ESC_REASON_ADMIN)
        message = log_escalate_admin(order.id)
        print(message)
        try:
            live_log.push("dist", message, level="WARN")
        except Exception:
            pass


# ---------- logs: unified formatter ( D v1.1) ----------


def fmt_rank_item(row: dict[str, Any]) -> str:
    """Format candidate row according to log spec."""
    shift_flag = "on" if row.get("shift", True) else "off"
    car_flag = 1 if row.get("car") else 0
    avg_val = float(row.get("avg_week") or 0)
    rating_val = float(row.get("rating", 0) or 0)
    rnd_val = float(row.get("rnd", 0) or 0)
    return (
        f"{{mid={row['mid']} shift={shift_flag} car={car_flag} "
        f"avg_week={avg_val:.0f} rating={rating_val:.1f} "
        f"score=car({car_flag})>avg({avg_val:.0f})>rat({rating_val:.1f})>rnd({rnd_val:.2f})}}"
    )


def log_tick_header(
    order_row: Any, round_num: int, rounds_total: int, sla: int, candidates_cnt: int
) -> str:
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
    return (
        f"[dist] order={order_row.id} city={order_row.city_id} "
        f"district={district if district is not None else '-'} cat={cat} type={order_type}\n"
        f"round={round_num}/{rounds_total} sla={sla}s candidates={candidates_cnt}"
    )


def log_decision_offer(mid: int, until: datetime) -> str:
    return f"decision=offer mid={mid} until={until.isoformat()}"


def log_force_first(mid: int) -> str:
    return f"force_first=preferred_master mid={mid}"


def log_skip_no_district(order_id: int) -> str:
    return f"[dist] order={order_id} skip_auto: no_district  escalate=logist_now"


def log_skip_no_category(order_id: int, category: Any) -> str:
    value = category if category not in (None, "") else "-"
    return (
        f"[dist] order={order_id} skip_auto: no_category_filter "
        f"category={value} -> escalate=logist_now"
    )


def log_escalate(order_id: int) -> str:
    return f"[dist] order={order_id} candidates=0  escalate=logist"


def log_escalate_admin(order_id: int) -> str:
    return f"[dist] order={order_id} escalate=admin"


# ---------- core queries ----------


async def autoblock_guarantee_timeouts(session: AsyncSession) -> int:
    """Auto-block preferred master if he timed out on a GUARANTEE offer."""
    rows = await session.execute(
        text(
            """
        WITH timed AS (
          SELECT DISTINCT o.preferred_master_id AS mid
            FROM offers ofr
            JOIN orders o ON o.id = ofr.order_id
            JOIN masters m ON m.id = ofr.master_id
           WHERE ofr.state = 'EXPIRED'
             AND o.status = 'GUARANTEE'
             AND o.preferred_master_id IS NOT NULL
             AND ofr.master_id = o.preferred_master_id
             AND m.is_blocked = FALSE
        )
        UPDATE masters
           SET is_blocked = TRUE,
               is_active = FALSE,
               blocked_at = NOW(),
               blocked_reason = 'guarantee_refusal'
         WHERE id IN (SELECT mid FROM timed)
         RETURNING id
        """
        )
    )
    changed = rows.fetchall()
    master_ids = [int(row[0]) for row in changed]
    for mid in master_ids:
        message = f"guarantee_autoblock mid={mid} reason=timeout"
        print(f"[dist] {message}")
        try:
            live_log.push("dist", message, level="WARN")
        except Exception:
            pass
    return len(master_ids)


async def autoblock_guarantee_declines(session: AsyncSession) -> int:
    """Auto-block preferred master if they explicitly declined a GUARANTEE offer."""
    rows = await session.execute(
        text(
            """
        WITH declined AS (
          SELECT DISTINCT o.preferred_master_id AS mid
            FROM offers ofr
            JOIN orders o ON o.id = ofr.order_id
            JOIN masters m ON m.id = ofr.master_id
           WHERE ofr.state = 'DECLINED'
             AND o.status = 'GUARANTEE'
             AND o.preferred_master_id IS NOT NULL
             AND ofr.master_id = o.preferred_master_id
             AND m.is_blocked = FALSE
        )
        UPDATE masters
           SET is_blocked = TRUE,
               is_active = FALSE,
               blocked_at = NOW(),
               blocked_reason = 'guarantee_refusal'
         WHERE id IN (SELECT mid FROM declined)
         RETURNING id
        """
        )
    )
    changed = rows.fetchall()
    master_ids = [int(row[0]) for row in changed]
    for mid in master_ids:
        message = f"guarantee_autoblock mid={mid} reason=decline"
        print(f"[dist] {message}")
        try:
            live_log.push("dist", message, level="WARN")
        except Exception:
            pass
    return len(master_ids)


async def expire_sent_offers(session: AsyncSession, now: datetime) -> int:
    """Expire SENT offers by SLA."""
    result = await session.execute(
        text(
            """
        UPDATE offers
           SET state='EXPIRED', responded_at=NOW()
         WHERE state='SENT' AND (expires_at IS NOT NULL) AND expires_at < NOW()
        """
        )
    )
    cursor = cast(CursorResult[Any], result)
    return int(cursor.rowcount or 0)
    # ндекс: ix_offers__expires_at (миграция 0001) — быстрый апдейт по диапазону.


async def finalize_accepted_if_any(session: AsyncSession, order_id: int) -> bool:
    """
      ACCEPTED    .
    Races  WHERE assigned_master_id IS NULL + partial unique index uix_offers__order_accepted_once.
    """
    row = await session.execute(
        text(
            """
        SELECT master_id FROM offers
         WHERE order_id=:oid AND state='ACCEPTED'
         ORDER BY responded_at DESC NULLS LAST
         LIMIT 1
        """
        ).bindparams(oid=order_id)
    )
    r = row.first()
    if not r:
        return False
    master_id = int(r[0])
    upd = await session.execute(
        text(
            """
        UPDATE orders
           SET assigned_master_id=:mid,
               status='ASSIGNED',
               updated_at=NOW(),
               version=version+1
         WHERE id=:oid AND assigned_master_id IS NULL
         RETURNING id
        """
        ).bindparams(oid=order_id, mid=master_id)
    )
    ok = upd.first() is not None
    if ok:
        # :   SENT      ACCEPTED   
        pass
    return ok
    # ндекс: uix_offers__order_accepted_once (partial unique).
    # ндексы orders: ix_orders__status_city_date, ix_orders__assigned_master — апдейты не медленные (PK).


async def fetch_orders_batch(session: AsyncSession, limit: int = 100) -> Sequence[Any]:
    """Fetch up to `limit` candidate orders (SKIP LOCKED) in SEARCHING/
    GUARANTEE statuses for distribution processing."""
    rows = await session.execute(
        text(
            """
        SELECT id,
               city_id,
               district_id,
               preferred_master_id,
               status,
               category,
               order_type,
               dist_escalated_logist_at,
               dist_escalated_admin_at,
               no_district
          FROM orders
         WHERE assigned_master_id IS NULL
           AND status IN ('SEARCHING','GUARANTEE')
         ORDER BY created_at
         LIMIT :lim
         FOR UPDATE SKIP LOCKED
        """
        ).bindparams(lim=limit)
    )
    return rows.fetchall()
    # ндекс: ix_orders__city_status и ix_orders__status_city_date.


async def current_round(session: AsyncSession, order_id: int) -> int:
    row = await session.execute(
        text(
            "SELECT COALESCE(max(round_number),0) FROM offers WHERE order_id=:oid"
        ).bindparams(oid=order_id)
    )
    return int(row.scalar_one() or 0)
    # ндексы: ix_offers__order_state (по order_id).


async def has_active_sent_offer(session: AsyncSession, order_id: int) -> bool:
    row = await session.execute(
        text(
            """
        SELECT 1
          FROM offers
         WHERE order_id=:oid
           AND state='SENT'
           AND (expires_at IS NULL OR expires_at > NOW())
         LIMIT 1
        """
        ).bindparams(oid=order_id)
    )
    return row.first() is not None


async def candidate_rows(
    session: AsyncSession,
    order_id: int,
    city_id: int,
    district_id: int | None,
    preferred_master_id: int | None,
    skill_code: str,
    limit: int,
    force_preferred_first: bool = False,
) -> list[dict[str, Any]]:
    """
    Ƹ  ( ,     orders):
      -  
      -  // 
      -   (SHIFT_ON)
      -    
      -    
      -  ,       
    : car desc, avg_week desc, rating desc, random asc
    """
    #   (-  override   SQL)
    global_limit = await _max_active_limit_for(session)

    if not skill_code:
        return []

    # NOTE: orders.category holds ENUM-like strings; map to skills via CATEGORY_TO_SKILL_CODE.
    sql = text(
        f"""
    WITH active_cnt AS (
      SELECT assigned_master_id AS mid, count(*) AS cnt
        FROM orders
       WHERE assigned_master_id IS NOT NULL
         AND status IN ('ASSIGNED','EN_ROUTE','WORKING','PAYMENT')
       GROUP BY assigned_master_id
    ),
    avg7 AS (
      SELECT assigned_master_id AS mid, AVG(total_sum)::numeric(10,2) AS avg_check
        FROM orders
       WHERE assigned_master_id IS NOT NULL
         AND status IN ('PAYMENT','CLOSED')
         AND created_at >= NOW() - INTERVAL '7 days'
       GROUP BY assigned_master_id
    )
    SELECT
        m.id              AS mid,
        m.has_vehicle     AS car,
        m.rating          AS rating,
        COALESCE(a.avg_check, 0) AS avg_week,
        COALESCE(ac.cnt, 0)      AS active_cnt,
        m.is_on_shift     AS shift,
        RANDOM()          AS rnd
    FROM masters m
    JOIN master_districts md
      ON md.master_id = m.id
     AND md.district_id = :did
    JOIN master_skills ms
      ON ms.master_id = m.id
    JOIN skills s
      ON s.id = ms.skill_id
     AND s.code = :skill_code
     AND s.is_active = TRUE
    LEFT JOIN active_cnt ac ON ac.mid = m.id
    LEFT JOIN avg7 a ON a.mid = m.id
    WHERE m.city_id = :cid
      AND m.is_active = TRUE
      AND m.is_blocked = FALSE
      AND m.verified = TRUE
      AND m.is_on_shift = TRUE
      AND (m.break_until IS NULL OR m.break_until <= NOW())
      --   :  override  
      AND (COALESCE(m.max_active_orders_override, :gmax) > COALESCE(ac.cnt,0))
      --  ,        
      AND NOT EXISTS (
        SELECT 1 FROM offers o
         WHERE o.order_id = :oid AND o.master_id = m.id
      )
    ORDER BY
      (CASE WHEN m.has_vehicle THEN 1 ELSE 0 END) DESC,
      a.avg_check DESC NULLS LAST,
      m.rating DESC NULLS LAST,
      rnd ASC
    LIMIT :lim
    """
    ).bindparams(
        cid=city_id, did=district_id, oid=order_id, lim=limit, gmax=global_limit, skill_code=skill_code
    )

    rows = await session.execute(sql)
    out = []
    for r in rows.mappings():
        out.append(dict(r))
    # : force first  ,        
    if force_preferred_first and preferred_master_id:
        idx = next(
            (i for i, x in enumerate(out) if int(x["mid"]) == int(preferred_master_id)),
            -1,
        )
        if idx >= 0:
            pm = out.pop(idx)
            out.insert(0, pm)
            print(log_force_first(int(preferred_master_id)))
    return out
    # ндексы:
    #  - ix_masters__mod_shift (moderation_status, shift_status)
    #  - ix_masters__city_id
    #  - ix_masters__heartbeat ()
    #  - master_districts PK (master_id, district_id)
    #  - ix_orders__assigned_master  active_cnt
    #  - ix_orders__created_at  avg7


async def send_offer(
    session: AsyncSession,
    order_id: int,
    master_id: int,
    round_number: int,
    sla_seconds: int,
) -> bool:
    """демпотентная вставка оффера (уникальность (order_id, master_id))."""
    row = await session.execute(
        text(
            """
        INSERT INTO offers(order_id, master_id, round_number, state, sent_at, expires_at)
        VALUES (:oid, :mid, :rnd, 'SENT', NOW(), NOW() + MAKE_INTERVAL(secs => :sla))
        ON CONFLICT ON CONSTRAINT uq_offers__order_master DO NOTHING
        RETURNING id
        """
        ).bindparams(oid=order_id, mid=master_id, rnd=round_number, sla=sla_seconds)
    )
    return row.first() is not None
    # ндексы: uq_offers__order_master, ix_offers__order_state.


# ---------- per-order processing ----------\n\n
async def process_one_order(
    session: Optional[AsyncSession], cfg: DistConfig, o: Any
) -> None:
    await _maybe_escalate_admin(session, cfg, o)

    district_missing = getattr(o, "district_id", None) is None
    no_district_flag = bool(getattr(o, "no_district", False))
    if district_missing or no_district_flag:
        message = log_skip_no_district(o.id)
        print(message)
        try:
            live_log.push("dist", message, level="WARN")
        except Exception:
            pass
        await _mark_logist_escalation(session, o, "no_district")
        await _maybe_escalate_admin(session, cfg, o)
        return

    if await has_active_sent_offer(session, o.id):
        await _reset_escalations(session, o)
        return

    if await finalize_accepted_if_any(session, o.id):
        await _reset_escalations(session, o)
        print(f"[dist] order={o.id} assigned_by_offer")
        return

    cur = await current_round(session, o.id)
    if cur >= cfg.rounds:
        await _mark_logist_escalation(session, o, "rounds_exhausted")
        await _maybe_escalate_admin(session, cfg, o)
        return
    next_round = cur + 1

    order_type = getattr(o, "type", None)
    if order_type is None:
        order_type = getattr(o, "order_type", None)
    status = getattr(o, "status", None)
    is_guarantee = False
    if status is not None and str(status) == m.OrderStatus.GUARANTEE.value:
        is_guarantee = True
    if not is_guarantee and order_type is not None:
        try:
            is_guarantee = str(order_type) == m.OrderType.GUARANTEE.value
        except AttributeError:
            is_guarantee = str(order_type).upper() == "GUARANTEE"

    category = getattr(o, "category", None)
    skill_code = _skill_code_for_category(category)
    if skill_code is None:
        message = log_skip_no_category(o.id, category)
        print(message)
        try:
            live_log.push("dist", message, level="WARN")
        except Exception:
            pass
        return

    cand = await candidate_rows(
        session=session,
        order_id=o.id,
        city_id=o.city_id,
        district_id=o.district_id,
        preferred_master_id=o.preferred_master_id,
        skill_code=skill_code,
        limit=50,
        force_preferred_first=is_guarantee,
    )

    header = log_tick_header(o, next_round, cfg.rounds, cfg.sla_seconds, len(cand))
    print(header)
    try:
        live_log.push("dist", header)
    except Exception:
        pass
    if cand:
        top = cand[:10]
        ranked = ", ".join(
            fmt_rank_item(
                {
                    "mid": x["mid"],
                    "car": x["car"],
                    "avg_week": float(x["avg_week"] or 0),
                    "rating": float(x["rating"] or 0),
                    "rnd": float(x["rnd"] or 0),
                }
            )
            for x in top
        )
        ranked_block = "ranked=[\n  " + ranked + "\n]"
        print(ranked_block)
        try:
            live_log.push("dist", ranked_block)
        except Exception:
            pass

        first = cand[0]
        await _reset_escalations(session, o)
        ok = await send_offer(
            session, o.id, int(first["mid"]), next_round, cfg.sla_seconds
        )
        if ok:
            until = _now() + timedelta(seconds=cfg.sla_seconds)
            decision = log_decision_offer(int(first["mid"]), until)
            print(decision)
            try:
                live_log.push("dist", decision)
            except Exception:
                pass
        else:
            print(
                f"[dist] order={o.id} race_conflict: offer exists for mid={first['mid']}"
            )
    else:
        await _mark_logist_escalation(session, o, "no_candidates")
        await _maybe_escalate_admin(session, cfg, o)
# ---------- main loop ----------




async def tick_once() -> None:
    async with SessionLocal() as s:
        cfg = await _load_config(s)
        # 0)  SENT
        expired = await expire_sent_offers(s, _now())
        if expired:
            await s.commit()
        blocked = await autoblock_guarantee_timeouts(s)
        if blocked:
            await s.commit()
        declined_blocked = await autoblock_guarantee_declines(s)
        if declined_blocked:
            await s.commit()

        # 1)    
        rows = await fetch_orders_batch(s, limit=100)
        #    (    )
        for o in rows:
            await process_one_order(s, cfg, o)
        await s.commit()  #  /


async def run_loop() -> None:
    while True:
        try:
            await tick_once()
        except Exception as e:
            print(f"[dist] ERROR: {e!r}")
        await asyncio.sleep(30)


# CLI
async def main() -> None:
    print("[dist] worker started")
    await run_loop()


if __name__ == "__main__":
    asyncio.run(main())
