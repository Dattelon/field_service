from __future__ import annotations

from typing import Iterable, Optional
from types import SimpleNamespace

from sqlalchemy import select

from field_service.bots.admin_bot.services_db import DBOrdersService, MasterBrief
from field_service.db import models as m
from field_service.services.candidates import select_candidates


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
        async with self._session_factory() as session:
            city_filter = _normalize_city_filter(city_ids)
            if city_filter is not None and not city_filter:
                return [], False
            allowed_cities = (
                {int(value) for value in city_filter} if city_filter is not None else None
            )
            order_q = await session.execute(
                select(
                    m.orders.id,
                    m.orders.city_id,
                    m.orders.district_id,
                    m.orders.category,
                ).where(m.orders.id == order_id)
            )
            order_row = order_q.first()
            if not order_row:
                return [], False

            raw_city = getattr(order_row, "city_id", None)
            if raw_city is None:
                return [], False
            try:
                order_city_id = int(raw_city)
            except (TypeError, ValueError):
                return [], False
            if allowed_cities is not None and order_city_id not in allowed_cities:
                return [], False

            raw_district = getattr(order_row, "district_id", None)
            if raw_district is None:
                return [], False
            try:
                district_id = int(raw_district)
            except (TypeError, ValueError):
                return [], False

            order_payload = SimpleNamespace(
                id=order_id,
                city_id=order_city_id,
                district_id=district_id,
                category=getattr(order_row, "category", None),
            )

            candidate_infos = await select_candidates(
                order_payload,
                "manual",
                session=session,
            )

            slice_end = offset + page_size + 1
            page_slice = candidate_infos[offset:slice_end]
            has_next = len(page_slice) > page_size
            page_candidates = page_slice[:page_size]

            briefs: list[MasterBrief] = []
            for candidate in page_candidates:
                briefs.append(
                    MasterBrief(
                        id=candidate.master_id,
                        full_name=candidate.full_name,
                        city_id=candidate.city_id,
                        has_car=candidate.has_car,
                        avg_week_check=candidate.avg_week_check,
                        rating_avg=candidate.rating_avg,
                        is_on_shift=candidate.is_on_shift,
                        is_active=candidate.is_active,
                        verified=candidate.verified,
                        in_district=candidate.in_district,
                        active_orders=candidate.active_orders,
                        max_active_orders=candidate.max_active_orders,
                        on_break=candidate.on_break,
                    )
                )

            return briefs, has_next

    target.manual_candidates = manual_candidates
