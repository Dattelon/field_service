from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timezone, timedelta
from zoneinfo import ZoneInfo
from decimal import Decimal
import json
import secrets
import string
from typing import Any, Iterable, Mapping, Optional, Sequence, Tuple

from sqlalchemy import and_, delete, func, insert, select, text, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from rapidfuzz import fuzz, process
from field_service.config import settings

from field_service.db import models as m
from field_service.db.session import SessionLocal
from field_service.services import distribution_worker as dw
from field_service.services import live_log
from field_service.services import time_service
from field_service.services import settings_service as settings_store
from field_service.services import owner_requisites_service as owner_reqs
from field_service.services import guarantee_service
from field_service.services.guarantee_service import GuaranteeError
from field_service.services.referral_service import apply_rewards_for_commission

from .dto import (
    CityRef,
    CommissionAttachment,
    CommissionDetail,
    CommissionListItem,
    DistrictRef,
    MasterBrief,
    MasterListItem,
    MasterDocument,
    MasterDetail,
    NewOrderAttachment,
    NewOrderData,
    OrderAttachment,
    OrderDetail,
    OrderStatusHistoryItem,
    OrderListItem,
    OrderType,
    StaffAccessCode,
    StaffMember,
    StaffRole,
    StaffUser,
    StreetRef,
    TimeslotOption,
    WaitPayRecipient,
)

UTC = timezone.utc
PAYMENT_METHOD_LABELS = {
    'card': 'РљР°СЂС‚Р°',
    'sbp': 'РЎР‘Рџ',
    'cash': 'РќР°Р»РёС‡РЅС‹Рµ',
}

LOCAL_TZ = settings_store.get_timezone()

def _format_datetime_local(value: Optional[datetime]) -> Optional[str]:
    if not value:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(LOCAL_TZ).strftime('%d.%m %H:%M')



def _parse_env_time(value: str, fallback: time) -> time:
    try:
        hh, mm = map(int, value.split(":"))
        return time(hour=hh, minute=mm)
    except Exception:
        return fallback


WORKDAY_START_DEFAULT = time_service.parse_time_string(settings.workday_start, default=time(10, 0))
WORKDAY_END_DEFAULT = time_service.parse_time_string(settings.workday_end, default=time(20, 0))
LATE_ASAP_THRESHOLD = time_service.parse_time_string(settings.asap_late_threshold, default=time(19, 30))

def _zone_storage_value(tz: ZoneInfo) -> str:
    return getattr(tz, 'key', str(tz))


async def _workday_window() -> tuple[time, time]:
    try:
        return await settings_store.get_working_window()
    except Exception:
        return WORKDAY_START_DEFAULT, WORKDAY_END_DEFAULT


QUEUE_STATUSES = {
    m.OrderStatus.SEARCHING,
    m.OrderStatus.ASSIGNED,
    m.OrderStatus.EN_ROUTE,
    m.OrderStatus.WORKING,
    m.OrderStatus.PAYMENT,
    m.OrderStatus.GUARANTEE,
}


@dataclass(slots=True)
class _StaffAccess:
    id: int
    role: m.StaffRole
    is_active: bool
    city_ids: frozenset[int]


async def _load_staff_access(
    session: AsyncSession, staff_id: Optional[int]
) -> Optional[_StaffAccess]:
    if not staff_id:
        return None
    row = await session.execute(
        select(m.staff_users).where(m.staff_users.id == staff_id)
    )
    staff = row.scalar_one_or_none()
    if not staff or not staff.is_active:
        return None
    cities_q = await session.execute(
        select(m.staff_cities.city_id).where(m.staff_cities.staff_user_id == staff.id)
    )
    city_ids = frozenset(int(c[0]) for c in cities_q)
    return _StaffAccess(
        id=staff.id,
        role=staff.role,
        is_active=staff.is_active,
        city_ids=city_ids,
    )


def _visible_city_ids_for_staff(staff: Optional[_StaffAccess]) -> Optional[frozenset[int]]:
    if staff is None:
        return None
    if staff.role == m.StaffRole.ADMIN:
        return None
    return staff.city_ids


def _staff_can_access_city(
    staff: Optional[_StaffAccess], city_id: Optional[int]
) -> bool:
    if city_id is None:
        return False
    visible = _visible_city_ids_for_staff(staff)
    if visible is None:
        return True
    return city_id in visible

def _prepare_setting_value(value: object, value_type: str) -> str:
    vt = value_type.upper()
    if vt == "JSON":
        return json.dumps(value, ensure_ascii=False)
    if vt == "BOOL":
        if isinstance(value, str):
            return "true" if value.strip().lower() in {"1", "true", "yes", "on"} else "false"
        return "true" if bool(value) else "false"
    if vt == "TIME" and isinstance(value, time):
        return value.strftime("%H:%M")
    return "" if value is None else str(value)


def _format_created_at(dt: Optional[datetime]) -> str:
    if not dt:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(LOCAL_TZ).strftime("%d.%m %H:%M")


def _format_slot(
    scheduled_date: Optional[datetime],
    slot_label: Optional[str],
    slot_start: Optional[datetime],
    slot_end: Optional[datetime],
) -> Optional[str]:
    if slot_label:
        return slot_label
    if slot_start and slot_end:
        return f"{slot_start.strftime('%H:%M')}-{slot_end.strftime('%H:%M')}"
    if scheduled_date:
        return scheduled_date.strftime("%d.%m")
    return None

def _map_staff_role(db_role: m.StaffRole) -> StaffRole:
    if db_role == m.StaffRole.ADMIN:
        return StaffRole.GLOBAL_ADMIN
    if hasattr(m.StaffRole, "CITY_ADMIN") and db_role == getattr(
        m.StaffRole, "CITY_ADMIN"
    ):
        return StaffRole.CITY_ADMIN
    return StaffRole.LOGIST


def _map_staff_role_to_db(role: StaffRole) -> m.StaffRole:
    if role is StaffRole.CITY_ADMIN and hasattr(m.StaffRole, "CITY_ADMIN"):
        return getattr(m.StaffRole, "CITY_ADMIN")
    if role is StaffRole.LOGIST:
        return m.StaffRole.LOGIST
    return m.StaffRole.ADMIN


def _sorted_city_tuple(city_ids: Optional[Iterable[int]]) -> tuple[int, ...]:
    if not city_ids:
        return tuple()
    return tuple(sorted({int(cid) for cid in city_ids}))


async def _load_staff_city_map(
    session: AsyncSession, staff_rows: Sequence[m.staff_users]
) -> dict[int, list[int]]:
    ids = [row.id for row in staff_rows]
    city_map: dict[int, list[int]] = {sid: [] for sid in ids}
    if not ids:
        return city_map
    rows = await session.execute(
        select(m.staff_cities.staff_user_id, m.staff_cities.city_id).where(
            m.staff_cities.staff_user_id.in_(ids)
        )
    )
    for staff_id, city_id in rows:
        city_map[int(staff_id)].append(int(city_id))
    return city_map


async def _collect_code_cities(
    session: AsyncSession, code_ids: Sequence[int]
) -> dict[int, list[int]]:
    links: dict[int, list[int]] = {cid: [] for cid in code_ids}
    if not code_ids:
        return links
    rows = await session.execute(
        select(
            m.staff_access_code_cities.access_code_id,
            m.staff_access_code_cities.city_id,
        ).where(m.staff_access_code_cities.access_code_id.in_(code_ids))
    )
    for code_id, city_id in rows:
        links[int(code_id)].append(int(city_id))
    return links


class AccessCodeError(RuntimeError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _order_type_from_db(value: Optional[str]) -> OrderType:
    if not value:
        return OrderType.NORMAL
    try:
        return OrderType(value)
    except ValueError:
        return OrderType.NORMAL


def _map_order_type_to_db(order_type: OrderType) -> m.OrderType:
    if order_type is OrderType.GUARANTEE:
        return m.OrderType.GUARANTEE
    return m.OrderType.NORMAL


def _attachment_type_from_string(value: Optional[str]) -> m.AttachmentFileType:
    if not value:
        return m.AttachmentFileType.OTHER
    normalized = value.lower()
    if normalized == "photo":
        return m.AttachmentFileType.PHOTO
    if normalized == "document":
        return m.AttachmentFileType.DOCUMENT
    return m.AttachmentFileType.OTHER


def _generate_staff_code() -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(8))


class DBStaffService:
    def __init__(self, session_factory=SessionLocal, *, access_code_ttl_hours: int | None = None) -> None:
        self._session_factory = session_factory
        if access_code_ttl_hours is None:
            access_code_ttl_hours = settings.access_code_ttl_hours
        self._access_code_ttl_hours = int(access_code_ttl_hours) if access_code_ttl_hours is not None else 0

    async def seed_global_admins(self, tg_ids: Sequence[int]) -> int:
        unique_ids = sorted({int(tg) for tg in tg_ids if tg})
        if not unique_ids:
            return 0
        async with self._session_factory() as session:
            payload = [
                {
                    "tg_user_id": tg_id,
                    "role": m.StaffRole.ADMIN,
                    "is_active": True,
                }
                for tg_id in unique_ids
            ]
            if not payload:
                return 0
            async with session.begin():
                total = await session.scalar(select(func.count()).select_from(m.staff_users))
                if total and int(total) > 0:
                    return 0
                await session.execute(insert(m.staff_users), payload)
            return len(payload)

    async def get_by_tg_id(self, tg_id: int) -> Optional[StaffUser]:
        if tg_id is None:
            return None
        async with self._session_factory() as session:
            row = await session.execute(
                select(m.staff_users).where(m.staff_users.tg_user_id == tg_id)
            )
            staff = row.scalar_one_or_none()
            if not staff:
                return None
            city_rows = await session.execute(
                select(m.staff_cities.city_id).where(
                    m.staff_cities.staff_user_id == staff.id
                )
            )
            city_ids = frozenset(int(c[0]) for c in city_rows)
            return StaffUser(
                id=staff.id,
                tg_id=staff.tg_user_id or 0,
                role=_map_staff_role(staff.role),
                is_active=bool(staff.is_active),
                city_ids=city_ids,
                full_name=staff.full_name or "",
                phone=staff.phone or "",
            )
    async def list_staff(
        self,
        *,
        role: Optional[StaffRole],
        page: int,
        page_size: int,
    ) -> tuple[list[StaffMember], bool]:
        offset = max(page - 1, 0) * page_size
        async with self._session_factory() as session:
            stmt = select(m.staff_users).order_by(m.staff_users.created_at.desc())
            if role:
                stmt = stmt.where(
                    m.staff_users.role == _map_staff_role_to_db(role)
                )
            rows = await session.execute(stmt.offset(offset).limit(page_size + 1))
            staff_rows = rows.scalars().all()
            has_next = len(staff_rows) > page_size
            staff_rows = staff_rows[:page_size]
            if not staff_rows:
                return [], has_next
            city_map = await _load_staff_city_map(session, staff_rows)
            members = [
                StaffMember(
                    id=staff.id,
                    tg_id=staff.tg_user_id,
                    username=staff.username,
                    full_name=staff.full_name or "",
                    phone=staff.phone,
                    role=_map_staff_role(staff.role),
                    is_active=bool(staff.is_active),
                    city_ids=_sorted_city_tuple(city_map.get(staff.id)),
                    created_at=staff.created_at,
                    updated_at=staff.updated_at,
                )
                for staff in staff_rows
            ]
            return members, has_next

    async def get_staff_member(self, staff_id: int) -> Optional[StaffMember]:
        async with self._session_factory() as session:
            row = await session.execute(
                select(m.staff_users).where(m.staff_users.id == staff_id)
            )
            staff = row.scalar_one_or_none()
            if not staff:
                return None
            city_map = await _load_staff_city_map(session, [staff])
            return StaffMember(
                id=staff.id,
                tg_id=staff.tg_user_id,
                username=staff.username,
                full_name=staff.full_name or "",
                phone=staff.phone,
                role=_map_staff_role(staff.role),
                is_active=bool(staff.is_active),
                city_ids=_sorted_city_tuple(city_map.get(staff.id)),
                created_at=staff.created_at,
                updated_at=staff.updated_at,
            )

    async def set_staff_cities(
        self, staff_id: int, city_ids: Iterable[int]
    ) -> None:
        normalized = _sorted_city_tuple(city_ids)
        async with self._session_factory() as session:
            async with session.begin():
                await session.execute(
                    delete(m.staff_cities).where(m.staff_cities.staff_user_id == staff_id)
                )
                session.add_all(
                    m.staff_cities(staff_user_id=staff_id, city_id=cid)
                    for cid in normalized
                )

    async def set_staff_role(self, staff_id: int, role: StaffRole) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                await session.execute(
                    update(m.staff_users)
                    .where(m.staff_users.id == staff_id)
                    .values(role=_map_staff_role_to_db(role))
                )

    async def set_staff_active(self, staff_id: int, is_active: bool) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                await session.execute(
                    update(m.staff_users)
                    .where(m.staff_users.id == staff_id)
                    .values(is_active=is_active)
                )

    async def update_staff_profile(
        self, staff_id: int, *, full_name: str, phone: str, username: Optional[str] | None = None
    ) -> None:
        values: dict[str, Any] = {"full_name": full_name, "phone": phone}
        if username is not None:
            values["username"] = username
        async with self._session_factory() as session:
            async with session.begin():
                await session.execute(
                    update(m.staff_users)
                    .where(m.staff_users.id == staff_id)
                    .values(**values)
                )


    async def create_access_code(
        self,
        *,
        role: StaffRole,
        city_ids: Iterable[int],
        issued_by_staff_id: Optional[int],
        expires_at: Optional[datetime],
        comment: Optional[str],
    ) -> StaffAccessCode:
        unique_cities = _sorted_city_tuple(city_ids)
        expires_at_value = expires_at
        ttl_hours = max(0, self._access_code_ttl_hours)
        if expires_at_value is None and ttl_hours > 0:
            expires_at_value = datetime.now(UTC) + timedelta(hours=ttl_hours)
        async with self._session_factory() as session:
            async with session.begin():
                code_value = await self._generate_unique_code(session)
                db_role = _map_staff_role_to_db(role)
                city_column = unique_cities[0] if len(unique_cities) == 1 else None
                code_row = m.staff_access_codes(
                    code=code_value,
                    role=db_role,
                    city_id=city_column,
                    issued_by_staff_id=issued_by_staff_id,
                    expires_at=expires_at_value,
                    comment=comment,
                )
                session.add(code_row)
                await session.flush()
                session.add_all(
                    m.staff_access_code_cities(
                        access_code_id=code_row.id, city_id=cid
                    )
                    for cid in unique_cities
                )
                cities_label = "".join(str(cid) for cid in unique_cities) or '-'
                live_log.push("staff", f"access_code issued code={code_value} role={role.value} cities={cities_label}")
            return StaffAccessCode(
                id=code_row.id,
                code=code_row.code,
                role=role,
                city_ids=unique_cities,
                issued_by_staff_id=code_row.issued_by_staff_id,
                used_by_staff_id=code_row.used_by_staff_id,
                expires_at=code_row.expires_at,
                used_at=code_row.used_at,
                is_revoked=bool(code_row.is_revoked),
                comment=code_row.comment,
                created_at=code_row.created_at,
            )

    async def validate_access_code_value(self, code_value: str) -> Optional[StaffAccessCode]:
        normalized = (code_value or "").strip().upper()
        if not normalized:
            return None
        now = datetime.now(UTC)
        async with self._session_factory() as session:
            row = await session.execute(
                select(m.staff_access_codes).where(m.staff_access_codes.code == normalized)
            )
            code_row = row.scalar_one_or_none()
            if not code_row:
                return None
            if bool(code_row.is_revoked):
                return None
            if code_row.used_at is not None:
                return None
            expires_at = code_row.expires_at
            if expires_at and expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)
            if expires_at and expires_at < now:
                return None
            link_map = await _collect_code_cities(session, [code_row.id])
            cities = _sorted_city_tuple(
                link_map.get(code_row.id) or ([code_row.city_id] if code_row.city_id else [])
            )
            role = _map_staff_role(code_row.role)
            if role in (StaffRole.CITY_ADMIN, StaffRole.LOGIST) and not cities:
                return None
            return StaffAccessCode(
                id=code_row.id,
                code=code_row.code,
                role=role,
                city_ids=cities,
                issued_by_staff_id=code_row.issued_by_staff_id,
                used_by_staff_id=code_row.used_by_staff_id,
                expires_at=code_row.expires_at,
                used_at=code_row.used_at,
                is_revoked=bool(code_row.is_revoked),
                comment=code_row.comment,
                created_at=code_row.created_at,
            )


    async def register_staff_user_from_code(
        self,
        *,
        code_value: str,
        tg_user_id: int,
        username: Optional[str],
        full_name: str,
        phone: str,
    ) -> StaffUser:
        normalized = (code_value or "").strip().upper()
        if not normalized:
            raise AccessCodeError("invalid_code")
        now = datetime.now(UTC)
        async with self._session_factory() as session:
            async with session.begin():
                code_stmt = (
                    select(m.staff_access_codes)
                    .where(
                        m.staff_access_codes.code == normalized,
                        m.staff_access_codes.is_revoked == False,
                        m.staff_access_codes.used_at.is_(None),
                    )
                    .with_for_update()
                )
                code_row = (await session.execute(code_stmt)).scalar_one_or_none()
                if not code_row:
                    raise AccessCodeError("invalid_code")
                expires_at = code_row.expires_at
                if expires_at and expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=UTC)
                if expires_at and expires_at < now:
                    raise AccessCodeError("expired")
                link_map = await _collect_code_cities(session, [code_row.id])
                city_ids = _sorted_city_tuple(
                    link_map.get(code_row.id) or ([code_row.city_id] if code_row.city_id else [])
                )
                role = _map_staff_role(code_row.role)
                if role in (StaffRole.CITY_ADMIN, StaffRole.LOGIST) and not city_ids:
                    raise AccessCodeError("no_cities")
                existing = await session.execute(
                    select(m.staff_users).where(m.staff_users.tg_user_id == tg_user_id)
                )
                if existing.scalar_one_or_none():
                    raise AccessCodeError("already_staff")
                staff_row = m.staff_users(
                    tg_user_id=tg_user_id,
                    username=username,
                    full_name=full_name,
                    phone=phone,
                    role=_map_staff_role_to_db(role),
                    is_active=True,
                )
                session.add(staff_row)
                await session.flush()
                session.add_all(
                    m.staff_cities(staff_user_id=staff_row.id, city_id=cid)
                    for cid in city_ids
                )
                await session.execute(
                    update(m.staff_access_codes)
                    .where(m.staff_access_codes.id == code_row.id)
                    .values(
                        used_by_staff_id=staff_row.id,
                        used_at=now,
                    )
                )
                live_log.push("staff", f"access_code used code={code_row.code} staff={staff_row.id}")
            return StaffUser(
                id=staff_row.id,
                tg_id=tg_user_id,
                role=role,
                is_active=True,
                city_ids=frozenset(city_ids),
                full_name=staff_row.full_name or "",
                phone=staff_row.phone or "",
            )


    async def list_access_codes(
        self,
        *,
        state: str,
        page: int,
        page_size: int,
    ) -> tuple[list[StaffAccessCode], bool]:
        offset = max(page - 1, 0) * page_size
        now = datetime.now(UTC)
        async with self._session_factory() as session:
            stmt = select(m.staff_access_codes).order_by(
                m.staff_access_codes.created_at.desc()
            )
            if state == "active":
                stmt = stmt.where(
                    (m.staff_access_codes.is_revoked == False)  # noqa: E712
                    & (m.staff_access_codes.used_at.is_(None))
                    & (
                        (m.staff_access_codes.expires_at.is_(None))
                        | (m.staff_access_codes.expires_at >= now)
                    )
                )
            elif state == "used":
                stmt = stmt.where(m.staff_access_codes.used_at.is_not(None))
            elif state == "revoked":
                stmt = stmt.where(m.staff_access_codes.is_revoked == True)  # noqa: E712
            rows = await session.execute(stmt.offset(offset).limit(page_size + 1))
            code_rows = rows.scalars().all()
            has_next = len(code_rows) > page_size
            code_rows = code_rows[:page_size]
            if not code_rows:
                return [], has_next
            link_map = await _collect_code_cities(
                session, [code.id for code in code_rows]
            )
            items: list[StaffAccessCode] = []
            for code in code_rows:
                cities = _sorted_city_tuple(
                    link_map.get(code.id) or ([code.city_id] if code.city_id else [])
                )
                items.append(
                    StaffAccessCode(
                        id=code.id,
                        code=code.code,
                        role=_map_staff_role(code.role),
                        city_ids=cities,
                        issued_by_staff_id=code.issued_by_staff_id,
                        used_by_staff_id=code.used_by_staff_id,
                        expires_at=code.expires_at,
                        used_at=code.used_at,
                        is_revoked=bool(code.is_revoked),
                        comment=code.comment,
                        created_at=code.created_at,
                    )
                )
            return items, has_next

    async def list_wait_pay_recipients(self) -> list[WaitPayRecipient]:
        async with self._session_factory() as session:
            rows = await session.execute(
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

    async def get_access_code(self, code_id: int) -> Optional[StaffAccessCode]:
        async with self._session_factory() as session:
            row = await session.execute(
                select(m.staff_access_codes).where(m.staff_access_codes.id == code_id)
            )
            code = row.scalar_one_or_none()
            if not code:
                return None
            link_map = await _collect_code_cities(session, [code.id])
            cities = _sorted_city_tuple(
                link_map.get(code.id) or ([code.city_id] if code.city_id else [])
            )
            return StaffAccessCode(
                id=code.id,
                code=code.code,
                role=_map_staff_role(code.role),
                city_ids=cities,
                issued_by_staff_id=code.issued_by_staff_id,
                used_by_staff_id=code.used_by_staff_id,
                expires_at=code.expires_at,
                used_at=code.used_at,
                is_revoked=bool(code.is_revoked),
                comment=code.comment,
                created_at=code.created_at,
            )

    async def revoke_access_code(
        self, code_id: int, *, by_staff_id: Optional[int] = None
    ) -> bool:
        async with self._session_factory() as session:
            async with session.begin():
                result = await session.execute(
                    update(m.staff_access_codes)
                    .where(
                        (m.staff_access_codes.id == code_id)
                        & (m.staff_access_codes.used_at.is_(None))
                        & (m.staff_access_codes.is_revoked == False)  # noqa: E712
                    )
                    .values(is_revoked=True)
                    .returning(m.staff_access_codes.id, m.staff_access_codes.code)
                )
                row = result.first()
                if not row:
                    return False
                revoked_code = row.code
            live_log.push("staff", f"access_code revoked code={revoked_code} by={by_staff_id}")
        return True

    async def _generate_unique_code(self, session: AsyncSession) -> str:
        for _ in range(50):
            code_value = _generate_staff_code()
            exists = await session.execute(
                select(m.staff_access_codes.id).where(
                    m.staff_access_codes.code == code_value
                )
            )
            if exists.first() is None:
                return code_value
        raise RuntimeError("Unable to generate unique access code after 50 attempts")


class DBOrdersService:
    def __init__(self, session_factory=SessionLocal) -> None:
        self._session_factory = session_factory

async def _city_timezone(self, session: AsyncSession, city_id: Optional[int]) -> ZoneInfo:
    if not city_id:
        return time_service.resolve_timezone(settings.timezone)
    if hasattr(m.cities, "timezone"):
        row = await session.execute(
            select(m.cities.timezone).where(m.cities.id == int(city_id))
        )
        value = row.scalar_one_or_none()
        if value:
            return time_service.resolve_timezone(str(value))
    return time_service.resolve_timezone(settings.timezone)

async def get_city_timezone(self, city_id: Optional[int]) -> str:
    async with self._session_factory() as session:
        tz = await self._city_timezone(session, city_id)
        return _zone_storage_value(tz)

    async def list_cities(
        self, *, query: Optional[str] = None, limit: int = 20
    ) -> list[CityRef]:
        async with self._session_factory() as session:
            stmt = (
                select(m.cities.id, m.cities.name)
                .where(m.cities.is_active == True)  # noqa: E712
                .order_by(m.cities.name)
                .limit(limit)
            )
            if query:
                pattern = f"%{query.lower()}%"
                stmt = stmt.where(func.lower(m.cities.name).like(pattern))
            rows = await session.execute(stmt)
            fetched = rows.all()
            return [CityRef(id=int(row.id), name=row.name) for row in fetched]

    async def get_city(self, city_id: int) -> Optional[CityRef]:
        async with self._session_factory() as session:
            row = await session.execute(
                select(m.cities.id, m.cities.name).where(m.cities.id == city_id)
            )
            result = row.first()
            if not result:
                return None
            return CityRef(id=int(result.id), name=result.name)

    async def list_districts(
        self, city_id: int, *, page: int, page_size: int
    ) -> tuple[list[DistrictRef], bool]:
        offset = max(page - 1, 0) * page_size
        async with self._session_factory() as session:
            stmt = (
                select(m.districts.id, m.districts.name)
                .where(m.districts.city_id == city_id)
                .order_by(m.districts.name)
                .offset(offset)
                .limit(page_size + 1)
            )
            rows = await session.execute(stmt)
            fetched = rows.all()
        has_next = len(fetched) > page_size
        districts = [
            DistrictRef(id=int(row.id), city_id=city_id, name=row.name)
            for row in fetched[:page_size]
        ]
        return districts, has_next

    async def get_district(self, district_id: int) -> Optional[DistrictRef]:
        async with self._session_factory() as session:
            row = await session.execute(
                select(m.districts.id, m.districts.name, m.districts.city_id)
                .where(m.districts.id == district_id)
            )
            result = row.first()
            if not result:
                return None
            return DistrictRef(
                id=int(result.id), city_id=int(result.city_id), name=result.name
            )

    async def search_streets(
        self, city_id: int, query: str, *, limit: int = 10
    ) -> list[StreetRef]:
        normalized = query.strip()
        if not normalized:
            return []
        async with self._session_factory() as session:
            stmt = (
                select(
                    m.streets.id,
                    m.streets.name,
                    m.streets.district_id,
                )
                .where(m.streets.city_id == city_id)
                .order_by(m.streets.name)
                .limit(200)
            )
            rows = await session.execute(stmt)
            items = rows.all()
        if not items:
            return []
        choices = {row.name: row for row in items}
        matches = process.extract(
            normalized,
            list(choices.keys()),
            scorer=fuzz.WRatio,
            processor=lambda s: s.lower(),
            limit=min(limit, len(choices)),
        )
        result: list[StreetRef] = []
        used: set[int] = set()
        for name, score, _ in matches:
            row = choices[name]
            street_id = int(row.id)
            if street_id in used:
                continue
            result.append(
                StreetRef(
                    id=street_id,
                    city_id=city_id,
                    district_id=int(row.district_id) if row.district_id is not None else None,
                    name=row.name,
                    score=float(score),
                )
            )
            used.add(street_id)
        return result

    async def get_street(self, street_id: int) -> Optional[StreetRef]:
        async with self._session_factory() as session:
            row = await session.execute(
                select(
                    m.streets.id,
                    m.streets.city_id,
                    m.streets.district_id,
                    m.streets.name,
                ).where(m.streets.id == street_id)
            )
            result = row.first()
            if not result:
                return None
            return StreetRef(
                id=int(result.id),
                city_id=int(result.city_id),
                district_id=int(result.district_id) if result.district_id is not None else None,
                name=result.name,
            )

    async def list_queue(
        self,
        *,
        city_ids: Optional[Iterable[int]],
        page: int,
        page_size: int,
        status_filter: Optional[OrderStatus] = None,
        category: Optional[str] = None,
        master_id: Optional[int] = None,
        scheduled_date: Optional[date] = None,
    ) -> tuple[list[OrderListItem], bool]:
        offset = max(page - 1, 0) * page_size
        city_filter: Optional[list[int]] = None
        if city_ids is not None:
            city_filter = [int(cid) for cid in city_ids]
            if not city_filter:
                return [], False
        allowed_statuses = [status.value for status in QUEUE_STATUSES]
        async with self._session_factory() as session:
            stmt = (
                select(
                    m.orders.id,
                    m.orders.city_id,
                    m.cities.name.label("city_name"),
                    m.orders.district_id,
                    m.districts.name.label("district_name"),
                    m.streets.name.label("street_name"),
                    m.orders.house,
                    m.orders.status,
                    m.orders.order_type,
                    m.orders.category,
                    m.orders.created_at,
                    m.orders.scheduled_date,
                    m.orders.slot_label,
                    m.orders.time_slot_start,
                    m.orders.time_slot_end,
                    m.orders.assigned_master_id,
                    m.masters.full_name.label("master_name"),
                    m.masters.phone.label("master_phone"),
                    func.count(m.attachments.id).label("attachments_count"),
                )
                .select_from(m.orders)
                .join(m.cities, m.orders.city_id == m.cities.id)
                .join(
                    m.districts,
                    m.orders.district_id == m.districts.id,
                    isouter=True,
                )
                .join(
                    m.streets,
                    m.orders.street_id == m.streets.id,
                    isouter=True,
                )
                .join(
                    m.masters,
                    m.orders.assigned_master_id == m.masters.id,
                    isouter=True,
                )
                .join(
                    m.attachments,
                    (m.attachments.entity_type == m.AttachmentEntity.ORDER)
                    & (m.attachments.entity_id == m.orders.id),
                    isouter=True,
                )
            )
            if status_filter:
                stmt = stmt.where(m.orders.status == status_filter.value)
            else:
                stmt = stmt.where(m.orders.status.in_(allowed_statuses))
            if city_filter is not None:
                stmt = stmt.where(m.orders.city_id.in_(city_filter))
            if category:
                stmt = stmt.where(m.orders.category == category)
            if master_id:
                stmt = stmt.where(m.orders.assigned_master_id == master_id)
            if scheduled_date:
                stmt = stmt.where(m.orders.scheduled_date == scheduled_date)
            stmt = (
                stmt.group_by(
                    m.orders.id,
                    m.orders.city_id,
                    m.cities.name,
                    m.orders.district_id,
                    m.districts.name,
                    m.streets.name,
                    m.orders.house,
                    m.orders.status,
                    m.orders.order_type,
                    m.orders.category,
                    m.orders.created_at,
                    m.orders.scheduled_date,
                    m.orders.slot_label,
                    m.orders.time_slot_start,
                    m.orders.time_slot_end,
                    m.orders.assigned_master_id,
                    m.masters.full_name,
                    m.masters.phone,
                )
                .order_by(m.orders.created_at.desc())
                .offset(offset)
                .limit(page_size + 1)
            )
            rows = await session.execute(stmt)
            fetched = rows.all()
        has_next = len(fetched) > page_size
        items: list[OrderListItem] = []
        for row in fetched[:page_size]:
            order_type = _order_type_from_db(row.order_type)
            timeslot = _format_slot(
                row.scheduled_date,
                row.slot_label,
                row.time_slot_start,
                row.time_slot_end,
            )
            items.append(
                OrderListItem(
                    id=row.id,
                    city_id=row.city_id,
                    city_name=row.city_name,
                    district_id=row.district_id,
                    district_name=row.district_name,
                    street_name=row.street_name,
                    house=row.house,
                    status=str(row.status),
                    order_type=order_type,
                    category=row.category,
                    created_at_local=_format_created_at(row.created_at),
                    timeslot_local=timeslot,
                    master_id=row.assigned_master_id,
                    master_name=row.master_name,
                    master_phone=row.master_phone,
                    has_attachments=bool(row.attachments_count),
                )
            )
        return items, has_next

    async def list_wait_pay_recipients(self) -> list[WaitPayRecipient]:
        async with self._session_factory() as session:
            rows = await session.execute(
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

    async def get_card(self, order_id: int) -> Optional[OrderDetail]:
        async with self._session_factory() as session:
            stmt = (
                select(
                    m.orders,
                    m.cities.name.label("city_name"),
                    m.districts.name.label("district_name"),
                    m.streets.name.label("street_name"),
                    m.masters.full_name.label("master_name"),
                    m.masters.phone.label("master_phone"),
                )
                .select_from(m.orders)
                .join(m.cities, m.orders.city_id == m.cities.id)
                .join(
                    m.districts,
                    m.orders.district_id == m.districts.id,
                    isouter=True,
                )
                .join(
                    m.streets,
                    m.orders.street_id == m.streets.id,
                    isouter=True,
                )
                .join(
                    m.masters,
                    m.orders.assigned_master_id == m.masters.id,
                    isouter=True,
                )
                .where(m.orders.id == order_id)
            )
            row = await session.execute(stmt)
            data = row.first()
            if not data:
                return None
            order: m.orders = data.orders
            attachments = await self._load_attachments(session, order.id)
            timeslot = _format_slot(
                order.scheduled_date,
                order.slot_label,
                order.time_slot_start,
                order.time_slot_end,
            )
            order_type = _order_type_from_db(getattr(order, "order_type", None))
            return OrderDetail(
                id=order.id,
                city_id=order.city_id,
                city_name=data.city_name,
                district_id=order.district_id,
                district_name=data.district_name,
                street_name=data.street_name,
                house=order.house,
                status=order.status.value,
                order_type=order_type,
                category=order.category,
                created_at_local=_format_created_at(order.created_at),
                timeslot_local=timeslot,
                master_id=order.assigned_master_id,
                master_name=data.master_name,
                master_phone=data.master_phone,
                has_attachments=bool(attachments),
                client_name=order.client_name,
                client_phone=order.client_phone,
                apartment=order.apartment,
                address_comment=order.address_comment,
                description=order.description,
                latitude=float(order.latitude) if order.latitude is not None else None,
                longitude=float(order.longitude)
                if order.longitude is not None
                else None,
                company_payment=Decimal(order.company_payment or 0),
                total_price=Decimal(order.total_price or 0),
                attachments=attachments,
            )

    async def list_status_history(
        self, order_id: int, *, limit: int = 5
    ) -> tuple[OrderStatusHistoryItem, ...]:
        async with self._session_factory() as session:
            limited = max(1, limit)
            rows = await session.execute(
                select(
                    m.order_status_history.id,
                    m.order_status_history.from_status,
                    m.order_status_history.to_status,
                    m.order_status_history.reason,
                    m.order_status_history.changed_by_staff_id,
                    m.order_status_history.changed_by_master_id,
                    m.order_status_history.created_at,
                )
                .where(m.order_status_history.order_id == order_id)
                .order_by(m.order_status_history.created_at.desc())
                .limit(limited)
            )
            items: list[OrderStatusHistoryItem] = []
            for row in rows:
                items.append(
                    OrderStatusHistoryItem(
                        id=row.id,
                        from_status=row.from_status.value if row.from_status else None,
                        to_status=row.to_status.value if row.to_status else None,
                        reason=row.reason,
                        changed_by_staff_id=row.changed_by_staff_id,
                        changed_by_master_id=row.changed_by_master_id,
                        changed_at_local=_format_created_at(row.created_at) or "",
                    )
                )
            return tuple(items)

    async def get_order_attachment(
        self, order_id: int, attachment_id: int
    ) -> Optional[OrderAttachment]:
        async with self._session_factory() as session:
            row = await session.execute(
                select(
                    m.attachments.id,
                    m.attachments.file_type,
                    m.attachments.file_id,
                    m.attachments.file_name,
                    m.attachments.caption,
                )
                .where(
                    and_(
                        m.attachments.entity_type == m.AttachmentEntity.ORDER,
                        m.attachments.entity_id == order_id,
                        m.attachments.id == attachment_id,
                    )
                )
                .limit(1)
            )
            data = row.first()
            if not data:
                return None
            return OrderAttachment(
                id=data.id,
                file_type=str(data.file_type),
                file_id=data.file_id,
                file_name=data.file_name,
                caption=data.caption,
            )

    async def _load_attachments(
        self, session: AsyncSession, order_id: int
    ) -> tuple[OrderAttachment, ...]:
        rows = await session.execute(
            select(
                m.attachments.id,
                m.attachments.file_type,
                m.attachments.file_id,
                m.attachments.file_name,
                m.attachments.caption,
            )
            .where(
                (m.attachments.entity_type == m.AttachmentEntity.ORDER)
                & (m.attachments.entity_id == order_id)
            )
            .order_by(m.attachments.created_at.asc())
        )
        attachments = []
        for row in rows:
            attachments.append(
                OrderAttachment(
                    id=row.id,
                    file_type=str(row.file_type),
                    file_id=row.file_id,
                    file_name=row.file_name,
                    caption=row.caption,
                )
            )
        return tuple(attachments)

    async def create_order(self, data: NewOrderData) -> int:
        async with self._session_factory() as session:
            async with session.begin():
                tz = await self._city_timezone(session, data.city_id)
                _, workday_end = await _workday_window()
                now_local = datetime.now(timezone.utc).astimezone(tz)
                current_time = now_local.timetz()
                if current_time.tzinfo is not None:
                    current_time = current_time.replace(tzinfo=None)
                initial_status = data.initial_status or m.OrderStatus.SEARCHING
                if data.initial_status is None and current_time >= workday_end:
                    initial_status = m.OrderStatus.DEFERRED
                order = m.orders(
                    city_id=data.city_id,
                    district_id=data.district_id,
                    street_id=data.street_id,
                    house=data.house,
                    apartment=data.apartment,
                    address_comment=data.address_comment,
                    client_name=data.client_name,
                    client_phone=data.client_phone,
                    category=data.category,
                    description=data.description,
                    order_type=_map_order_type_to_db(data.order_type),
                    scheduled_date=data.scheduled_date,
                    time_slot_start=data.time_slot_start,
                    time_slot_end=data.time_slot_end,
                    slot_label=data.slot_label,
                    latitude=data.latitude,
                    longitude=data.longitude,
                    preferred_master_id=data.preferred_master_id,
                    guarantee_source_order_id=data.guarantee_source_order_id,
                    company_payment=Decimal(data.company_payment or 0),
                    total_price=Decimal(data.total_price or 0),
                    created_by_staff_id=data.created_by_staff_id,
                    status=initial_status,
                )
                session.add(order)
                await session.flush()
                if data.attachments:
                    session.add_all(
                        m.attachments(
                            entity_type=m.AttachmentEntity.ORDER,
                            entity_id=order.id,
                            file_type=_attachment_type_from_string(att.file_type),
                            file_id=att.file_id,
                            file_unique_id=att.file_unique_id,
                            file_name=att.file_name,
                            mime_type=att.mime_type,
                            caption=att.caption,
                            uploaded_by_staff_id=data.created_by_staff_id,
                        )
                        for att in data.attachments
                    )
                session.add(
                    m.order_status_history(
                        order_id=order.id,
                        from_status=None,
                        to_status=initial_status,
                        reason="created_by_staff",
                        changed_by_staff_id=data.created_by_staff_id,
                    )
                )
            return order.id

    async def has_active_guarantee(self, source_order_id: int) -> bool:
        async with self._session_factory() as session:
            row = await session.execute(
                select(1)
                .where(m.orders.guarantee_source_order_id == source_order_id)
                .where(~m.orders.status.in_([m.OrderStatus.CANCELED, m.OrderStatus.CLOSED]))
                .limit(1)
            )
            return row.first() is not None

    async def create_guarantee_order(self, source_order_id: int, by_staff_id: int) -> int:
        async with self._session_factory() as session:
            async with session.begin():
                src_query = await session.execute(
                    select(m.orders)
                    .where(m.orders.id == source_order_id)
                    .with_for_update()
                )
                source = src_query.scalar_one_or_none()
                if source is None:
                    raise GuaranteeError("source order not found")

                staff = await _load_staff_access(session, by_staff_id or None)
                if not _staff_can_access_city(staff, source.city_id):
                    raise GuaranteeError("no access to city")

                status_val = getattr(source, "status", None)
                if isinstance(status_val, m.OrderStatus):
                    status_is_closed = status_val == m.OrderStatus.CLOSED
                else:
                    status_is_closed = str(status_val).upper() == m.OrderStatus.CLOSED.value
                if not status_is_closed:
                    raise GuaranteeError("source order must be CLOSED")

                if getattr(source, "order_type", None) == m.OrderType.GUARANTEE:
                    raise GuaranteeError("source order already guarantee")

                if not source.assigned_master_id:
                    raise GuaranteeError("source order has no assigned master")

                existing = await session.execute(
                    select(m.orders.id)
                    .where(m.orders.guarantee_source_order_id == source_order_id)
                    .where(~m.orders.status.in_([m.OrderStatus.CANCELED, m.OrderStatus.CLOSED]))
                    .limit(1)
                )
                if existing.first():
                    raise GuaranteeError("guarantee already exists")

                created = await guarantee_service.create_from_closed_order(
                    session,
                    source_order_id,
                    source=source,
                    created_by_staff_id=staff.id if staff else None,
                )
                return created.id

    async def return_to_search(self, order_id: int, by_staff_id: int) -> bool:
        async with self._session_factory() as session:
            async with session.begin():
                q = await session.execute(
                    select(m.orders)
                    .where(m.orders.id == order_id)
                    .with_for_update()
                )
                order = q.scalar_one_or_none()
                if not order:
                    return False
                staff = await _load_staff_access(session, by_staff_id or None)
                if not _staff_can_access_city(staff, order.city_id):
                    return False
                if order.status in {m.OrderStatus.CANCELED, m.OrderStatus.CLOSED}:
                    return False
                prev_status = order.status
                order.assigned_master_id = None
                order.status = (
                    m.OrderStatus.GUARANTEE
                    if getattr(order, "order_type", None) == m.OrderType.GUARANTEE
                    else m.OrderStatus.SEARCHING
                )
                order.updated_at = datetime.now(UTC)
                order.version = (order.version or 0) + 1
                order.cancel_reason = None
                session.add(
                    m.order_status_history(
                        order_id=order.id,
                        from_status=prev_status,
                        to_status=m.OrderStatus.SEARCHING,
                        reason="manual_return",
                        changed_by_staff_id=staff.id if staff else None,
                    )
                )
                await session.execute(
                    update(m.offers)
                    .where(
                        (m.offers.order_id == order.id)
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
                    .values(state=m.OfferState.CANCELED, responded_at=func.now())
                )
        return True

    async def cancel(self, order_id: int, reason: str, by_staff_id: int) -> bool:
        async with self._session_factory() as session:
            async with session.begin():
                q = await session.execute(
                    select(m.orders)
                    .where(m.orders.id == order_id)
                    .with_for_update()
                )
                order = q.scalar_one_or_none()
                if not order:
                    return False
                staff = await _load_staff_access(session, by_staff_id or None)
                if not _staff_can_access_city(staff, order.city_id):
                    return False
                if order.status == m.OrderStatus.CANCELED:
                    return True
                prev_status = order.status
                order.assigned_master_id = None
                order.status = m.OrderStatus.CANCELED
                order.updated_at = datetime.now(UTC)
                order.version = (order.version or 0) + 1
                order.cancel_reason = reason
                session.add(
                    m.order_status_history(
                        order_id=order.id,
                        from_status=prev_status,
                        to_status=m.OrderStatus.CANCELED,
                        reason=reason,
                        changed_by_staff_id=staff.id if staff else None,
                    )
                )
                await session.execute(
                    update(m.offers)
                    .where(
                        (m.offers.order_id == order.id)
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
                    .values(state=m.OfferState.CANCELED, responded_at=func.now())
                )
        return True

    async def assign_master(
        self, order_id: int, master_id: int, by_staff_id: int
    ) -> bool:
        async with self._session_factory() as session:
            async with session.begin():
                order_q = await session.execute(
                    select(m.orders)
                    .where(m.orders.id == order_id)
                    .with_for_update()
                )
                order = order_q.scalar_one_or_none()
                if not order:
                    return False
                staff = await _load_staff_access(session, by_staff_id or None)
                if not _staff_can_access_city(staff, order.city_id):
                    return False
                master_q = await session.execute(
                    select(m.masters).where(m.masters.id == master_id)
                )
                master = master_q.scalar_one_or_none()
                if not master:
                    return False
                if master.city_id is not None and master.city_id != order.city_id:
                    return False
                if order.district_id:
                    md_q = await session.execute(
                        select(m.master_districts)
                        .where(
                            (m.master_districts.master_id == master.id)
                            & (m.master_districts.district_id == order.district_id)
                        )
                        .limit(1)
                    )
                    if md_q.first() is None:
                        return False
                prev_status = order.status
                order.assigned_master_id = master.id
                order.status = m.OrderStatus.ASSIGNED
                order.updated_at = datetime.now(UTC)
                order.version = (order.version or 0) + 1
                order.cancel_reason = None
                session.add(
                    m.order_status_history(
                        order_id=order.id,
                        from_status=prev_status,
                        to_status=m.OrderStatus.ASSIGNED,
                        reason="manual_assign",
                        changed_by_staff_id=staff.id if staff else None,
                    )
                )
                await session.execute(
                    update(m.offers)
                    .where(
                        (m.offers.order_id == order.id)
                        & (
                            m.offers.state.in_(
                                [m.OfferState.SENT, m.OfferState.VIEWED]
                            )
                        )
                    )
                    .values(state=m.OfferState.CANCELED, responded_at=func.now())
                )
        return True



@dataclass(frozen=True)
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
                        m.orders.order_type,
                        m.orders.dist_escalated_logist_at,
                        m.orders.dist_escalated_admin_at,
                    )
                    .where(m.orders.id == order_id)
                    .with_for_update()
                )
                data = order_q.first()
                if not data:
                    return False, AutoAssignResult(
                        "Р—Р°СЏРІРєР° РЅРµ РЅР°Р№РґРµРЅР°",
                        code="not_found",
                    )

                staff = await _load_staff_access(session, by_staff_id or None)
                if not _staff_can_access_city(staff, data.city_id):
                    return False, AutoAssignResult(
                        "РќРµРґРѕСЃС‚Р°С‚РѕС‡РЅРѕ РїСЂР°РІ РґР»СЏ РіРѕСЂРѕРґР°",
                        code="forbidden",
                    )

                status_enum = _coerce_order_status(getattr(data, "status", None))
                logistic_mark = getattr(data, "dist_escalated_logist_at", None)

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
                                reason=f"{dw.ESC_REASON_LOGIST}:no_district",
                            )
                        )
                    message = dw.log_skip_no_district(order_id)
                    _push_dist_log(message, level="WARN")
                    return False, AutoAssignResult(
                        "РќРµР»СЊР·СЏ Р·Р°РїСѓСЃС‚РёС‚СЊ Р°РІС‚Рѕ: РЅРµ РІС‹Р±СЂР°РЅ СЂР°Р№РѕРЅ. Р—Р°СЏРІРєР° РїРµСЂРµРґР°РЅР° Р»РѕРіРёСЃС‚Сѓ.",
                        code="no_district",
                    )

                category = getattr(data, "category", None)
                skill_code = dw._skill_code_for_category(category)
                if skill_code is None:
                    message = dw.log_skip_no_category(order_id, category)
                    _push_dist_log(message, level="WARN")
                    return False, AutoAssignResult(
                        "РљР°С‚РµРіРѕСЂРёСЏ Р·Р°РєР°Р·Р° РЅРµ РїРѕРґРґРµСЂР¶РёРІР°РµС‚СЃСЏ РґР»СЏ Р°РІС‚РѕРЅР°Р·РЅР°С‡РµРЅРёСЏ",
                        code="no_category",
                    )

                order_type = getattr(data, "order_type", None)
                is_guarantee = False
                if status_enum is m.OrderStatus.GUARANTEE:
                    is_guarantee = True
                elif order_type is not None:
                    try:
                        is_guarantee = str(order_type) == m.OrderType.GUARANTEE.value
                    except AttributeError:
                        is_guarantee = str(order_type).upper() == "GUARANTEE"

                cfg = await dw._load_config(session)  # type: ignore[attr-defined]
                current_round = await dw.current_round(session, order_id)
                if current_round >= cfg.rounds:
                    return False, AutoAssignResult(
                        "Р›РёРјРёС‚ Р°РІС‚РѕРјР°С‚РёС‡РµСЃРєРёС… РїРѕРїС‹С‚РѕРє РёСЃС‡РµСЂРїР°РЅ",
                        code="rounds_exhausted",
                    )

                candidates = await dw.candidate_rows(
                    session=session,
                    order_id=order_id,
                    city_id=data.city_id,
                    district_id=data.district_id,
                    preferred_master_id=data.preferred_master_id,
                    skill_code=skill_code,
                    limit=50,
                    force_preferred_first=is_guarantee,
                )

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
                    if pref_id is not None and int(candidates[0]["mid"]) == pref_id:
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
                    sent = await dw.send_offer(
                        session,
                        order_id,
                        master_id,
                        next_round,
                        cfg.sla_seconds,
                    )
                    if not sent:
                        conflict = (
                            f"[dist] order={order_id} race_conflict: offer exists for mid={master_id}"
                        )
                        _push_dist_log(conflict, level="WARN")
                        return False, AutoAssignResult(
                            "РќРµ СѓРґР°Р»РѕСЃСЊ РѕС‚РїСЂР°РІРёС‚СЊ РѕС„С„РµСЂ РјР°СЃС‚РµСЂСѓ",
                            code="offer_conflict",
                        )

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
                    return True, AutoAssignResult(
                        message=(
                            f"РћС„С„РµСЂ РѕС‚РїСЂР°РІР»РµРЅ РјР°СЃС‚РµСЂСѓ {master_id} РґРѕ {deadline.isoformat()}"
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
                            reason=f"{dw.ESC_REASON_LOGIST}:no_candidates",
                        )
                    )

                _push_dist_log(dw.log_escalate(order_id), level="WARN")
                return False, AutoAssignResult(
                    "РљР°РЅРґРёРґР°С‚РѕРІ РЅРµС‚ вЂ” СЌСЃРєР°Р»Р°С†РёСЏ",
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
                        m.orders.order_type,
                    )
                    .where(m.orders.id == order_id)
                    .with_for_update()
                )
                order = order_row.first()
                if not order:
                    return False, "Р—Р°СЏРІРєР° РЅРµ РЅР°Р№РґРµРЅР°"

                staff = await _load_staff_access(session, by_staff_id or None)
                if not _staff_can_access_city(staff, order.city_id):
                    return False, "РќРµС‚ РґРѕСЃС‚СѓРїР° Рє РіРѕСЂРѕРґСѓ"

                status = getattr(order, "status", None)
                allowed_statuses = {
                    m.OrderStatus.SEARCHING,
                    m.OrderStatus.GUARANTEE,
                }
                status_enum = (
                    status if isinstance(status, m.OrderStatus) else m.OrderStatus(str(status))
                    if status is not None
                    else m.OrderStatus.SEARCHING
                )
                if status_enum not in allowed_statuses:
                    return False, "Р—Р°СЏРІРєР° РЅРµ РІ РїРѕРёСЃРєРµ"

                category = getattr(order, "category", None)
                skill_code = dw._skill_code_for_category(category)
                if skill_code is None:
                    return False, "РљР°С‚РµРіРѕСЂРёСЏ Р·Р°СЏРІРєРё РЅРµ РїРѕРґРґРµСЂР¶РёРІР°РµС‚СЃСЏ"

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
                    return False, "РњР°СЃС‚РµСЂ РЅРµ РЅР°Р№РґРµРЅ"
                if master.city_id != order.city_id:
                    return False, "РњР°СЃС‚РµСЂ СЂР°Р±РѕС‚Р°РµС‚ РІ РґСЂСѓРіРѕРј РіРѕСЂРѕРґРµ"
                if not master.is_active or master.is_blocked or not master.verified:
                    return False, "РњР°СЃС‚РµСЂ РЅРµРґРѕСЃС‚СѓРїРµРЅ"

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
                        return False, "РњР°СЃС‚РµСЂ РЅРµ РѕР±СЃР»СѓР¶РёРІР°РµС‚ СЂР°Р№РѕРЅ"

                skill_row = await session.execute(
                    select(m.master_skills.id)
                    .join(m.skills, m.master_skills.skill_id == m.skills.id)
                    .where(
                        (m.master_skills.master_id == master_id)
                        & (m.skills.code == skill_code)
                        & (m.skills.is_active == True)
                    )
                    .limit(1)
                )
                if skill_row.first() is None:
                    return False, "РЈ РјР°СЃС‚РµСЂР° РЅРµС‚ РЅСѓР¶РЅРѕРіРѕ РЅР°РІС‹РєР°"

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
                    return False, "РћС„С„РµСЂ СѓР¶Рµ РѕС‚РїСЂР°РІР»РµРЅ СЌС‚РѕРјСѓ РјР°СЃС‚РµСЂСѓ"

                cfg = await dw._load_config(session)
                current_round = await dw.current_round(session, order_id)
                round_number = (current_round or 0) + 1
                sent = await dw.send_offer(
                    session,
                    order_id,
                    master_id,
                    round_number,
                    cfg.sla_seconds,
                )
                if not sent:
                    return False, "РќРµ СѓРґР°Р»РѕСЃСЊ РѕС‚РїСЂР°РІРёС‚СЊ РѕС„С„РµСЂ"

                await session.execute(
                    update(m.orders)
                    .where(m.orders.id == order_id)
                    .values(
                        dist_escalated_logist_at=None,
                        dist_escalated_admin_at=None,
                    )
                )
        return True, "РћС„С„РµСЂ РѕС‚РїСЂР°РІР»РµРЅ"



class DBMastersService:
    def __init__(self, session_factory=SessionLocal) -> None:
        self._session_factory = session_factory

    async def list_masters(
        self,
        group: str,
        *,
        city_ids: Optional[Iterable[int]],
        page: int,
        page_size: int,
        search: Optional[str] = None,
    ) -> tuple[list[MasterListItem], bool]:
        group_key = group.lower()
        filters: list[Any] = []
        if city_ids is not None:
            ids = [int(cid) for cid in city_ids]
            if not ids:
                return [], False
            filters.append(m.masters.city_id.in_(ids))
        if search:
            like = f"%{search.lower()}%"
            filters.append(
                func.lower(m.masters.full_name).like(like)
                | func.lower(func.coalesce(m.masters.phone, '')).like(like)
            )
        if group_key == "pending":
            filters.append(m.masters.moderation_status == m.ModerationStatus.PENDING)
        elif group_key == "approved":
            filters.append(m.masters.moderation_status == m.ModerationStatus.APPROVED)
            filters.append(m.masters.is_blocked.is_(False))
        elif group_key == "blocked":
            filters.append(m.masters.is_blocked.is_(True))
        else:
            filters.append(m.masters.moderation_status == m.ModerationStatus.APPROVED)

        offset = max(page - 1, 0) * page_size
        async with self._session_factory() as session:
            stmt = (
                select(
                    m.masters.id,
                    m.masters.full_name,
                    m.masters.phone,
                    m.cities.name.label('city_name'),
                    m.masters.moderation_status,
                    m.masters.verified,
                    m.masters.is_active,
                    m.masters.is_blocked,
                    m.masters.created_at,
                )
                .select_from(m.masters)
                .join(m.cities, m.masters.city_id == m.cities.id, isouter=True)
                .where(*filters)
                .order_by(m.masters.created_at.desc())
                .offset(offset)
                .limit(page_size + 1)
            )
            rows = await session.execute(stmt)
            fetched = rows.all()
        has_next = len(fetched) > page_size
        items: list[MasterListItem] = []
        for row in fetched[:page_size]:
            created_at_local = _format_created_at(row.created_at)
            moderation_status = (
                row.moderation_status.value
                if hasattr(row.moderation_status, 'value')
                else str(row.moderation_status)
            )
            items.append(
                MasterListItem(
                    id=int(row.id),
                    full_name=row.full_name or f"РњР°СЃС‚РµСЂ #{row.id}",
                    phone=row.phone,
                    city_name=row.city_name,
                    moderation_status=moderation_status,
                    verified=bool(row.verified),
                    is_active=bool(row.is_active),
                    is_blocked=bool(row.is_blocked),
                    created_at_local=created_at_local,
                )
            )
        return items, has_next

    async def list_wait_pay_recipients(self) -> list[WaitPayRecipient]:
        async with self._session_factory() as session:
            rows = await session.execute(
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
            row = await session.execute(
                select(m.masters, m.cities.name.label('city_name'))
                .join(m.cities, m.masters.city_id == m.cities.id, isouter=True)
                .where(m.masters.id == master_id)
            )
            result = row.first()
            if not result:
                return None
            master: m.masters = result.masters
            city_name = result.city_name

            district_rows = await session.execute(
                select(m.districts.name)
                .join(
                    m.master_districts,
                    m.master_districts.district_id == m.districts.id,
                )
                .where(m.master_districts.master_id == master.id)
                .order_by(m.districts.name)
            )
            district_names = tuple(dr[0] for dr in district_rows)

            skill_rows = await session.execute(
                select(m.skills.name)
                .join(
                    m.master_skills,
                    m.master_skills.skill_id == m.skills.id,
                )
                .where(m.master_skills.master_id == master.id)
                .order_by(m.skills.name)
            )
            skill_names = tuple(sr[0] for sr in skill_rows)

            doc_rows = await session.execute(
                select(
                    m.attachments.id,
                    m.attachments.file_type,
                    m.attachments.file_id,
                    m.attachments.file_name,
                    m.attachments.caption,
                )
                .where(
                    (m.attachments.entity_type == m.AttachmentEntity.MASTER)
                    & (m.attachments.entity_id == master.id)
                )
                .order_by(m.attachments.created_at.asc())
            )
            documents = tuple(
                MasterDocument(
                    id=int(doc.id),
                    file_type=str(doc.file_type),
                    file_id=doc.file_id,
                    file_name=doc.file_name,
                    caption=doc.caption,
                )
                for doc in doc_rows
            )

            moderation_status = (
                master.moderation_status.value
                if hasattr(master.moderation_status, 'value')
                else str(master.moderation_status)
            )
            shift_status = (
                master.shift_status.value
                if getattr(master, 'shift_status', None) is not None
                else 'UNKNOWN'
            )
            payout_method = (
                master.payout_method.value
                if getattr(master, 'payout_method', None) is not None
                else None
            )
            created_at_local = _format_created_at(master.created_at)
            updated_at_local = _format_datetime_local(master.updated_at) or created_at_local
            blocked_at_local = _format_datetime_local(master.blocked_at)

            return MasterDetail(
                id=master.id,
                full_name=master.full_name,
                phone=master.phone,
                city_id=master.city_id,
                city_name=city_name,
                rating=float(master.rating or 0),
                has_vehicle=bool(getattr(master, 'has_vehicle', False)),
                is_active=bool(master.is_active),
                is_blocked=bool(master.is_blocked),
                blocked_reason=master.blocked_reason,
                blocked_at_local=blocked_at_local,
                moderation_status=moderation_status,
                moderation_note=getattr(master, 'moderation_note', None),
                verified=bool(master.verified),
                is_on_shift=bool(master.is_on_shift),
                shift_status=shift_status,
                payout_method=payout_method,
                payout_data=dict(master.payout_data or {}),
                referral_code=master.referral_code,
                referred_by_master_id=master.referred_by_master_id,
                current_limit=getattr(master, 'max_active_orders_override', None),
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
        limit = page_size + 1
        async with self._session_factory() as session:
            order_q = await session.execute(
                select(
                    m.orders.city_id,
                    m.orders.district_id,
                    m.orders.preferred_master_id,
                    m.orders.category,
                    m.orders.status,
                    m.orders.order_type,
                ).where(m.orders.id == order_id)
            )
            order_row = order_q.first()
            if not order_row or order_row.district_id is None:
                return [], False
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
),
avg7 AS (
  SELECT assigned_master_id AS mid, AVG(total_price)::numeric(10,2) AS avg_check
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
                    cid=order_row.city_id,
                    did=order_row.district_id,
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
        for row in result_rows:
            data = dict(row)
            mid = int(data["mid"])
            max_limit = int(data["max_limit"] or global_limit)
            active_cnt = int(data["active_cnt"] or 0)
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


    async def list_wait_pay_recipients(self) -> list[WaitPayRecipient]:
        async with self._session_factory() as session:
            rows = await session.execute(
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
                        full_name=full_name or f"РњР°СЃС‚РµСЂ #{int(master_id)}",
                    )
                )
        return recipients

    async def approve_master(self, master_id: int, by_staff_id: int) -> bool:
        async with self._session_factory() as session:
            async with session.begin():
                result = await session.execute(
                    update(m.masters)
                    .where(m.masters.id == master_id)
                    .values(
                        moderation_status=m.ModerationStatus.APPROVED,
                        moderation_note=None,
                        verified=True,
                        is_active=True,
                        updated_at=datetime.now(UTC),
                    )
                    .returning(m.masters.id)
                )
                return result.first() is not None

    async def reject_master(
        self, master_id: int, *, reason: str, by_staff_id: int
    ) -> bool:
        async with self._session_factory() as session:
            async with session.begin():
                result = await session.execute(
                    update(m.masters)
                    .where(m.masters.id == master_id)
                    .values(
                        moderation_status=m.ModerationStatus.REJECTED,
                        moderation_note=reason,
                        verified=False,
                        is_active=False,
                        updated_at=datetime.now(UTC),
                    )
                    .returning(m.masters.id)
                )
                return result.first() is not None

    async def set_master_active(self, master_id: int, *, is_active: bool) -> bool:
        async with self._session_factory() as session:
            async with session.begin():
                result = await session.execute(
                    update(m.masters)
                    .where(m.masters.id == master_id)
                    .values(is_active=is_active, updated_at=datetime.now(UTC))
                    .returning(m.masters.id)
                )
                return result.first() is not None

    async def block_master(
        self, master_id: int, *, reason: str, by_staff_id: int
    ) -> bool:
        async with self._session_factory() as session:
            async with session.begin():
                result = await session.execute(
                    update(m.masters)
                    .where(m.masters.id == master_id)
                    .values(
                        is_blocked=True,
                        blocked_reason=reason,
                        blocked_at=datetime.now(UTC),
                        updated_at=datetime.now(UTC),
                    )
                    .returning(m.masters.id)
                )
                return result.first() is not None

    async def unblock_master(self, master_id: int, *, by_staff_id: int) -> bool:
        async with self._session_factory() as session:
            async with session.begin():
                result = await session.execute(
                    update(m.masters)
                    .where(m.masters.id == master_id)
                    .values(
                        is_blocked=False,
                        blocked_reason=None,
                        blocked_at=None,
                        updated_at=datetime.now(UTC),
                    )
                    .returning(m.masters.id)
                )
                return result.first() is not None

    async def set_master_limit(
        self, master_id: int, *, limit: Optional[int]
    ) -> bool:
        async with self._session_factory() as session:
            async with session.begin():
                result = await session.execute(
                    update(m.masters)
                    .where(m.masters.id == master_id)
                    .values(max_active_orders_override=limit)
                    .returning(m.masters.id)
                )
                return result.first() is not None

    async def delete_master(self, master_id: int) -> bool:
        async with self._session_factory() as session:
            async with session.begin():
                result = await session.execute(
                    delete(m.masters).where(m.masters.id == master_id).returning(m.masters.id)
                )
                return result.first() is not None
class DBFinanceService:
    def __init__(self, session_factory=SessionLocal) -> None:
        self._session_factory = session_factory

    async def list_commissions(
        self,
        segment: str,
        *,
        page: int,
        page_size: int,
        city_ids: Optional[Iterable[int]],
    ) -> tuple[list[CommissionListItem], bool]:
        status_map = {
            "aw": [
                m.CommissionStatus.WAIT_PAY.value,
                m.CommissionStatus.REPORTED.value,
            ],
            "pd": [m.CommissionStatus.APPROVED.value],
            "ov": [m.CommissionStatus.OVERDUE.value],
        }
        statuses = status_map.get(segment, [m.CommissionStatus.WAIT_PAY.value])
        offset = max(page - 1, 0) * page_size
        async with self._session_factory() as session:
            stmt = (
                select(
                    m.commissions.id,
                    m.commissions.order_id,
                    m.commissions.amount,
                    m.commissions.status,
                    m.commissions.deadline_at,
                    m.masters.full_name,
                    m.masters.id.label("master_id"),
                    m.orders.city_id,
                )
                .select_from(m.commissions)
                .join(m.orders, m.orders.id == m.commissions.order_id)
                .join(m.masters, m.masters.id == m.commissions.master_id, isouter=True)
                .where(m.commissions.status.in_(statuses))
                .order_by(m.commissions.created_at.desc())
                .offset(offset)
                .limit(page_size + 1)
            )
            if city_ids is not None:
                ids = [int(cid) for cid in city_ids]
                if not ids:
                    return [], False
                stmt = stmt.where(m.orders.city_id.in_(ids))
            rows = await session.execute(stmt)
            fetched = rows.all()
        has_next = len(fetched) > page_size
        items: list[CommissionListItem] = []
        for row in fetched[:page_size]:
            deadline = _format_created_at(row.deadline_at)
            items.append(
                CommissionListItem(
                    id=row.id,
                    order_id=row.order_id,
                    master_id=row.master_id,
                    master_name=row.full_name,
                    status=row.status,
                    amount=Decimal(row.amount or 0),
                    deadline_at_local=deadline if deadline else None,
                )
            )
        return items, has_next

    async def list_wait_pay_recipients(self) -> list[WaitPayRecipient]:
        async with self._session_factory() as session:
            rows = await session.execute(
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

    async def get_commission_detail(
        self, commission_id: int
    ) -> Optional[CommissionDetail]:
        async with self._session_factory() as session:
            stmt = (
                select(m.commissions, m.orders, m.masters)
                .join(m.orders, m.orders.id == m.commissions.order_id)
                .join(m.masters, m.masters.id == m.commissions.master_id, isouter=True)
                .where(m.commissions.id == commission_id)
            )
            row = await session.execute(stmt)
            result = row.first()
            if not result:
                return None
            commission, order, master = result
            attachments_rows = (
                await session.execute(
                    select(
                        m.attachments.id,
                        m.attachments.file_type,
                        m.attachments.file_id,
                        m.attachments.file_name,
                        m.attachments.caption,
                    )
                    .where(
                        (m.attachments.entity_type == m.AttachmentEntity.COMMISSION)
                        & (m.attachments.entity_id == commission.id)
                    )
                    .order_by(m.attachments.created_at.asc())
                )
            ).all()
            attachments = tuple(
                CommissionAttachment(
                    id=int(att.id),
                    file_type=str(getattr(att.file_type, 'value', att.file_type)),
                    file_id=att.file_id,
                    file_name=att.file_name,
                    caption=att.caption,
                )
                for att in attachments_rows
            )
            deadline = _format_created_at(commission.deadline_at)
            created_at = _format_created_at(commission.created_at)
            paid_reported = _format_created_at(commission.paid_reported_at)
            paid_approved = _format_created_at(commission.paid_approved_at)
            snapshot = commission.pay_to_snapshot or {}
            methods = tuple(
                PAYMENT_METHOD_LABELS.get(str(meth), str(meth))
                for meth in snapshot.get("methods", [])
                if str(meth)
            )
            snapshot_map: dict[str, Optional[str]] = {
                "card_last4": snapshot.get("card_number_last4"),
                "card_holder": snapshot.get("card_holder"),
                "card_bank": snapshot.get("card_bank"),
                "sbp_phone": snapshot.get("sbp_phone_masked"),
                "sbp_bank": snapshot.get("sbp_bank"),
                "other_text": snapshot.get("other_text"),
                "comment": snapshot.get("comment"),
                "qr_file_id": snapshot.get("sbp_qr_file_id"),
            }
            master_phone = getattr(master, "phone", None) if master else None
            return CommissionDetail(

                id=commission.id,
                order_id=commission.order_id,
                master_id=commission.master_id,
                master_name=getattr(master, "full_name", None) if master else None,
                master_phone=master_phone,
                status=commission.status.value
                if hasattr(commission.status, "value")
                else str(commission.status),
                amount=Decimal(commission.amount or 0),
                rate=Decimal(commission.rate or commission.percent or 0),
                deadline_at_local=deadline or None,
                created_at_local=created_at or "",
                paid_reported_at_local=paid_reported or None,
                paid_approved_at_local=paid_approved or None,
                paid_amount=Decimal(commission.paid_amount or 0)
                if commission.paid_amount is not None
                else None,
                has_checks=bool(commission.has_checks),
                snapshot_methods=methods,
                snapshot_data=snapshot_map,
                attachments=attachments,
            )

    async def approve(self, commission_id: int, *, paid_amount: Decimal, by_staff_id: int) -> bool:
        paid_amount = Decimal(str(paid_amount)).quantize(Decimal('0.01'))
        async with self._session_factory() as session:
            async with session.begin():
                row = await session.execute(
                    select(m.commissions, m.orders)
                    .join(m.orders, m.orders.id == m.commissions.order_id)
                    .where(m.commissions.id == commission_id)
                    .with_for_update()
                )
                result = row.first()
                if not result:
                    return False
                commission_row, order_row = result
                await session.execute(
                    update(m.commissions)
                    .where(m.commissions.id == commission_id)
                    .values(
                        status=m.CommissionStatus.APPROVED,
                        is_paid=True,
                        paid_amount=paid_amount,
                        paid_approved_at=datetime.now(UTC),
                        payment_reference=None,
                    )
                )
                if order_row.status != m.OrderStatus.CLOSED:
                    await session.execute(
                        update(m.orders)
                        .where(m.orders.id == order_row.id)
                        .values(
                            status=m.OrderStatus.CLOSED,
                            updated_at=func.now(),
                            version=order_row.version + 1,
                        )
                    )
                    await session.execute(
                        insert(m.order_status_history).values(
                            order_id=order_row.id,
                            from_status=order_row.status,
                            to_status=m.OrderStatus.CLOSED,
                            changed_by_staff_id=by_staff_id,
                            reason='commission_paid',
                        )
                    )

            await apply_rewards_for_commission(
                session,
                commission_id=commission_id,
                master_id=commission_row.master_id,
                base_amount=paid_amount,
            )
        return True

    async def reject(
        self, commission_id: int, reason: str, by_staff_id: int
    ) -> bool:
        async with self._session_factory() as session:
            async with session.begin():
                await session.execute(
                    update(m.commissions)
                    .where(m.commissions.id == commission_id)
                    .values(
                        status=m.CommissionStatus.WAIT_PAY,
                        is_paid=False,
                        paid_approved_at=None,
                        paid_reported_at=None,
                        paid_amount=None,
                        payment_reference=reason,
                    )
                )
        return True

    async def block_master_for_overdue(
        self, master_id: int, by_staff_id: int
    ) -> bool:
        async with self._session_factory() as session:
            async with session.begin():
                await session.execute(
                    update(m.masters)
                    .where(m.masters.id == master_id)
                    .values(
                        is_blocked=True,
                        is_active=False,
                        blocked_at=datetime.now(UTC),
                        blocked_reason="manual_block_from_finance",
                        updated_at=func.now(),
                    )
                )
        return True


class DBSettingsService:
    def __init__(self, session_factory=SessionLocal) -> None:
        self._session_factory = session_factory

    async def get_channel_settings(self) -> dict[str, Optional[int]]:
        keys = ("alerts_channel_id", "logs_channel_id", "reports_channel_id")
        async with self._session_factory() as session:
            rows = await session.execute(
                select(m.settings.key, m.settings.value).where(m.settings.key.in_(keys))
            )
            result: dict[str, Optional[int]] = {key: None for key in keys}
            for key, value in rows:
                try:
                    result[str(key)] = int(value) if value is not None else None
                except (TypeError, ValueError):
                    result[str(key)] = None
            return result

    async def get_values(self, keys: Sequence[str]) -> dict[str, tuple[str, str]]:
        if not keys:
            return {}
        async with self._session_factory() as session:
            rows = await session.execute(
                select(m.settings.key, m.settings.value, m.settings.value_type).where(
                    m.settings.key.in_(list(keys))
                )
            )
            return {row[0]: (row[1], row[2]) for row in rows}




    async def set_value(self, key: str, value: object, *, value_type: str = "STR") -> None:
        normalized = settings_store._normalize_value_type(value_type)
        payload = settings_store._serialize_value(value, normalized)

        async def _apply(session: AsyncSession) -> None:
            stmt = insert(m.settings).values(key=key, value=payload, value_type=normalized)
            if hasattr(stmt, "on_conflict_do_update"):
                stmt = stmt.on_conflict_do_update(
                    index_elements=[m.settings.key],
                    set_={"value": payload, "value_type": normalized},
                )
                await session.execute(stmt)
            else:
                existing = await session.execute(
                    select(m.settings).where(m.settings.key == key)
                )
                if existing.scalar_one_or_none():
                    await session.execute(
                        update(m.settings)
                        .where(m.settings.key == key)
                        .values(value=payload, value_type=normalized)
                    )
                else:
                    await session.execute(
                        insert(m.settings).values(
                            key=key,
                            value=payload,
                            value_type=normalized,
                        )
                    )

        async with self._session_factory() as session:
            for attempt in range(2):
                try:
                    if session.in_transaction():
                        await _apply(session)
                    else:
                        async with session.begin():
                            await _apply(session)
                except OperationalError as exc:
                    message = str(exc).lower()
                    if "no such table" in message and "settings" in message and attempt == 0:
                        await session.run_sync(
                            lambda sync_session: m.settings.__table__.create(
                                sync_session.connection(), checkfirst=True
                            )
                        )
                        continue
                    raise
                else:
                    break
        settings_store.invalidate_working_window_cache()


    async def get_owner_pay_requisites(self, *, staff_id: int | None = None) -> dict[str, Any]:
        async with self._session_factory() as session:
            if staff_id is not None:
                data = await owner_reqs.fetch_for_staff(session, staff_id)
                if not owner_reqs.is_default(data):
                    return data
            return await owner_reqs.fetch_effective(session)

    async def update_owner_pay_requisites(self, staff_id: int, payload: dict[str, Any]) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                await owner_reqs.update_for_staff(session, staff_id, payload)

