from __future__ import annotations

from datetime import datetime
from typing import Iterable, Optional

from sqlalchemy import select, text

from field_service.bots.admin_bot.services_db import (
    DBOrdersService,
    MasterBrief,
    UTC,
)
from field_service.db import models as m
from field_service.services import distribution_worker as dw


def _normalize_city_filter(city_ids: Optional[Iterable[int]]) -> Optional[tuple[int, ...]]:
    if city_ids is None:
        return None
    return tuple(sorted({int(value) for value in city_ids}))


def apply_manual_candidates_patch(target: type[DBOrdersService]) -> None:
    async def manual_candidates(
        self: DBOrdersService,
        order_id: int,
        *,
        page: int,
        page_size: int,
        city_ids: Optional[Iterable[int]] = None,
    ) -> tuple[list[MasterBrief], bool]:
        page = max(page, 1)
        offset = (page - 1) * page_size
        limit = page_size + 1
        async with self._session_factory() as session:
            city_filter = _normalize_city_filter(city_ids)
            if city_filter is not None and not city_filter:
                return [], False
            allowed_cities = {int(value) for value in city_filter} if city_filter is not None else None
            order_q = await session.execute(
                select(
                    m.orders.city_id,
                    m.orders.district_id,
                    m.orders.category,
                ).where(m.orders.id == order_id)
            )
            order_row = order_q.first()
            if not order_row:
                return [], False
            order_city_id = getattr(order_row, "city_id", None)
            if order_city_id is None:
                return [], False
            order_city_id = int(order_city_id)
            if allowed_cities is not None and order_city_id not in allowed_cities:
                return [], False
            district_id = getattr(order_row, "district_id", None)
            if district_id is None:
                return [], False
            district_id = int(district_id)
            category = getattr(order_row, "category", None)
            skill_code = dw._skill_code_for_category(category)
            if skill_code is None:
                return [], False
            global_limit = await dw._max_active_limit_for(session)
            now = datetime.now(UTC)
            rows = await session.execute(
                text(
                    """
WITH active_cnt AS (
  SELECT assigned_master_id AS mid, COUNT(*) AS cnt
    FROM orders
   WHERE assigned_master_id IS NOT NULL
     AND status IN ('ASSIGNED','EN_ROUTE','WORKING','PAYMENT')
   GROUP BY assigned_master_id
)
avg7 AS (
  SELECT assigned_master_id AS mid, AVG(total_sum)::numeric(10,2) AS avg_check
    FROM orders
   WHERE assigned_master_id IS NOT NULL
     AND status IN ('PAYMENT','CLOSED')
     AND created_at >= NOW() - INTERVAL '7 days'
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
    COALESCE(ac.cnt, 0)      AS active_cnt,
    COALESCE(m.max_active_orders_override, :gmax) AS max_limit,
    COALESCE(a.avg_check, 0) AS avg_week
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
  AND m.is_blocked = FALSE
  AND m.verified = TRUE
  AND m.is_active = TRUE
  AND NOT EXISTS (
    SELECT 1
      FROM offers o
     WHERE o.order_id = :oid
       AND o.master_id = m.id
       AND o.state IN ('SENT','VIEWED','ACCEPTED')
  )
ORDER BY
  CASE WHEN m.is_on_shift = TRUE AND (m.break_until IS NULL OR m.break_until <= :now) THEN 1 ELSE 0 END DESC,
  CASE WHEN m.has_vehicle THEN 1 ELSE 0 END DESC,
  a.avg_check DESC NULLS LAST,
  m.rating DESC NULLS LAST
OFFSET :offset
LIMIT :limit
                    """
                ).bindparams(
                    cid=order_city_id,
                    did=district_id,
                    oid=order_id,
                    skill_code=skill_code,
                    offset=offset,
                    limit=limit,
                    gmax=global_limit,
                    now=now,
                )
            )
            fetched = rows.mappings().all()
        has_next = len(fetched) > page_size
        result_rows = fetched[:page_size]
        briefs: list[MasterBrief] = []
        for mapping in result_rows:
            data = dict(mapping)
            mid = int(data.get("mid"))
            max_limit = int(data.get("max_limit") or global_limit)
            active_cnt = int(data.get("active_cnt") or 0)
            break_until = data.get("break_until")
            on_break = bool(break_until and break_until > now)
            briefs.append(
                MasterBrief(
                    id=mid,
                    full_name=data.get("full_name") or f"РњР°СЃС‚РµСЂ #{mid}",
                    city_id=int(data.get("city_id") or 0),
                    has_car=bool(data.get("has_vehicle")),
                    avg_week_check=float(data.get("avg_week") or 0),
                    rating_avg=float(data.get("rating") or 0),
                    is_on_shift=bool(data.get("is_on_shift")),
                    is_active=bool(data.get("is_active")),
                    verified=bool(data.get("verified")),
                    in_district=True,
                    active_orders=active_cnt,
                    max_active_orders=max_limit,
                    on_break=on_break,
                )
            )
        return briefs, has_next

    target.manual_candidates = manual_candidates
