# field_service/services/distribution_worker.py
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Sequence

from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from field_service.db.session import SessionLocal
from field_service.db import models as m

UTC = timezone.utc

# ---------- helpers ----------

async def _get_int_setting(session: AsyncSession, key: str, default: int) -> int:
    row = await session.execute(
        select(m.settings.value).where(m.settings.key == key)
    )
    v = row.scalar_one_or_none()
    try:
        return int(v) if v is not None else int(default)
    except Exception:
        return int(default)

async def _max_active_limit_for(session: AsyncSession) -> int:
    # глобальный лимит
    return await _get_int_setting(session, "max_active_orders", 1)

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

# ---------- logs: unified formatter (приложение D v1.1) ----------
def fmt_rank_item(row: dict[str, Any]) -> str:
    # row must contain: mid, shift, car, avg_week, rating, rnd
    return ("{mid=" + str(row["mid"]) +
            f" shift={row.get('shift','on')} car={1 if row.get('car') else 0} "
            f"avg_week={row.get('avg_week'):.0f} rating={row.get('rating', 0):.1f} "
            f"score=car({1 if row.get('car') else 0})>avg({int(row.get('avg_week') or 0)})"
            f">rat({row.get('rating', 0):.1f})>rnd({row.get('rnd', 0):.2f})" +
            "}")

def log_tick_header(order_row: Any, round_num: int, rounds_total: int, sla: int, candidates_cnt: int) -> str:
    return (f"[dist] order={order_row.id} city_id={order_row.city_id} "
            f"district_id={order_row.district_id or '-'} "
            f"type={'GUARANTEE' if str(order_row.status)=='GUARANTEE' else 'NORMAL'}\n"
            f"round={round_num}/{rounds_total} sla={sla}s candidates={candidates_cnt}")

def log_decision_offer(mid: int, until: datetime) -> str:
    return f"decision=offer mid={mid} until={until.isoformat()}"

def log_skip_no_district(order_id: int) -> str:
    return f"[dist] order={order_id} skip_auto: no_district → escalate=logist_now"

def log_escalate(order_id: int) -> str:
    return f"[dist] order={order_id} candidates=0 → escalate=logist"

# ---------- core queries ----------

async def expire_sent_offers(session: AsyncSession, now: datetime) -> int:
    """Expire SENT offers by SLA."""
    q = await session.execute(
        text("""
        UPDATE offers
           SET state='EXPIRED', responded_at=NOW()
         WHERE state='SENT' AND (expires_at IS NOT NULL) AND expires_at < NOW()
        """)
    )
    return q.rowcount or 0
    # Индекс: ix_offers__expires_at (миграция 0001) — быстрый апдейт по диапазону.

async def finalize_accepted_if_any(session: AsyncSession, order_id: int) -> bool:
    """
    Если есть ACCEPTED — закрепить мастера атомарно.
    Races закрывает WHERE assigned_master_id IS NULL + partial unique index uix_offers__order_accepted_once.
    """
    row = await session.execute(
        text("""
        SELECT master_id FROM offers
         WHERE order_id=:oid AND state='ACCEPTED'
         ORDER BY responded_at DESC NULLS LAST
         LIMIT 1
        """).bindparams(oid=order_id)
    )
    r = row.first()
    if not r:
        return False
    master_id = int(r[0])
    upd = await session.execute(
        text("""
        UPDATE orders
           SET assigned_master_id=:mid,
               status='ASSIGNED',
               updated_at=NOW(),
               version=version+1
         WHERE id=:oid AND assigned_master_id IS NULL
         RETURNING id
        """).bindparams(oid=order_id, mid=master_id)
    )
    ok = upd.first() is not None
    if ok:
        # фиксируем: у своих SENT по этому мастеру меняем на ACCEPTED уже сделано мастером
        pass
    return ok
    # Индекс: uix_offers__order_accepted_once (partial unique).
    # Индексы orders: ix_orders__status_city_date, ix_orders__assigned_master — апдейты не медленные (PK).

async def fetch_orders_batch(session: AsyncSession, limit: int = 100) -> Sequence[Any]:
    """
    Вытаскиваем заявки для распределения пачкой, блокируя строки (SKIP LOCKED).
    Учитываем оба статуса: DISTRIBUTION и GUARANTEE (по вашей схеме GUARANTEE — тоже ENUM статуса).
    """
    rows = await session.execute(
        text("""
        SELECT id, city_id, district_id, preferred_master_id, status
          FROM orders
         WHERE assigned_master_id IS NULL
           AND status IN ('DISTRIBUTION','GUARANTEE')
         ORDER BY created_at
         LIMIT :lim
         FOR UPDATE SKIP LOCKED
        """).bindparams(lim=limit)
    )
    return rows.fetchall()
    # Индекс: ix_orders__city_status и ix_orders__status_city_date.

async def current_round(session: AsyncSession, order_id: int) -> int:
    row = await session.execute(
        text("SELECT COALESCE(max(round_number),0) FROM offers WHERE order_id=:oid")
        .bindparams(oid=order_id)
    )
    return int(row.scalar_one() or 0)
    # Индексы: ix_offers__order_state (по order_id).

async def has_active_sent_offer(session: AsyncSession, order_id: int) -> bool:
    row = await session.execute(
        text("""
        SELECT 1
          FROM offers
         WHERE order_id=:oid
           AND state='SENT'
           AND (expires_at IS NULL OR expires_at > NOW())
         LIMIT 1
        """).bindparams(oid=order_id)
    )
    return row.first() is not None

async def candidate_rows(
    session: AsyncSession,
    order_id: int,
    city_id: int,
    district_id: int | None,
    preferred_master_id: int | None,
    limit: int,
) -> list[dict[str, Any]]:
    """
    Жёсткие фильтры (без категории, если её нет в orders):
      - город совпадает
      - мастер одобрен/активен/не блокирован
      - смена включена (SHIFT_ON)
      - район присутствует у мастера
      - не превышен лимит активных
      - исключить мастеров, которые уже получали оффер по этому заказу
    Сортировка: car desc, avg_week desc, rating desc, random asc
    """
    # Глобальный лимит (пер- мастер override учтём в SQL)
    global_limit = await _max_active_limit_for(session)

    # NOTE: без поля category в orders пропускаем skill-фильтр. Добавлю в [CHANGE REQUEST].
    sql = text(f"""
    WITH active_cnt AS (
      SELECT assigned_master_id AS mid, count(*) AS cnt
        FROM orders
       WHERE assigned_master_id IS NOT NULL
         AND status IN ('ASSIGNED','SCHEDULED','IN_PROGRESS','DONE')
       GROUP BY assigned_master_id
    ),
    avg7 AS (
      SELECT assigned_master_id AS mid, AVG(total_price)::numeric(10,2) AS avg_check
        FROM orders
       WHERE assigned_master_id IS NOT NULL
         AND status IN ('DONE','CLOSED')
         AND created_at >= NOW() - INTERVAL '7 days'
       GROUP BY assigned_master_id
    )
    SELECT
        m.id              AS mid,
        m.has_vehicle     AS car,
        m.rating          AS rating,
        COALESCE(a.avg_check, 0) AS avg_week,
        COALESCE(ac.cnt, 0)      AS active_cnt,
        RANDOM()          AS rnd
    FROM masters m
    JOIN master_districts md
      ON md.master_id = m.id
     AND md.district_id = :did
    LEFT JOIN active_cnt ac ON ac.mid = m.id
    LEFT JOIN avg7 a ON a.mid = m.id
    WHERE m.city_id = :cid
      AND m.is_active = TRUE
      AND m.is_blocked = FALSE
      AND m.moderation_status = 'APPROVED'
      AND m.shift_status = 'SHIFT_ON'
      AND (m.break_until IS NULL OR m.break_until <= NOW())
      -- лимит активных заказов: индивидуальный override либо глобальный
      AND (COALESCE(m.max_active_orders_override, :gmax) > COALESCE(ac.cnt,0))
      -- исключаем тех, кому уже слали любые офферы по этому заказу
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
    """).bindparams(
        cid=city_id, did=district_id, oid=order_id, lim=limit, gmax=global_limit
    )

    rows = await session.execute(sql)
    out = []
    for r in rows.mappings():
        out.append(dict(r))
    # Гарантия: force first прежнего мастера, если он прошёл фильтры и не получал оффер
    if preferred_master_id:
        idx = next((i for i, x in enumerate(out) if int(x["mid"]) == int(preferred_master_id)), -1)
        if idx >= 0:
            pm = out.pop(idx)
            out.insert(0, pm)
    return out
    # Индексы:
    #  - ix_masters__mod_shift (moderation_status, shift_status)
    #  - ix_masters__city_id
    #  - ix_masters__heartbeat (косвенно)
    #  - master_districts PK (master_id, district_id)
    #  - ix_orders__assigned_master для active_cnt
    #  - ix_orders__created_at для avg7

async def send_offer(
    session: AsyncSession,
    order_id: int,
    master_id: int,
    round_number: int,
    sla_seconds: int,
) -> bool:
    """Идемпотентная вставка оффера (уникальность (order_id, master_id))."""
    row = await session.execute(
        text("""
        INSERT INTO offers(order_id, master_id, round_number, state, sent_at, expires_at)
        VALUES (:oid, :mid, :rnd, 'SENT', NOW(), NOW() + MAKE_INTERVAL(secs => :sla))
        ON CONFLICT ON CONSTRAINT uq_offers__order_master DO NOTHING
        RETURNING id
        """).bindparams(oid=order_id, mid=master_id, rnd=round_number, sla=sla_seconds)
    )
    return row.first() is not None
    # Индексы: uq_offers__order_master, ix_offers__order_state.

# ---------- per-order processing ----------

async def process_one_order(session: AsyncSession, cfg: DistConfig, o: Any) -> None:
    # no_district → сразу логист
    if o.district_id is None:
        print(log_skip_no_district(o.id))
        return

    # если уже ждём ответа по SLA — ничего не делаем
    if await has_active_sent_offer(session, o.id):
        return

    # если уже есть ACCEPTED — закрепим мастера
    if await finalize_accepted_if_any(session, o.id):
        # зафиксируем лог
        print(f"[dist] order={o.id} assigned_by_offer")
        return

    # определить раунд
    cur = await current_round(session, o.id)
    if cur >= cfg.rounds:
        print(log_escalate(o.id))
        # здесь можно послать алерт логисту/админу через ваш канал, пока логируем
        return
    next_round = cur + 1

    # собрать кандидатов
    cand = await candidate_rows(
        session=session,
        order_id=o.id,
        city_id=o.city_id,
        district_id=o.district_id,
        preferred_master_id=o.preferred_master_id,
        limit=50,  # отберём топ-50, отправим первому
    )

    # лог заголовок
    header = log_tick_header(o, next_round, cfg.rounds, cfg.sla_seconds, len(cand))
    print(header)
    if cand:
        # топ‑10 в лог
        top = cand[:10]
        ranked = ", ".join(fmt_rank_item({
            "mid": x["mid"],
            "car": x["car"],
            "avg_week": float(x["avg_week"] or 0),
            "rating": float(x["rating"] or 0),
            "rnd": float(x["rnd"] or 0),
        }) for x in top)
        print("ranked=[\n  " + ranked + "\n]")

        first = cand[0]
        ok = await send_offer(session, o.id, int(first["mid"]), next_round, cfg.sla_seconds)
        if ok:
            until = _now() + timedelta(seconds=cfg.sla_seconds)
            print(log_decision_offer(int(first["mid"]), until))
        else:
            print(f"[dist] order={o.id} race_conflict: offer exists for mid={first['mid']}")
    else:
        print(log_escalate(o.id))

# ---------- main loop ----------

async def tick_once() -> None:
    async with SessionLocal() as s:
        cfg = await _load_config(s)
        # 0) истечь SENT
        expired = await expire_sent_offers(s, _now())
        if expired:
            await s.commit()

        # 1) пачка заказов под распределение
        rows = await fetch_orders_batch(s, limit=100)
        # обрабатываем по одному (таски можно распараллелить при необходимости)
        for o in rows:
            await process_one_order(s, cfg, o)
        await s.commit()  # фиксация офферов/назначений

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
