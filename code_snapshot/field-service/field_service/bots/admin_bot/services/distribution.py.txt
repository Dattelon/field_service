"""Distribution service: auto-assignment of orders to masters."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional, Sequence

from sqlalchemy import func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from field_service.db import models as m
from field_service.db.session import SessionLocal
from field_service.services import distribution_scheduler as dw
from field_service.services import distribution_worker as legacy_dw
from field_service.services import live_log
from field_service.services.candidates import select_candidates

from ..core.dto import MasterBrief, OrderType


# Common utilities from _common
from ._common import (
    UTC,
    QUEUE_STATUSES,
    ACTIVE_ORDER_STATUSES,
    AVG_CHECK_STATUSES,
    STREET_DUPLICATE_THRESHOLD,
    STREET_MIN_SCORE,
    PAYMENT_METHOD_LABELS,
    OWNER_PAY_SETTING_FIELDS,
    _is_column_missing_error,
    _normalize_street_name,
    _format_datetime_local,
    _format_created_at,
    _zone_storage_value,
    _workday_window,
    _load_staff_access,
    _visible_city_ids_for_staff,
    _staff_can_access_city,
    _load_staff_city_map,
    _collect_code_cities,
    _prepare_setting_value,
    _raw_order_type,
    _map_staff_role,
    _map_staff_role_to_db,
    _sorted_city_tuple,
    _order_type_from_db,
    _map_order_type_to_db,
    _attachment_type_from_string,
    _generate_staff_code,
    _push_dist_log,
    _coerce_order_status,
)

_WORKER_BASE: dict[str, Callable[..., Any] | None] = {
    name: getattr(legacy_dw, name, None)
    for name in ("_load_config", "current_round", "candidate_rows", "send_offer")
}


@dataclass
class AutoAssignResult:
    message: str
    master_id: Optional[int] = None
    deadline: Optional[datetime] = None
    code: str = "ok"




def _push_dist_log(message: str, *, level: str = "INFO") -> None:
    try:
        live_log.push("dist", message, level=level)
    except Exception:
        pass
    print(message)


def _coerce_order_status(value: Any) -> m.OrderStatus:
    if isinstance(value, m.OrderStatus):
        return value
    if value is None:
        return m.OrderStatus.SEARCHING
    try:
        return m.OrderStatus(str(value))
    except ValueError:
        return m.OrderStatus.SEARCHING


def _worker_override(name: str) -> Callable[..., Any] | None:
    original = _WORKER_BASE.get(name)
    if original is None:
        return None
    current = getattr(legacy_dw, name, None)
    if current is None or current is original:
        return None
    return current


async def _load_config_for_session(session: AsyncSession):
    loader = _worker_override("_load_config")
    if loader is not None:
        return await loader(session)
    return await dw._load_config()


class DBDistributionService:
    def __init__(self, session_factory=SessionLocal) -> None:
        self._session_factory = session_factory


    async def assign_auto(
        self,
        order_id: int,
        by_staff_id: int,
    ) -> tuple[bool, AutoAssignResult]:
        async with self._session_factory() as session:
            async with session.begin():
                order_q = await session.execute(
                    select(
                        m.orders.id,
                        m.orders.city_id,
                        m.orders.district_id,
                        m.orders.preferred_master_id,
                        m.orders.category,
                        m.orders.status,
                        m.orders.type.label("order_type"),
                        m.orders.dist_escalated_logist_at,
                        m.orders.dist_escalated_admin_at,
                    )
                    .where(m.orders.id == order_id)
                    .with_for_update()
                )
                data = order_q.first()
                if not data:
                    return False, AutoAssignResult(
                        "  ",
                        code="not_found",
                    )

                staff = await _load_staff_access(session, by_staff_id or None)
                if not _staff_can_access_city(staff, data.city_id):
                    return False, AutoAssignResult(
                        "   ",
                        code="forbidden",
                    )

                status_enum = _coerce_order_status(getattr(data, "status", None))
                logistic_mark = getattr(data, "dist_escalated_logist_at", None)

                # 🔧 BUGFIX: Переводим DEFERRED → SEARCHING перед распределением
                if status_enum == m.OrderStatus.DEFERRED:
                    await session.execute(
                        update(m.orders)
                        .where(m.orders.id == order_id)
                        .values(status=m.OrderStatus.SEARCHING)
                    )
                    await session.execute(
                        insert(m.order_status_history).values(
                            order_id=order_id,
                            from_status=m.OrderStatus.DEFERRED,
                            to_status=m.OrderStatus.SEARCHING,
                            changed_by_staff_id=by_staff_id,
                            actor_type=m.ActorType.ADMIN,
                            reason="Принудительный запуск распределения из админ-бота",
                        )
                    )
                    status_enum = m.OrderStatus.SEARCHING
                    _push_dist_log(f"[dist] order={order_id} DEFERRED→SEARCHING (forced by staff #{by_staff_id})", level="INFO")

                if data.district_id is None:
                    if logistic_mark is None:
                        await session.execute(
                            update(m.orders)
                            .where(m.orders.id == order_id)
                            .values(
                                dist_escalated_logist_at=func.now(),
                                dist_escalated_admin_at=None,
                            )
                        )
                        await session.execute(
                            insert(m.order_status_history).values(
                                order_id=order_id,
                                from_status=status_enum,
                                to_status=status_enum,
                                actor_type=m.ActorType.AUTO_DISTRIBUTION,
                                reason=f"{dw.ESC_REASON_LOGIST}:no_district",
                            )
                        )
                    message = dw.log_skip_no_district(order_id)
                    _push_dist_log(message, level="WARN")
                    return False, AutoAssignResult(
                        "  :   .   .",
                        code="no_district",
                    )

                category = getattr(data, "category", None)
                skill_code = dw._skill_code_for_category(category)
                if skill_code is None:
                    message = dw.log_skip_no_category(order_id, category)
                    _push_dist_log(message, level="WARN")
                    return False, AutoAssignResult(
                        "     ",
                        code="no_category",
                    )

                order_type = _order_type_from_db(getattr(data, "order_type", None))
                is_guarantee = (
                    status_enum is m.OrderStatus.GUARANTEE
                    or order_type is OrderType.GUARANTEE
                )

                cfg = await _load_config_for_session(session)
                patched_round = _worker_override("current_round")
                patched_candidate_rows = _worker_override("candidate_rows")
                patched_send_offer = _worker_override("send_offer")
                if patched_round and patched_send_offer:
                    round_index = await patched_round(session, order_id)
                    candidate_rows: list[dict] = []
                    if patched_candidate_rows:
                        candidate_rows = await patched_candidate_rows(
                            order=data,
                            session=session,
                            limit=50,
                        )
                    if not candidate_rows:
                        _push_dist_log(
                            f"[dist] order={order_id} decision=no_candidates",
                            level="WARN",
                        )
                        return False, AutoAssignResult(
                            "no_candidates",
                            code="no_candidates",
                        )
                    first_candidate = candidate_rows[0] or {}
                    try:
                        master_id = int(first_candidate.get("mid"))
                    except (TypeError, ValueError):
                        master_id = 0
                    if master_id <= 0:
                        _push_dist_log(
                            f"[dist] order={order_id} decision=no_candidates",
                            level="WARN",
                        )
                        return False, AutoAssignResult(
                            "no_candidates",
                            code="no_candidates",
                        )
                    sent = await patched_send_offer(
                        session,
                        order_id,
                        master_id,
                        round_index + 1,
                        cfg.sla_seconds,
                    )
                    if not sent:
                        _push_dist_log(
                            f"[dist] order={order_id} decision=offer_conflict master={master_id}",
                            level="WARN",
                        )
                        return False, AutoAssignResult(
                            "offer_conflict",
                            code="offer_conflict",
                        )
                    _push_dist_log(
                        f"[dist] order={order_id} decision=offer master={master_id}",
                        level="INFO",
                    )
                    return True, AutoAssignResult(
                        "offer_sent",
                        master_id=master_id,
                        deadline=datetime.now(UTC) + timedelta(seconds=cfg.sla_seconds),
                        code="offer_sent",
                    )

                current_round = await dw.current_round(session, order_id)
                if current_round >= cfg.rounds:
                    return False, AutoAssignResult(
                        "   ",
                        code="rounds_exhausted",
                    )

                candidate_infos = await select_candidates(
                    data,
                    "auto",
                    session=session,
                    limit=50,
                    log_hook=lambda message: _push_dist_log(message, level="INFO"),
                )

                candidates = [
                    {
                        "mid": candidate.master_id,
                        "car": candidate.has_car,
                        "avg_week": candidate.avg_week_check,
                        "rating": candidate.rating_avg,
                        "rnd": candidate.random_rank,
                        "shift": candidate.is_on_shift,
                    }
                    for candidate in candidate_infos
                ]

                header = dw.log_tick_header(
                    data,
                    current_round + 1,
                    cfg.rounds,
                    cfg.sla_seconds,
                    len(candidates),
                )
                _push_dist_log(header)

                if is_guarantee and data.preferred_master_id and candidates:
                    try:
                        pref_id = int(data.preferred_master_id)
                    except (TypeError, ValueError):
                        pref_id = None
                    if candidates and pref_id is not None and int(candidates[0]["mid"]) == pref_id:
                        _push_dist_log(dw.log_force_first(pref_id))

                if candidates:
                    top_limit = min(len(candidates), 10)
                    ranked_items = ", ".join(
                        dw.fmt_rank_item(
                            {
                                "mid": row.get("mid"),
                                "car": row.get("car"),
                                "avg_week": float(row.get("avg_week") or 0),
                                "rating": float(row.get("rating") or 0),
                                "rnd": float(row.get("rnd") or 0),
                                "shift": row.get("shift", True),
                            }
                        )
                        for row in candidates[:top_limit]
                    )
                    if ranked_items:
                        _push_dist_log("ranked=[\n  " + ranked_items + "\n]")

                    master_id = int(candidates[0]["mid"])
                    next_round = current_round + 1
                    sent = await dw._send_offer(
                        session,
                        oid=order_id,
                        mid=master_id,
                        round_number=next_round,
                        sla_seconds=cfg.sla_seconds,
                    )
                    if not sent:
                        conflict = (
                            f"[dist] order={order_id} race_conflict: offer exists for mid={master_id}"
                        )
                        _push_dist_log(conflict, level="WARN")
                        return False, AutoAssignResult(
                            "    ",
                            code="offer_conflict",
                        )

                    # Отправить push-уведомление мастеру о новом оффере
                    try:
                        from field_service.services.push_notifications import notify_master, NotificationEvent
                        order_data = await dw._get_order_notification_data(session, order_id)
                        if order_data:
                            await notify_master(
                                session,
                                master_id=master_id,
                                event=NotificationEvent.NEW_OFFER,
                                **order_data,
                            )
                            _push_dist_log(f"[dist] Push notification queued for master#{master_id} about order#{order_id}")
                    except Exception as e:
                        _push_dist_log(f"[dist] Failed to queue notification for master#{master_id}: {e}", level="ERROR")

                    await session.execute(
                        update(m.orders)
                        .where(m.orders.id == order_id)
                        .values(
                            dist_escalated_logist_at=None,
                            dist_escalated_admin_at=None,
                        )
                    )

                    deadline = datetime.now(timezone.utc) + timedelta(seconds=cfg.sla_seconds)
                    _push_dist_log(dw.log_decision_offer(master_id, deadline))
                    
                    # CR-2025-10-03-015: Форматируем дедлайн красиво
                    deadline_formatted = _format_datetime_local(deadline) or deadline.strftime("%d.%m %H:%M")
                    
                    return True, AutoAssignResult(
                        message=(
                            f"✅ Предложение отправлено\n\n"
                            f"👤 Мастер #{master_id}\n"
                            f"⏰ Срок: {deadline_formatted}"
                        ),
                        master_id=master_id,
                        deadline=deadline,
                        code="offer_sent",
                    )

                if logistic_mark is None:
                    await session.execute(
                        update(m.orders)
                        .where(m.orders.id == order_id)
                        .values(
                            dist_escalated_logist_at=func.now(),
                            dist_escalated_admin_at=None,
                        )
                    )
                    await session.execute(
                        insert(m.order_status_history).values(
                            order_id=order_id,
                            from_status=status_enum,
                            to_status=status_enum,
                            actor_type=m.ActorType.AUTO_DISTRIBUTION,
                            reason=f"{dw.ESC_REASON_LOGIST}:no_candidates",
                        )
                    )

                _push_dist_log(dw.log_escalate(order_id), level="WARN")
                return False, AutoAssignResult(
                    "   ",
                    code="no_candidates",
                )



    async def send_manual_offer(
        self,
        order_id: int,
        master_id: int,
        by_staff_id: int,
    ) -> tuple[bool, str]:
        async with self._session_factory() as session:
            async with session.begin():
                order_row = await session.execute(
                    select(
                        m.orders.id,
                        m.orders.city_id,
                        m.orders.district_id,
                        m.orders.category,
                        m.orders.status,
                        m.orders.type.label("order_type"),
                    )
                    .where(m.orders.id == order_id)
                    .with_for_update()
                )
                order = order_row.first()
                if not order:
                    return False, "  "

                staff = await _load_staff_access(session, by_staff_id or None)
                if not _staff_can_access_city(staff, order.city_id):
                    return False, "   "

                status = getattr(order, "status", None)
                # 🔧 BUGFIX: Разрешаем ручное назначение для DEFERRED
                allowed_statuses = {
                    m.OrderStatus.SEARCHING,
                    m.OrderStatus.GUARANTEE,
                    m.OrderStatus.DEFERRED,
                }
                status_enum = (
                    status if isinstance(status, m.OrderStatus) else m.OrderStatus(str(status))
                    if status is not None
                    else m.OrderStatus.SEARCHING
                )
                if status_enum not in allowed_statuses:
                    return False, "   "

                # 🔧 BUGFIX: Переводим DEFERRED → SEARCHING при ручном назначении
                if status_enum == m.OrderStatus.DEFERRED:
                    await session.execute(
                        update(m.orders)
                        .where(m.orders.id == order_id)
                        .values(status=m.OrderStatus.SEARCHING)
                    )
                    await session.execute(
                        insert(m.order_status_history).values(
                            order_id=order_id,
                            from_status=m.OrderStatus.DEFERRED,
                            to_status=m.OrderStatus.SEARCHING,
                            changed_by_staff_id=by_staff_id,
                            actor_type=m.ActorType.ADMIN,
                            reason="Ручное назначение из админ-бота",
                        )
                    )
                    status_enum = m.OrderStatus.SEARCHING

                category = getattr(order, "category", None)
                skill_code = dw._skill_code_for_category(category)
                if skill_code is None:
                    return False, "   "

                master_row = await session.execute(
                    select(
                        m.masters.id,
                        m.masters.city_id,
                        m.masters.is_active,
                        m.masters.is_blocked,
                        m.masters.verified,
                    ).where(m.masters.id == master_id)
                )
                master = master_row.first()
                if not master:
                    return False, "  "
                if master.city_id != order.city_id:
                    return False, "    "
                if not master.is_active or master.is_blocked or not master.verified:
                    return False, " "

                if order.district_id:
                    district_row = await session.execute(
                        select(m.master_districts)
                        .where(
                            (m.master_districts.master_id == master_id)
                            & (m.master_districts.district_id == order.district_id)
                        )
                        .limit(1)
                    )
                    if district_row.first() is None:
                        return False, "   "

                skill_row = await session.execute(
                    select(m.master_skills.master_id)
                    .join(m.skills, m.master_skills.skill_id == m.skills.id)
                    .where(
                        (m.master_skills.master_id == master_id)
                        & (m.skills.code == skill_code)
                        & (m.skills.is_active == True)
                    )
                    .limit(1)
                )
                if skill_row.first() is None:
                    return False, "Мастер не владеет требуемым навыком"

                existing_offer = await session.execute(
                    select(m.offers.id)
                    .where(
                        (m.offers.order_id == order_id)
                        & (m.offers.master_id == master_id)
                        & (
                            m.offers.state.in_(
                                [
                                    m.OfferState.SENT,
                                    m.OfferState.VIEWED,
                                    m.OfferState.ACCEPTED,
                                ]
                            )
                        )
                    )
                    .limit(1)
                )
                if existing_offer.first() is not None:
                    return False, "    "

                cfg = await _load_config_for_session(session)
                current_round = await dw.current_round(session, order_id)
                round_number = (current_round or 0) + 1
                send_offer_fn = getattr(dw, "_send_offer", None)
                if send_offer_fn is not None:
                    sent = await send_offer_fn(
                        session,
                        oid=order_id,
                        mid=master_id,
                        round_number=round_number,
                        sla_seconds=cfg.sla_seconds,
                    )
                else:
                    legacy_send = getattr(dw, "send_offer", None)
                    if legacy_send is None:
                        return False, "   "
                    sent = await legacy_send(
                        session,
                        order_id,
                        master_id,
                        round_number,
                        cfg.sla_seconds,
                    )
                if not sent:
                    return False, "   "

                # Отправить push-уведомление мастеру о новом оффере
                try:
                    from field_service.services.push_notifications import notify_master, NotificationEvent
                    order_data = await dw._get_order_notification_data(session, order_id)
                    if order_data:
                        await notify_master(
                            session,
                            master_id=master_id,
                            event=NotificationEvent.NEW_OFFER,
                            **order_data,
                        )
                        _push_dist_log(f"[dist] Push notification queued for master#{master_id} about order#{order_id}")
                except Exception as e:
                    _push_dist_log(f"[dist] Failed to queue notification for master#{master_id}: {e}", level="ERROR")

                await session.execute(
                    update(m.orders)
                    .where(m.orders.id == order_id)
                    .values(
                        dist_escalated_logist_at=None,
                        dist_escalated_admin_at=None,
                    )
                )
        return True, " "





