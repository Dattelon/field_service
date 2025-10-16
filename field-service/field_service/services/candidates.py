from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Sequence

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from field_service.db import models as m
from field_service.db.session import SessionLocal
from field_service.services import distribution_scheduler as ds
from field_service.services.skills_map import get_skill_code
from field_service.infra.structured_logging import log_candidate_rejection

UTC = timezone.utc
logger = logging.getLogger(__name__)

_ACTIVE_ORDER_STATUSES: Sequence[str] = tuple(
    status.value
    for status in (
        m.OrderStatus.ASSIGNED,
        m.OrderStatus.EN_ROUTE,
        m.OrderStatus.WORKING,
        m.OrderStatus.PAYMENT,
    )
)

_ACTIVE_OFFER_STATES: Sequence[str] = tuple(
    state.value
    for state in (
        m.OfferState.SENT,
        m.OfferState.VIEWED,
        m.OfferState.ACCEPTED,
    )
)


@dataclass(slots=True)
class CandidateInfo:
    master_id: int
    full_name: str
    city_id: int
    has_car: bool
    avg_week_check: float
    rating_avg: float
    is_on_shift: bool
    on_break: bool
    is_active: bool
    verified: bool
    in_district: bool
    active_orders: int
    max_active_orders: int
    has_skill: bool
    has_open_offer: bool
    random_rank: float


_REASON_LABELS: dict[str, str] = {
    "city": "  ",
    "district": "  ",
    "verified": "  ",
    "active": "  ",
    "shift": "  ",
    "break": "  ",
    "skill": "  ",
    "limit": "   ",
    "offer": "   ",
}


def _order_attr(order: Any, name: str, default: Any = None) -> Any:
    if isinstance(order, dict):
        return order.get(name, default)
    return getattr(order, name, default)


def _log_rejection(
    order_id: int,
    candidate_id: int,
    mode: str,
    reasons: Iterable[str],
    hook: Any | None,
    master_details: dict[str, Any] | None = None,
) -> None:
    if not reasons:
        return
    
    reasons_list = list(reasons)
    labels = [_REASON_LABELS.get(reason, reason) for reason in reasons_list]
    reason_text = ", ".join(labels)
    message = (
        f"[candidates] order={order_id} master={candidate_id} mode={mode} : {reason_text}"
    )
    logger.info(message)
    
    # ✅ STEP 4.2: Structured logging - candidate rejection
    log_candidate_rejection(
        order_id=order_id,
        master_id=candidate_id,
        mode=mode,
        rejection_reasons=reasons_list,
        master_details=master_details or {},
    )
    
    if hook is not None:
        try:
            hook(message)
        except Exception:  # pragma: no cover - log hook should not break selection
            logger.exception("candidate rejection hook failed")


async def select_candidates(
    order: Any,
    mode: str,
    *,
    session: AsyncSession | None = None,
    limit: int | None = None,
    log_hook: Any | None = None,
) -> list[CandidateInfo]:
    """Return filtered candidates for an order, logging skipped masters."""

    raw_id = _order_attr(order, "id")
    try:
        order_id = int(raw_id)
    except (TypeError, ValueError):
        logger.info("[candidates]     : %r", raw_id)
        return []

    city_id = _order_attr(order, "city_id")
    district_id = _order_attr(order, "district_id")
    try:
        city_id_int = int(city_id)
    except (TypeError, ValueError):
        logger.info("[candidates] order=%s:  -  ", order_id)
        return []
    city_id = city_id_int

    skill_code = get_skill_code(_order_attr(order, "category"))
    if skill_code is None:
        logger.info(
            "[candidates] order=%s:  -    ", order_id
        )
        return []

    owns_session = session is None
    if owns_session:
        async with SessionLocal() as new_session:
            return await select_candidates(
                order,
                mode,
                session=new_session,
                limit=limit,
                log_hook=log_hook,
            )

    assert session is not None

    global_limit = await ds._max_active_limit_for(session)
    now = datetime.now(UTC)

    active_statuses_sql = ", ".join(f"'{status}'" for status in _ACTIVE_ORDER_STATUSES)
    offer_states_sql = ", ".join(f"'{state}'" for state in _ACTIVE_OFFER_STATES)

    # Dialect-specific bits for AVG and date arithmetic
    dialect_name = getattr(getattr(session, "bind", None), "dialect", None)
    dialect_name = getattr(dialect_name, "name", "") or ""
    is_sqlite = "sqlite" in dialect_name

    avg_expr = (
        "AVG(total_sum) AS avg_check" if is_sqlite else "AVG(total_sum)::numeric(10,2) AS avg_check"
    )
    date_7days_ago = (
        "DATETIME('now', '-7 days')" if is_sqlite else "NOW() - INTERVAL '7 days'"
    )

    sql = text(
        f"""
WITH active_cnt AS (
    SELECT assigned_master_id AS mid, COUNT(*) AS cnt
      FROM orders
     WHERE assigned_master_id IS NOT NULL
        AND status IN ({active_statuses_sql})
      GROUP BY assigned_master_id
),
avg7 AS (
    SELECT assigned_master_id AS mid, {avg_expr}
      FROM orders
     WHERE assigned_master_id IS NOT NULL
       AND status IN ('PAYMENT','CLOSED')
       AND created_at >= {date_7days_ago}
      GROUP BY assigned_master_id
)
SELECT
    m.id AS mid,
    m.full_name,
    m.city_id,
    m.has_vehicle,
    m.rating,
    m.is_on_shift,
    m.break_until,
    m.is_active,
    m.verified,
    COALESCE(ac.cnt, 0) AS active_cnt,
    COALESCE(m.max_active_orders_override, :gmax) AS max_limit,
    COALESCE(a.avg_check, 0) AS avg_week,
    ((:did IS NULL) OR EXISTS (
        SELECT 1 FROM master_districts md
         WHERE md.master_id = m.id AND md.district_id = :did
    )) AS in_district,
    EXISTS (
        SELECT 1 FROM master_skills ms
         JOIN skills s ON s.id = ms.skill_id
        WHERE ms.master_id = m.id
          AND s.is_active = TRUE
          AND s.code = :skill_code
    ) AS skill_match,
    EXISTS (
        SELECT 1 FROM offers o
         WHERE o.order_id = :oid
           AND o.master_id = m.id
               AND o.state IN ({offer_states_sql})
       ) AS has_open_offer
FROM masters m
LEFT JOIN active_cnt ac ON ac.mid = m.id
LEFT JOIN avg7 a ON a.mid = m.id
WHERE m.city_id = :cid
  AND m.is_blocked = FALSE
ORDER BY m.id
        """
    )

    try:
        district_bind = int(district_id) if district_id is not None else None
    except (TypeError, ValueError):
        district_bind = None

    rows = await session.execute(
        sql.bindparams(
            cid=int(city_id),
            did=district_bind,
            oid=order_id,
            skill_code=skill_code,
            gmax=global_limit,
        )
    )

    candidates: list[CandidateInfo] = []
    for mapping in rows.mappings():
        master_id = int(mapping["mid"])
        reasons: list[str] = []

        if int(mapping["city_id"] or 0) != int(city_id):
            reasons.append("city")

        in_district = bool(mapping.get("in_district"))
        if not in_district:
            reasons.append("district")

        has_skill = bool(mapping.get("skill_match"))
        if not has_skill:
            reasons.append("skill")

        verified = bool(mapping.get("verified"))
        if not verified:
            reasons.append("verified")

        is_active = bool(mapping.get("is_active"))
        if not is_active:
            reasons.append("active")

        is_on_shift = bool(mapping.get("is_on_shift"))
        if not is_on_shift:
            reasons.append("shift")

        break_until = mapping.get("break_until")
        on_break = bool(break_until and break_until > now)
        if on_break:
            reasons.append("break")

        active_orders = int(mapping.get("active_cnt") or 0)
        max_limit = int(mapping.get("max_limit") or global_limit or 0)
        if max_limit > 0 and active_orders >= max_limit:
            reasons.append("limit")

        has_open_offer = bool(mapping.get("has_open_offer"))
        if has_open_offer:
            reasons.append("offer")

        if reasons:
            # ✅ STEP 4.2: Pass master details to structured logging
            master_details = {
                "full_name": mapping.get("full_name") or f"Master #{master_id}",
                "city_id": int(mapping["city_id"] or 0),
                "has_vehicle": bool(mapping.get("has_vehicle")),
                "avg_week_check": float(mapping.get("avg_week") or 0),
                "rating": float(mapping.get("rating") or 0),
                "is_on_shift": is_on_shift,
                "on_break": on_break,
                "is_active": is_active,
                "verified": verified,
                "in_district": in_district,
                "active_orders": active_orders,
                "max_active_orders": max_limit,
                "has_skill": has_skill,
                "has_open_offer": has_open_offer,
            }
            _log_rejection(order_id, master_id, mode, reasons, log_hook, master_details)
            continue

        candidates.append(
            CandidateInfo(
                master_id=master_id,
                full_name=mapping.get("full_name") or f" #{master_id}",
                city_id=int(mapping["city_id"] or 0),
                has_car=bool(mapping.get("has_vehicle")),
                avg_week_check=float(mapping.get("avg_week") or 0),
                rating_avg=float(mapping.get("rating") or 0),
                is_on_shift=is_on_shift,
                on_break=on_break,
                is_active=is_active,
                verified=verified,
                in_district=in_district,
                active_orders=active_orders,
                max_active_orders=max_limit,
                has_skill=has_skill,
                has_open_offer=has_open_offer,
                random_rank=random.random(),
            )
        )

    candidates.sort(
        key=lambda item: (
            -int(item.has_car),
            -item.avg_week_check,
            -item.rating_avg,
            item.random_rank,
        )
    )

    if limit is not None:
        return candidates[:limit]
    return candidates
