"""Masters service: master management, profiles, documents."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Iterable, Mapping, Optional, Sequence
from types import SimpleNamespace

from sqlalchemy import delete, func, insert, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from field_service.db import models as m
from field_service.db.session import SessionLocal
from field_service.services._session_utils import maybe_managed_session
from field_service.services import live_log
from field_service.services.candidates import select_candidates

from ..core.dto import (
    MasterBrief, MasterListItem, MasterDocument, MasterDetail,
    OrderCategory,
)

logger = logging.getLogger(__name__)


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


class DBMastersService:
    def __init__(self, session_factory=SessionLocal) -> None:
        self._session_factory = session_factory

    async def list_active_skills(self) -> list[dict[str, object]]:
        async with self._session_factory() as session:
            rows = await s.execute(
                select(m.skills.id, m.skills.code, m.skills.name)
                .where(m.skills.is_active.is_(True))
                .order_by(m.skills.name.asc())
            )
            skills: list[dict[str, object]] = []
            for skill_id, code, name in rows.all():
                label = str(name or code or skill_id)
                skills.append(
                    {
                        "id": int(skill_id),
                        "code": str(code or skill_id),
                        "name": label,
                    }
                )
            return skills

    async def _get_default_master_limit(self, session: AsyncSession) -> int:
        value = await s.scalar(
            select(m.settings.value).where(m.settings.key == "max_active_orders")
        )
        try:
            parsed = int(value)
            if parsed > 0:
                return parsed
        except (TypeError, ValueError):
            pass
        return 5

    async def _log_admin_action(
        self,
        session: AsyncSession,
        *,
        admin_id: int,
        master_id: int,
        action: str,
        payload: Mapping[str, Any] | None = None,
    ) -> None:
        try:
            payload_json = dict(payload or {})
        except Exception:
            payload_json = {"raw": str(payload)}
        await s.execute(
            insert(m.admin_audit_log).values(
                admin_id=admin_id or None,
                master_id=master_id,
                action=action,
                payload_json=payload_json,
            )
        )

    async def get_master_referral_stats(self, master_id: int) -> dict[str, int | Decimal]:
        """Return referral statistics for a given master."""
        async with self._session_factory() as session:
            invited_stmt = (
                select(func.count())
                .select_from(m.masters)
                .where(m.masters.referred_by_master_id == master_id)
            )
            invited_total = int((await s.execute(invited_stmt)).scalar() or 0)

            pending_stmt = (
                select(func.count())
                .select_from(m.masters)
                .where(
                    m.masters.referred_by_master_id == master_id,
                    m.masters.verified.is_(False),
                )
            )
            invited_pending = int((await s.execute(pending_stmt)).scalar() or 0)

            rewards_stmt = (
                select(
                    func.count(),
                    func.sum(m.referral_rewards.amount),
                )
                .select_from(m.referral_rewards)
                .where(
                    m.referral_rewards.referrer_id == master_id,
                    m.referral_rewards.status != m.ReferralRewardStatus.CANCELED,
                )
            )
            rewards_row = (await s.execute(rewards_stmt)).first()
            rewards_count = int((rewards_row[0] if rewards_row else 0) or 0)
            amount_raw = rewards_row[1] if rewards_row else None
            rewards_amount = (
                amount_raw if isinstance(amount_raw, Decimal)
                else Decimal(str(amount_raw)) if amount_raw is not None
                else Decimal(0)
            )

            return {
                "invited_total": invited_total,
                "invited_pending": invited_pending,
                "rewards_count": rewards_count,
                "rewards_amount": rewards_amount,
            }

    async def list_masters(
        self,
        group: str,
        *,
        city_ids: Optional[Iterable[int]],
        category: Optional[str],
        page: int,
        page_size: int,
    ) -> tuple[list[MasterListItem], bool]:
        group_key = (group or "ok").lower()
        filters: list[Any] = [m.masters.is_deleted.is_(False)]
        if city_ids is not None:
            ids = [int(cid) for cid in city_ids]
            if not ids:
                return [], False
            filters.append(m.masters.city_id.in_(ids))

        if group_key in {"mod", "pending"}:
            filters.append(m.masters.verified.is_(False))
        elif group_key in {"blk", "blocked"}:
            filters.append(m.masters.is_active.is_(False))
        else:
            filters.append(m.masters.verified.is_(True))
            if group_key in {"ok", "approved"}:
                filters.append(m.masters.is_active.is_(True))

        category_value = (category or "").strip()
        if category_value and category_value.lower() != "all":
            skill_query = (
                select(m.master_skills.master_id)
                .join(m.skills, m.skills.id == m.master_skills.skill_id)
                .where(
                    m.master_skills.master_id == m.masters.id,
                    m.skills.is_active.is_(True),
                )
            )
            if category_value.isdigit():
                skill_query = skill_query.where(
                    m.master_skills.skill_id == int(category_value)
                )
            else:
                skill_query = skill_query.where(
                    func.lower(m.skills.code) == category_value.lower()
                )
            filters.append(skill_query.exists())

        offset = max(page - 1, 0) * page_size
        async with self._session_factory() as session:
            default_limit = await self._get_default_master_limit(session)
            active_orders_subq = (
                select(
                    m.orders.assigned_master_id.label("master_id"),
                    func.count(m.orders.id).label("cnt"),
                )
                .where(m.orders.status.in_(ACTIVE_ORDER_STATUSES))
                .group_by(m.orders.assigned_master_id)
                .subquery()
            )
            avg_check_subq = (
                select(
                    m.orders.assigned_master_id.label("master_id"),
                    func.avg(m.orders.total_sum).label("avg_check"),
                )
                .where(
                    m.orders.status.in_(AVG_CHECK_STATUSES),
                    m.orders.assigned_master_id.is_not(None),
                )
                .group_by(m.orders.assigned_master_id)
                .subquery()
            )
            skills_subq = (
                select(
                    m.master_skills.master_id.label("master_id"),
                    func.array_agg(func.distinct(m.skills.name)).label("skills"),
                )
                .join(m.skills, m.skills.id == m.master_skills.skill_id)
                .where(m.skills.is_active.is_(True))
                .group_by(m.master_skills.master_id)
                .subquery()
            )

            stmt = (
                select(
                    m.masters.id,
                    m.masters.full_name,
                    m.cities.name.label("city_name"),
                    m.masters.rating,
                    m.masters.has_vehicle,
                    m.masters.is_on_shift,
                    m.masters.shift_status,
                    m.masters.break_until,
                    m.masters.verified,
                    m.masters.is_active,
                    m.masters.is_deleted,
                    m.masters.max_active_orders_override,
                    active_orders_subq.c.cnt,
                    avg_check_subq.c.avg_check,
                    skills_subq.c.skills,
                )
                .select_from(m.masters)
                .join(m.cities, m.masters.city_id == m.cities.id, isouter=True)
                .join(
                    active_orders_subq,
                    active_orders_subq.c.master_id == m.masters.id,
                    isouter=True,
                )
                .join(
                    avg_check_subq,
                    avg_check_subq.c.master_id == m.masters.id,
                    isouter=True,
                )
                .join(
                    skills_subq,
                    skills_subq.c.master_id == m.masters.id,
                    isouter=True,
                )
                .where(*filters)
                .order_by(m.masters.full_name.asc())
                .offset(offset)
                .limit(page_size + 1)
            )
            rows = (await s.execute(stmt)).all()

        now_utc = datetime.now(UTC)
        items: list[MasterListItem] = []
        for row in rows[:page_size]:
            shift_status_value = (
                row.shift_status.value
                if hasattr(row.shift_status, "value")
                else str(row.shift_status or "SHIFT_OFF")
            )
            break_until = getattr(row, "break_until", None)
            on_break = False
            if break_until is not None:
                if break_until.tzinfo is None:
                    break_until = break_until.replace(tzinfo=UTC)
                on_break = break_until > now_utc
            if not on_break and shift_status_value.upper() == m.ShiftStatus.BREAK.value:
                on_break = True

            max_limit = row.max_active_orders_override
            if max_limit is None or int(max_limit) <= 0:
                max_limit = default_limit

            avg_value = None
            if row.avg_check is not None:
                try:
                    avg_value = Decimal(row.avg_check)
                except (TypeError, InvalidOperation):
                    avg_value = Decimal(str(row.avg_check))

            skills = tuple(row.skills or ())
            items.append(
                MasterListItem(
                    id=int(row.id),
                    full_name=row.full_name or f"#{row.id}",
                    city_name=row.city_name,
                    skills=skills,
                    rating=float(row.rating or 0),
                    has_vehicle=bool(row.has_vehicle),
                    is_on_shift=bool(row.is_on_shift),
                    shift_status=shift_status_value,
                    on_break=on_break,
                    verified=bool(row.verified),
                    is_active=bool(row.is_active),
                    is_deleted=bool(row.is_deleted),
                    active_orders=int(row.cnt or 0),
                    max_active_orders=int(max_limit) if max_limit is not None else None,
                    avg_check=avg_value,
                )
            )

        has_next = len(rows) > page_size
        return items, has_next

    async def list_wait_pay_recipients(self) -> list[WaitPayRecipient]:
        async with self._session_factory() as session:
            rows = await s.execute(
                select(
                    m.masters.id,
                    m.masters.tg_user_id,
                    m.masters.full_name,
                )
                .join(m.commissions, m.commissions.master_id == m.masters.id)
                .where(m.commissions.status == m.CommissionStatus.WAIT_PAY)
                .group_by(m.masters.id, m.masters.tg_user_id, m.masters.full_name)
                .order_by(m.masters.id)
            )
            recipients: list[WaitPayRecipient] = []
            for master_id, tg_user_id, full_name in rows.all():
                if tg_user_id is None:
                    continue
                recipients.append(
                    WaitPayRecipient(
                        master_id=int(master_id),
                        tg_user_id=int(tg_user_id),
                        full_name=full_name or f'Master {master_id}',
                    )
                )
        return recipients

    async def get_master_detail(self, master_id: int) -> Optional[MasterDetail]:
        async with self._session_factory() as session:
            default_limit = await self._get_default_master_limit(session)
            row = await s.execute(
                select(m.masters, m.cities.name.label("city_name"))
                .join(m.cities, m.masters.city_id == m.cities.id, isouter=True)
                .where(m.masters.id == master_id)
            )
            result = row.first()
            if not result:
                return None
            master: m.masters = result.masters
            city_name = result.city_name

            active_orders = await s.scalar(
                select(func.count(m.orders.id)).where(
                    (m.orders.assigned_master_id == master.id)
                    & (m.orders.status.in_(ACTIVE_ORDER_STATUSES))
                )
            ) or 0

            avg_check_value = await s.scalar(
                select(func.avg(m.orders.total_sum)).where(
                    (m.orders.assigned_master_id == master.id)
                    & (m.orders.status.in_(AVG_CHECK_STATUSES))
                )
            )
            if avg_check_value is not None:
                try:
                    avg_check = Decimal(avg_check_value)
                except (TypeError, InvalidOperation):
                    avg_check = Decimal(str(avg_check_value))
            else:
                avg_check = None

            has_orders = bool(
                await s.scalar(
                    select(m.orders.id)
                    .where(m.orders.assigned_master_id == master.id)
                    .limit(1)
                )
            )
            has_commissions = bool(
                await s.scalar(
                    select(m.commissions.id)
                    .where(m.commissions.master_id == master.id)
                    .limit(1)
                )
            )

            district_rows = await s.execute(
                select(m.districts.name)
                .join(
                    m.master_districts,
                    m.master_districts.district_id == m.districts.id,
                )
                .where(m.master_districts.master_id == master.id)
                .order_by(m.districts.name)
            )
            district_names = tuple(dr[0] for dr in district_rows)

            skill_rows = await s.execute(
                select(m.skills.name)
                .join(
                    m.master_skills,
                    m.master_skills.skill_id == m.skills.id,
                )
                .where(m.master_skills.master_id == master.id)
                .order_by(m.skills.name)
            )
            skill_names = tuple(sr[0] for sr in skill_rows)

            doc_rows = await s.execute(
                select(
                    m.attachments.id,
                    m.attachments.file_type,
                    m.attachments.file_id,
                    m.attachments.file_name,
                    m.attachments.caption,
                    m.attachments.document_type,
                )
                .where(
                    (m.attachments.entity_type == m.AttachmentEntity.MASTER)
                    & (m.attachments.entity_id == master.id)
                    & (
                        (m.attachments.document_type.in_(["passport", "selfie"]))
                        | (m.attachments.document_type.is_(None))
                    )
                )
                .order_by(m.attachments.created_at.asc())
            )
            documents = tuple(
                MasterDocument(
                    id=int(doc.id),
                    file_type=str(getattr(doc.file_type, "value", doc.file_type)),
                    file_id=doc.file_id,
                    file_name=doc.file_name,
                    caption=doc.caption,
                    document_type=doc.document_type,
                )
                for doc in doc_rows
            )

            moderation_status = (
                master.moderation_status.value
                if hasattr(master.moderation_status, "value")
                else str(master.moderation_status)
            )
            shift_status = (
                master.shift_status.value
                if getattr(master, "shift_status", None) is not None
                else "UNKNOWN"
            )
            payout_method = (
                master.payout_method.value
                if getattr(master, "payout_method", None) is not None
                else None
            )
            created_at_local = _format_created_at(master.created_at)
            updated_at_local = _format_datetime_local(master.updated_at) or created_at_local
            blocked_at_local = _format_datetime_local(master.blocked_at)
            verified_at_local = _format_datetime_local(getattr(master, "verified_at", None))
            moderation_reason = getattr(master, "moderation_reason", None) or getattr(
                master, "moderation_note", None
            )
            current_limit = master.max_active_orders_override
            if current_limit is None or int(current_limit) <= 0:
                current_limit = default_limit

            return MasterDetail(
                id=master.id,
                full_name=master.full_name,
                phone=master.phone,
                city_id=master.city_id,
                city_name=city_name,
                rating=float(master.rating or 0),
                has_vehicle=bool(getattr(master, "has_vehicle", False)),
                is_active=bool(master.is_active),
                is_blocked=bool(master.is_blocked),
                is_deleted=bool(getattr(master, "is_deleted", False)),
                blocked_reason=master.blocked_reason,
                blocked_at_local=blocked_at_local,
                moderation_status=moderation_status,
                moderation_reason=moderation_reason,
                verified=bool(master.verified),
                verified_at_local=verified_at_local,
                verified_by=getattr(master, "verified_by", None),
                is_on_shift=bool(master.is_on_shift),
                shift_status=shift_status,
                payout_method=payout_method,
                payout_data=dict(master.payout_data or {}),
                referral_code=master.referral_code,
                referred_by_master_id=master.referred_by_master_id,
                current_limit=current_limit,
                active_orders=int(active_orders),
                avg_check=avg_check,
                moderation_history=None,
                has_orders=has_orders,
                has_commissions=has_commissions,
                created_at_local=created_at_local,
                updated_at_local=updated_at_local,
                district_names=district_names,
                skill_names=skill_names,
                documents=documents,
            )


    async def manual_candidates(
        self,
        order_id: int,
        *,
        page: int,
        page_size: int,
    ) -> tuple[list[MasterBrief], bool]:
        page = max(page, 1)
        offset = (page - 1) * page_size
        async with self._session_factory() as session:
            order_q = await s.execute(
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
            raw_district = getattr(order_row, "district_id", None)
            try:
                city_id = int(raw_city) if raw_city is not None else None
            except (TypeError, ValueError):
                city_id = None
            try:
                district_id = int(raw_district) if raw_district is not None else None
            except (TypeError, ValueError):
                district_id = None

            order_payload = SimpleNamespace(
                id=order_id,
                city_id=city_id,
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

    async def list_wait_pay_recipients(self) -> list[WaitPayRecipient]:
        async with self._session_factory() as session:
            rows = await s.execute(
                select(
                    m.masters.id,
                    m.masters.tg_user_id,
                    m.masters.full_name,
                )
                .join(m.commissions, m.commissions.master_id == m.masters.id)
                .where(m.commissions.status == m.CommissionStatus.WAIT_PAY)
                .group_by(m.masters.id, m.masters.tg_user_id, m.masters.full_name)
                .order_by(m.masters.id)
            )
            recipients: list[WaitPayRecipient] = []
            for master_id, tg_user_id, full_name in rows.all():
                if tg_user_id is None:
                    continue
                recipients.append(
                    WaitPayRecipient(
                        master_id=int(master_id),
                        tg_user_id=int(tg_user_id),
                        full_name=full_name or f" #{int(master_id)}",
                    )
                )
        return recipients

    async def approve_master(self, master_id: int, by_staff_id: int) -> bool:
        """Mark a master as approved and log the action."""
        async with maybe_managed_session(session) as s:
                result = await s.execute(
                    update(m.masters)
                    .where(m.masters.id == master_id)
                    .values(
                        verified=True,
                        is_active=True,  # Активируем мастера при одобрении
                        moderation_status=m.ModerationStatus.APPROVED,
                        verified_at=datetime.now(UTC),
                        verified_by=by_staff_id,
                    )
                    .returning(m.masters.id)
                )
                if not result.first():
                    return False

                await self._log_admin_action(
                    session,
                    admin_id=by_staff_id,
                    master_id=master_id,
                    action="approve_master",
                    payload={},
                )
                live_log.push("moderation", f"master#{master_id} approved by staff#{by_staff_id}")
        return True

    async def reject_master(self, master_id: int, reason: str, by_staff_id: int) -> bool:
        """Reject a master with a provided reason."""
        async with maybe_managed_session(session) as s:
                result = await s.execute(
                    update(m.masters)
                    .where(m.masters.id == master_id)
                    .values(
                        verified=False,
                        moderation_status=m.ModerationStatus.REJECTED,
                        moderation_reason=reason,
                    )
                    .returning(m.masters.id)
                )
                if not result.first():
                    return False

                await self._log_admin_action(
                    session,
                    admin_id=by_staff_id,
                    master_id=master_id,
                    action="reject_master",
                    payload={"reason": reason},
                )
                live_log.push(
                    "moderation",
                    f"master#{master_id} rejected by staff#{by_staff_id}: {reason}",
                )
        return True

    async def block_master(self, master_id: int, reason: str, by_staff_id: int) -> bool:
        """Block a master and make them inactive."""
        async with maybe_managed_session(session) as s:
                result = await s.execute(
                    update(m.masters)
                    .where(m.masters.id == master_id)
                    .values(
                        is_blocked=True,
                        is_active=False,
                        blocked_at=datetime.now(UTC),
                        blocked_reason=reason,
                    )
                    .returning(m.masters.id)
                )
                if not result.first():
                    return False

                await self._log_admin_action(
                    session,
                    admin_id=by_staff_id,
                    master_id=master_id,
                    action="block_master",
                    payload={"reason": reason},
                )
                live_log.push(
                    "moderation",
                    f"master#{master_id} blocked by staff#{by_staff_id}: {reason}",
                )
        return True

    async def unblock_master(self, master_id: int, by_staff_id: int) -> bool:
        """Lift a block from a master and reactivate them."""
        async with maybe_managed_session(session) as s:
                result = await s.execute(
                    update(m.masters)
                    .where(m.masters.id == master_id)
                    .values(
                        is_blocked=False,
                        is_active=True,
                        blocked_at=None,
                        blocked_reason=None,
                    )
                    .returning(m.masters.id)
                )
                if not result.first():
                    return False

                await self._log_admin_action(
                    session,
                    admin_id=by_staff_id,
                    master_id=master_id,
                    action="unblock_master",
                    payload={},
                )
                live_log.push(
                    "moderation",
                    f"master#{master_id} unblocked by staff#{by_staff_id}",
                )
        return True

    async def set_master_limit(
        self,
        master_id: int,
        limit: int | None,
        by_staff_id: int,
    ) -> bool:
        """Override the max active orders limit for a master."""
        async with maybe_managed_session(session) as s:
                result = await s.execute(
                    update(m.masters)
                    .where(m.masters.id == master_id)
                    .values(max_active_orders_override=limit)
                    .returning(m.masters.id)
                )
                if not result.first():
                    return False

                await self._log_admin_action(
                    session,
                    admin_id=by_staff_id,
                    master_id=master_id,
                    action="set_limit",
                    payload={"limit": limit},
                )
                live_log.push(
                    "moderation",
                    f"master#{master_id} limit set to {limit} by staff#{by_staff_id}",
                )
        return True

    async def enqueue_master_notification(self, master_id: int, message: str) -> None:
        """Queue a moderation notification for a master."""
        async with maybe_managed_session(session) as s:
                row = await s.execute(
                    select(m.masters.tg_user_id).where(m.masters.id == master_id)
                )
                tg_user_id = row.scalar_one_or_none()

                if not tg_user_id:
                    logger.warning(f"Cannot notify master#{master_id}: no tg_user_id")
                    return

                await s.execute(
                    insert(m.notifications_outbox).values(
                        master_id=master_id,
                        event="moderation_update",
                        payload={"message": message},
                    )
                )
                live_log.push("moderation", f"notification queued for master#{master_id}")

    async def delete_master(
        self,
        master_id: int,
        by_staff_id: int,
    ) -> tuple[bool, bool]:
        """
        Delete a master from the system.
        
        Returns:
            tuple[bool, bool]: (success, is_soft_delete)
            - success: True if operation completed successfully
            - is_soft_delete: True if soft delete (has orders/commissions), False if hard delete
        """
        async with maybe_managed_session(session) as s:
                # Check if master has orders or commissions
                has_orders = bool(
                    await s.scalar(
                        select(m.orders.id)
                        .where(m.orders.assigned_master_id == master_id)
                        .limit(1)
                    )
                )
                has_commissions = bool(
                    await s.scalar(
                        select(m.commissions.id)
                        .where(m.commissions.master_id == master_id)
                        .limit(1)
                    )
                )
                
                if has_orders or has_commissions:
                    # Soft delete: mark as deleted but keep in database
                    result = await s.execute(
                        update(m.masters)
                        .where(m.masters.id == master_id)
                        .values(
                            is_deleted=True,
                            is_active=False,
                        )
                        .returning(m.masters.id)
                    )
                    if not result.first():
                        return False, False
                    
                    await self._log_admin_action(
                        session,
                        admin_id=by_staff_id,
                        master_id=master_id,
                        action="soft_delete_master",
                        payload={"has_orders": has_orders, "has_commissions": has_commissions},
                    )
                    live_log.push(
                        "moderation",
                        f"master#{master_id} soft deleted by staff#{by_staff_id}",
                    )
                    return True, True
                else:
                    # Hard delete: physically remove from database
                    # Log BEFORE deleting (FK constraint)
                    await self._log_admin_action(
                        session,
                        admin_id=by_staff_id,
                        master_id=master_id,
                        action="hard_delete_master",
                        payload={},
                    )
                    
                    # Delete related records
                    await s.execute(
                        delete(m.master_districts).where(m.master_districts.master_id == master_id)
                    )
                    await s.execute(
                        delete(m.master_skills).where(m.master_skills.master_id == master_id)
                    )
                    await s.execute(
                        delete(m.attachments).where(
                            (m.attachments.entity_type == m.AttachmentEntity.MASTER)
                            & (m.attachments.entity_id == master_id)
                        )
                    )
                    
                    # Now delete the master
                    result = await s.execute(
                        delete(m.masters)
                        .where(m.masters.id == master_id)
                        .returning(m.masters.id)
                    )
                    if not result.first():
                        return False, False
                    
                    live_log.push(
                        "moderation",
                        f"master#{master_id} hard deleted by staff#{by_staff_id}",
                    )
                    return True, False


