from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timezone, timedelta
from zoneinfo import ZoneInfo
from decimal import Decimal, InvalidOperation
import json
import re
import logging
import secrets
import string
from typing import Any, Iterable, Mapping, Optional, Sequence, Tuple
from types import SimpleNamespace

from sqlalchemy import and_, delete, func, insert, select, text, update, inspect
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from rapidfuzz import fuzz, process
from field_service.config import settings

from field_service.db import models as m
from field_service.db.session import SessionLocal
from field_service.services import distribution_scheduler as dw
from field_service.services.candidates import select_candidates
from field_service.services import live_log
from field_service.services import time_service
from field_service.services import settings_service as settings_store
from field_service.services import owner_requisites_service as owner_reqs
from field_service.services import guarantee_service
from field_service.services.guarantee_service import GuaranteeError
from field_service.services.referral_service import apply_rewards_for_commission
from field_service.data import cities as city_catalog

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
    OrderCategory,
    OrderStatus,
    OrderType,
    StaffAccessCode,
    StaffMember,
    StaffRole,
    StaffUser,
    StreetRef,
    TimeslotOption,
    WaitPayRecipient,
)
from .normalizers import normalize_category, normalize_status

UTC = timezone.utc
logger = logging.getLogger(__name__)
PAYMENT_METHOD_LABELS = {
    "card": "💳 Карта",
    "sbp": "СБП",
    "cash": "Наличные",
}

OWNER_PAY_SETTING_FIELDS: dict[str, tuple[str, str]] = {
    'methods': ('owner_pay_methods_enabled', 'JSON'),
    'card_number': ('owner_pay_card_number', 'STR'),
    'card_holder': ('owner_pay_card_holder', 'STR'),
    'card_bank': ('owner_pay_card_bank', 'STR'),
    'sbp_phone': ('owner_pay_sbp_phone', 'STR'),
    'sbp_bank': ('owner_pay_sbp_bank', 'STR'),
    'sbp_qr_file_id': ('owner_pay_sbp_qr_file_id', 'STR'),
    'other_text': ('owner_pay_other_text', 'STR'),
    'comment_template': ('owner_pay_comment_template', 'STR'),
}

LOCAL_TZ = settings_store.get_timezone()


HAS_STREET_CENTROIDS: bool | None = None
HAS_DISTRICT_CENTROIDS: bool | None = None
HAS_CITY_CENTROIDS: bool | None = None

async def _ensure_centroid_flag(session: AsyncSession, scope: str) -> bool:
    global HAS_STREET_CENTROIDS, HAS_DISTRICT_CENTROIDS, HAS_CITY_CENTROIDS

    flags = {
        'street': 'HAS_STREET_CENTROIDS',
        'district': 'HAS_DISTRICT_CENTROIDS',
        'city': 'HAS_CITY_CENTROIDS',
    }
    column_sets = {
        'street': (m.streets.centroid_lat, m.streets.centroid_lon),
        'district': (m.districts.centroid_lat, m.districts.centroid_lon),
        'city': (m.cities.centroid_lat, m.cities.centroid_lon),
    }

    flag_name = flags[scope]
    current = globals()[flag_name]
    if current is not None:
        return current

    selectors = column_sets[scope]
    try:
        await session.execute(select(*selectors).limit(1))
    except ProgrammingError as exc:
        if _is_column_missing_error(exc):
            globals()[flag_name] = False
            await session.rollback()
            return False
        raise
    else:
        globals()[flag_name] = True
        return True


def _is_column_missing_error(exc: Exception) -> bool:
    original = getattr(exc, "orig", None)
    if original is None:
        return False
    message = str(original).lower()
    return (
        original.__class__.__name__ == "UndefinedColumnError"
        or "undefined column" in message
        or "does not exist" in message
    )

STREET_DUPLICATE_THRESHOLD = 93
STREET_MIN_SCORE = 60



def _normalize_street_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())

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

ACTIVE_ORDER_STATUSES = (
    m.OrderStatus.ASSIGNED,
    m.OrderStatus.EN_ROUTE,
    m.OrderStatus.WORKING,
    m.OrderStatus.PAYMENT,
)

AVG_CHECK_STATUSES = (
    m.OrderStatus.WORKING,
    m.OrderStatus.PAYMENT,
    m.OrderStatus.CLOSED,
)


@dataclass(slots=True)
class _StaffAccess:
    id: int
    role: m.StaffRole
    is_active: bool
    city_ids: frozenset[int]
    full_name: Optional[str] = None


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
        full_name=staff.full_name,
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


def _raw_order_type(entity: Any) -> Any:
    value = getattr(entity, "type", None)
    if value is None:
        value = getattr(entity, "order_type", None)
    return value


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


def _order_type_from_db(value: Any) -> OrderType:
    if value is None:
        return OrderType.NORMAL
    if isinstance(value, OrderType):
        return value
    if isinstance(value, m.OrderType):
        return OrderType(value.value)
    if isinstance(value, str):
        candidate = value.upper().strip()
        try:
            return OrderType(candidate)
        except ValueError:
            return OrderType.NORMAL
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
        
    async def get_by_tg_id_or_username(
        self,
        tg_id: int,
        username: Optional[str] = None,
        update_tg_id: bool = True,
    ) -> Optional[StaffUser]:
        """   Telegram ID  username."""
        if tg_id is None:
            return None
        
        async with self._session_factory() as session:
            # 1.    tg_user_id
            row = await session.execute(
                select(m.staff_users).where(m.staff_users.tg_user_id == tg_id)
            )
            staff = row.scalar_one_or_none()
            
            # 2.     tg_id,   username
            if not staff and username:
                normalized_username = username.lower().lstrip("@")
                row = await session.execute(
                    select(m.staff_users).where(
                        m.staff_users.username == normalized_username
                    )
                )
                staff = row.scalar_one_or_none()
                
                # 3.    username  tg_user_id=NULL - 
                if staff and staff.tg_user_id is None and update_tg_id:
                    #    
                    staff.tg_user_id = tg_id
                    await session.commit()
                    live_log.push(
                        "staff",
                        f"tg_id linked: staff_id={staff.id} username={normalized_username} tg_id={tg_id}"
                    )
            
            if not staff:
                return None
            
            #  
            city_rows = await session.execute(
                select(m.staff_cities.city_id).where(
                    m.staff_cities.staff_user_id == staff.id
                )
            )
            city_ids = frozenset(int(c[0]) for c in city_rows)
            
            return StaffUser(
                id=staff.id,
                tg_id=staff.tg_user_id or tg_id,
                role=_map_staff_role(staff.role),
                is_active=bool(staff.is_active),
                city_ids=city_ids,
                full_name=staff.full_name or "",
                phone=staff.phone or "",
            )
    async def link_username_to_tg_id(
        self,
        username: str,
        tg_user_id: int,
        full_name: Optional[str] = None,
    ) -> Optional[StaffUser]:
        normalized_username = username.lower().lstrip("@")
    
        async with self._session_factory() as session:
            async with session.begin():
                stmt = (
                    select(m.staff_users)
                    .where(
                        m.staff_users.username == normalized_username,
                        m.staff_users.tg_user_id.is_(None)
                    )
                    .with_for_update()
                )
                row = await session.execute(stmt)
                staff = row.scalar_one_or_none()
                
                if not staff:
                    return None
                
                staff.tg_user_id = tg_user_id
                if full_name:
                    staff.full_name = full_name
                
                await session.flush()
                
                city_rows = await session.execute(
                    select(m.staff_cities.city_id).where(
                        m.staff_cities.staff_user_id == staff.id
                    )
                )
                city_ids = frozenset(int(c[0]) for c in city_rows)
                
                live_log.push(
                    "staff",
                    f"username linked: staff_id={staff.id} username={normalized_username} tg_id={tg_user_id}"
                )
        
        return StaffUser(
            id=staff.id,
            tg_id=tg_user_id,
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
        issued_by_staff_id: Optional[int] = None,
        created_by_staff_id: Optional[int] = None,
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
                issuer_id = issued_by_staff_id if issued_by_staff_id is not None else created_by_staff_id
                code_row = m.staff_access_codes(
                    code=code_value,
                    role=db_role,
                    city_id=city_column,
                    issued_by_staff_id=issuer_id,
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
                revoked_at=None,
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
                revoked_at=None,
                is_revoked=bool(code_row.is_revoked),
                comment=code_row.comment,
                created_at=code_row.created_at,
            )

    async def add_staff_direct(
        self,
        *,
        tg_id: Optional[int],
        username: Optional[str],
        role: StaffRole,
        city_ids: Iterable[int],
        created_by_staff_id: int,
    ) -> StaffUser:
        """Create staff user without requiring an access code."""
        if tg_id is None and (username is None or not username.strip()):
            raise ValueError("Either tg_id or username must be provided")

        unique_cities = _sorted_city_tuple(city_ids)
        now = datetime.now(UTC)

        async with self._session_factory() as session:
            async with session.begin():
                if tg_id is not None:
                    existing = await session.execute(
                        select(m.staff_users).where(m.staff_users.tg_user_id == tg_id)
                    )
                    if existing.scalar_one_or_none():
                        raise AccessCodeError("already_staff")

                full_name = (username or "").strip() or (f"User{tg_id}" if tg_id else "Unknown")

                staff_row = m.staff_users(
                    tg_user_id=tg_id,
                    username=username,
                    full_name=full_name,
                    phone="",
                    role=_map_staff_role_to_db(role),
                    is_active=True,
                )
                session.add(staff_row)
                await session.flush()

                if unique_cities:
                    session.add_all(
                        m.staff_cities(staff_user_id=staff_row.id, city_id=cid)
                        for cid in unique_cities
                    )

                cities_label = ", ".join(str(cid) for cid in unique_cities) or "all"
                live_log.push(
                    "staff",
                    (
                        f"staff added direct: id={staff_row.id} tg_id={tg_id} "
                        f"username={username} role={role.value} cities={cities_label} "
                        f"by={created_by_staff_id}"
                    ),
                )

        return StaffUser(
            id=staff_row.id,
            tg_id=tg_id or 0,
            role=role,
            is_active=True,
            city_ids=frozenset(unique_cities),
            full_name=staff_row.full_name or "",
            phone=staff_row.phone or "",
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
                live_log.push('staff', f'access_code used code={code_row.code} staff={staff_row.id}')
            return StaffUser(
                id=staff_row.id,
                tg_id=tg_user_id,
                role=role,
                is_active=True,
                city_ids=frozenset(city_ids),
                full_name=staff_row.full_name or '',
                phone=staff_row.phone or '',
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


    async def list_warranty_orders(
        self,
        *,
        city_ids: Optional[Iterable[int]],
        page: int,
        page_size: int,
    ) -> tuple[list[OrderListItem], bool]:
        """Return orders closed less than 14 days ago with paid commission."""
        offset = max(page - 1, 0) * page_size
        now = datetime.now(UTC)
        warranty_deadline = now - timedelta(days=14)

        city_filter: Optional[list[int]] = None
        if city_ids is not None:
            city_filter = [int(cid) for cid in city_ids]
            if not city_filter:
                return [], False

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
                    m.orders.type.label("order_type"),
                    m.orders.category,
                    m.orders.created_at,
                    m.orders.updated_at,
                    m.orders.assigned_master_id,
                    m.masters.full_name.label("master_name"),
                    m.masters.phone.label("master_phone"),
                    m.commissions.paid_approved_at,
                    func.count(m.attachments.id).label("attachments_count"),
                )
                .select_from(m.orders)
                .join(m.cities, m.orders.city_id == m.cities.id)
                .join(m.commissions, m.commissions.order_id == m.orders.id)
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
                .where(
                    m.orders.status == m.OrderStatus.CLOSED,
                    m.orders.type != m.OrderType.GUARANTEE,
                    m.commissions.paid_approved_at.isnot(None),
                    m.commissions.paid_approved_at >= warranty_deadline,
                )
            )

            if city_filter is not None:
                stmt = stmt.where(m.orders.city_id.in_(city_filter))

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
                    m.orders.type,
                    m.orders.category,
                    m.orders.created_at,
                    m.orders.updated_at,
                    m.orders.assigned_master_id,
                    m.masters.full_name,
                    m.masters.phone,
                    m.commissions.paid_approved_at,
                )
                .order_by(m.commissions.paid_approved_at.desc())
                .offset(offset)
                .limit(page_size + 1)
            )

            rows = await session.execute(stmt)
            fetched = rows.all()
            has_next = len(fetched) > page_size

            items: list[OrderListItem] = []

            for row in fetched[:page_size]:
                days_left = 0
                if row.paid_approved_at:
                    warranty_end = row.paid_approved_at + timedelta(days=14)
                    remaining = warranty_end - now
                    days_left = max(0, remaining.days)

                order_type = _order_type_from_db(row.order_type)
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
                        timeslot_local=f": {days_left} .",
                        master_id=row.assigned_master_id,
                        master_name=row.master_name,
                        master_phone=row.master_phone,
                        has_attachments=bool(row.attachments_count),
                    )
                )

        return items, has_next

    async def list_closed_orders(
        self,
        *,
        city_ids: Optional[Iterable[int]],
        page: int,
        page_size: int,
    ) -> tuple[list[OrderListItem], bool]:
        """Return closed orders outside guarantee window or guarantee type."""
        offset = max(page - 1, 0) * page_size
        now = datetime.now(UTC)
        warranty_deadline = now - timedelta(days=14)

        city_filter: Optional[list[int]] = None
        if city_ids is not None:
            city_filter = [int(cid) for cid in city_ids]
            if not city_filter:
                return [], False

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
                    m.orders.type.label("order_type"),
                    m.orders.category,
                    m.orders.created_at,
                    m.orders.updated_at,
                    m.orders.assigned_master_id,
                    m.masters.full_name.label("master_name"),
                    m.masters.phone.label("master_phone"),
                    m.commissions.paid_approved_at,
                    func.count(m.attachments.id).label("attachments_count"),
                )
                .select_from(m.orders)
                .join(m.cities, m.orders.city_id == m.cities.id)
                .join(
                    m.commissions,
                    m.commissions.order_id == m.orders.id,
                    isouter=True,
                )
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
                .where(
                    m.orders.status == m.OrderStatus.CLOSED,
                    (
                        (
                            (m.orders.type != m.OrderType.GUARANTEE)
                            & (m.commissions.paid_approved_at.isnot(None))
                            & (m.commissions.paid_approved_at < warranty_deadline)
                        )
                        | (m.orders.type == m.OrderType.GUARANTEE)
                        | (m.commissions.paid_approved_at.is_(None))
                    ),
                )
            )

            if city_filter is not None:
                stmt = stmt.where(m.orders.city_id.in_(city_filter))

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
                    m.orders.type,
                    m.orders.category,
                    m.orders.created_at,
                    m.orders.updated_at,
                    m.orders.assigned_master_id,
                    m.masters.full_name,
                    m.masters.phone,
                    m.commissions.paid_approved_at,
                )
                .order_by(m.orders.updated_at.desc())
                .offset(offset)
                .limit(page_size + 1)
            )

            rows = await session.execute(stmt)
            fetched = rows.all()
            has_next = len(fetched) > page_size

            items: list[OrderListItem] = []

            for row in fetched[:page_size]:
                closed_date = _format_datetime_local(row.updated_at) or "-"
                order_type = _order_type_from_db(row.order_type)
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
                        timeslot_local=f": {closed_date}",
                        master_id=row.assigned_master_id,
                        master_name=row.master_name,
                        master_phone=row.master_phone,
                        has_attachments=bool(row.attachments_count),
                    )
                )

        return items, has_next

    async def count_orders_by_sections(
        self,
        city_ids: Optional[Iterable[int]],
    ) -> dict[str, int]:
        """Count orders for queue menu counters."""
        now = datetime.now(UTC)
        warranty_deadline = now - timedelta(days=14)

        city_filter: Optional[list[int]] = None
        if city_ids is not None:
            city_filter = [int(cid) for cid in city_ids]
            if not city_filter:
                return {'queue': 0, 'guarantee': 0, 'closed': 0}

        async with self._session_factory() as session:
            queue_stmt = select(func.count(m.orders.id)).where(
                m.orders.status.in_(
                    [
                        m.OrderStatus.SEARCHING,
                        m.OrderStatus.ASSIGNED,
                        m.OrderStatus.EN_ROUTE,
                        m.OrderStatus.WORKING,
                        m.OrderStatus.PAYMENT,
                        m.OrderStatus.GUARANTEE,
                        m.OrderStatus.DEFERRED,
                    ]
                )
            )
            if city_filter is not None:
                queue_stmt = queue_stmt.where(m.orders.city_id.in_(city_filter))
            queue_count = await session.scalar(queue_stmt) or 0

            warranty_stmt = (
                select(func.count(m.orders.id))
                .select_from(m.orders)
                .join(m.commissions, m.commissions.order_id == m.orders.id)
                .where(
                    m.orders.status == m.OrderStatus.CLOSED,
                    m.orders.type != m.OrderType.GUARANTEE,
                    m.commissions.paid_approved_at.isnot(None),
                    m.commissions.paid_approved_at >= warranty_deadline,
                )
            )
            if city_filter is not None:
                warranty_stmt = warranty_stmt.where(m.orders.city_id.in_(city_filter))
            warranty_count = await session.scalar(warranty_stmt) or 0

            closed_stmt = (
                select(func.count(m.orders.id))
                .select_from(m.orders)
                .join(
                    m.commissions,
                    m.commissions.order_id == m.orders.id,
                    isouter=True,
                )
                .where(
                    m.orders.status == m.OrderStatus.CLOSED,
                    (
                        (
                            (m.orders.type != m.OrderType.GUARANTEE)
                            & (m.commissions.paid_approved_at.isnot(None))
                            & (m.commissions.paid_approved_at < warranty_deadline)
                        )
                        | (m.orders.type == m.OrderType.GUARANTEE)
                        | (m.commissions.paid_approved_at.is_(None))
                    ),
                )
            )
            if city_filter is not None:
                closed_stmt = closed_stmt.where(m.orders.city_id.in_(city_filter))
            closed_count = await session.scalar(closed_stmt) or 0

        return {
            'queue': int(queue_count),
            'guarantee': int(warranty_count),
            'closed': int(closed_count),
        }

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
            matching = city_catalog.match_cities(query)
            if limit is not None and limit > 0:
                matching = matching[:limit]
            if not matching:
                return []
            async with self._session_factory() as session:
                rows = await session.execute(
                    select(m.cities.id, m.cities.name)
                    .where(
                        m.cities.is_active == True,  # noqa: E712
                        m.cities.name.in_(matching),
                    )
                )
                fetched = {row.name: int(row.id) for row in rows}
            return [
                CityRef(id=fetched[name], name=name)
                for name in matching
                if name in fetched
            ]

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
                        m.streets.centroid_lat,
                        m.streets.centroid_lon,
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
                limit=min(limit * 3, len(choices)),
            )
            matches = sorted(matches, key=lambda item: (-item[1], -len(item[0])))
            result: list[StreetRef] = []
            used_ids: set[int] = set()
            used_norms: list[str] = []
            for name, score, _ in matches:
                if score is None or score < STREET_MIN_SCORE:
                    continue
                row = choices[name]
                street_id = int(row.id)
                if street_id in used_ids:
                    continue
                normalized_candidate = _normalize_street_name(name)
                if any(
                    max(
                        fuzz.WRatio(normalized_candidate, existing),
                        fuzz.partial_ratio(normalized_candidate, existing),
                        fuzz.partial_ratio(existing, normalized_candidate),
                    ) >= STREET_DUPLICATE_THRESHOLD
                    for existing in used_norms
                ):
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
                used_ids.add(street_id)
                used_norms.append(normalized_candidate)
                if len(result) >= limit:
                    break
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
            category: Optional[OrderCategory] = None,
            master_id: Optional[int] = None,
            timeslot_date: Optional[date] = None,
        ) -> tuple[list[OrderListItem], bool]:
            offset = max(page - 1, 0) * page_size
            city_filter: Optional[list[int]] = None
            if city_ids is not None:
                city_filter = [int(cid) for cid in city_ids]
                if not city_filter:
                    return [], False
            allowed_statuses = [status.value for status in QUEUE_STATUSES]
            async with self._session_factory() as session:
                category_enum = normalize_category(category)
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
                        m.orders.type.label("order_type"),
                        m.orders.category,
                        m.orders.created_at,
                        m.orders.timeslot_start_utc,
                        m.orders.timeslot_end_utc,
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
                if category_enum:
                    stmt = stmt.where(m.orders.category == category_enum)
                if master_id:
                    stmt = stmt.where(m.orders.assigned_master_id == master_id)
                if timeslot_date:
                    stmt = stmt.where(func.date(m.orders.timeslot_start_utc) == timeslot_date)
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
                        m.orders.type,
                        m.orders.category,
                        m.orders.created_at,
                        m.orders.timeslot_start_utc,
                        m.orders.timeslot_end_utc,
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
                tz_cache: dict[int, ZoneInfo] = {}
                for row in fetched[:page_size]:
                    order_type = _order_type_from_db(row.order_type)
                    tz = tz_cache.get(row.city_id)
                    if tz is None:
                        tz = await self._city_timezone(session, row.city_id)
                        tz_cache[row.city_id] = tz
                    timeslot = time_service.format_timeslot_local(
                        row.timeslot_start_utc,
                        row.timeslot_end_utc,
                        tz=tz,
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

    async def get_card(self, order_id: int, *, city_ids: Optional[Iterable[int]] = None) -> Optional[OrderDetail]:
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
                if city_ids is not None:
                    allowed = tuple(int(c) for c in city_ids)
                    if not allowed:
                        return None
                    stmt = stmt.where(m.orders.city_id.in_(allowed))
                row = await session.execute(stmt)
                data = row.first()
                if not data:
                    return None
                order: m.orders = data.orders
                attachments = await self._load_attachments(session, order.id)
                tz = await self._city_timezone(session, order.city_id)
                timeslot = time_service.format_timeslot_local(
                    order.timeslot_start_utc,
                    order.timeslot_end_utc,
                    tz=tz,
                )
                order_type = _order_type_from_db(_raw_order_type(order))
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
                    lat=float(order.lat) if order.lat is not None else None,
                    lon=float(order.lon) if order.lon is not None else None,
                    company_payment=Decimal(order.company_payment or 0),
                    total_sum=Decimal(order.total_sum or 0),
                    attachments=attachments,
                )

    async def list_status_history(
            self, order_id: int, *, limit: int = 5, city_ids: Optional[Iterable[int]] = None
        ) -> tuple[OrderStatusHistoryItem, ...]:
            async with self._session_factory() as session:
                limited = max(1, limit)
                stmt = (
                    select(
                        m.order_status_history.id,
                        m.order_status_history.from_status,
                        m.order_status_history.to_status,
                        m.order_status_history.reason,
                        m.order_status_history.changed_by_staff_id,
                        m.order_status_history.changed_by_master_id,
                        m.order_status_history.created_at,
                    )
                    .join(m.orders, m.orders.id == m.order_status_history.order_id)
                    .where(m.order_status_history.order_id == order_id)
                    .order_by(m.order_status_history.created_at.desc())
                    .limit(limited)
                )
                if city_ids is not None:
                    allowed = tuple(int(c) for c in city_ids)
                    if not allowed:
                        return tuple()
                    stmt = stmt.where(m.orders.city_id.in_(allowed))
                rows = await session.execute(stmt)
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
            self, order_id: int, attachment_id: int, *, city_ids: Optional[Iterable[int]] = None
        ) -> Optional[OrderAttachment]:
            async with self._session_factory() as session:
                stmt = (
                    select(
                        m.attachments.id,
                        m.attachments.file_type,
                        m.attachments.file_id,
                        m.attachments.file_name,
                        m.attachments.caption,
                    )
                    .select_from(m.attachments)
                    .join(
                        m.orders,
                        and_(
                            m.attachments.entity_type == m.AttachmentEntity.ORDER,
                            m.attachments.entity_id == m.orders.id,
                        ),
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
                if city_ids is not None:
                    allowed = tuple(int(c) for c in city_ids)
                    if not allowed:
                        return None
                    stmt = stmt.where(m.orders.city_id.in_(allowed))
                row = await session.execute(stmt)
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

    @staticmethod
    def _coerce_float(value: Optional[float]) -> Optional[float]:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None


    async def _resolve_order_coordinates(
        self,
        session: AsyncSession,
        *,
        city_id: int,
        district_id: Optional[int],
        street_id: Optional[int],
        raw_lat: Optional[float],
        raw_lon: Optional[float],
    ) -> tuple[Optional[float], Optional[float], Optional[str], Optional[int], Optional[int]]:
        lat = self._coerce_float(raw_lat)
        lon = self._coerce_float(raw_lon)
        resolved_district = district_id
        if lat is not None and lon is not None:
            return lat, lon, "user_location", 100, resolved_district

        street_has_centroids = False
        if street_id:
            street_has_centroids = await _ensure_centroid_flag(session, "street")
            street_columns = [m.streets.district_id]
            if street_has_centroids:
                street_columns.extend([m.streets.centroid_lat, m.streets.centroid_lon])
            try:
                row = await session.execute(
                    select(*street_columns).where(m.streets.id == street_id)
                )
            except ProgrammingError as exc:
                if street_has_centroids and _is_column_missing_error(exc):
                    globals()["HAS_STREET_CENTROIDS"] = False
                    await session.rollback()
                    row = await session.execute(
                        select(m.streets.district_id).where(m.streets.id == street_id)
                    )
                    street_has_centroids = False
                else:
                    raise
            data = row.mappings().first()
            if data is not None:
                district_val = data.get("district_id")
                if resolved_district is None and district_val is not None:
                    resolved_district = int(district_val)
                if street_has_centroids:
                    lat_val = data.get("centroid_lat")
                    lon_val = data.get("centroid_lon")
                    if lat_val is not None and lon_val is not None:
                        return (
                            float(lat_val),
                            float(lon_val),
                            "street_centroid",
                            80,
                            resolved_district,
                        )

        district_has_centroids = False
        if resolved_district is not None:
            district_has_centroids = await _ensure_centroid_flag(session, "district")
            if district_has_centroids:
                try:
                    row = await session.execute(
                        select(
                            m.districts.centroid_lat,
                            m.districts.centroid_lon,
                        ).where(m.districts.id == resolved_district)
                    )
                except ProgrammingError as exc:
                    if _is_column_missing_error(exc):
                        globals()["HAS_DISTRICT_CENTROIDS"] = False
                        await session.rollback()
                        district_has_centroids = False
                    else:
                        raise
                else:
                    data = row.mappings().first()
                    if data:
                        lat_val = data.get("centroid_lat")
                        lon_val = data.get("centroid_lon")
                        if lat_val is not None and lon_val is not None:
                            return (
                                float(lat_val),
                                float(lon_val),
                                "district_centroid",
                                60,
                                resolved_district,
                            )

        city_has_centroids = await _ensure_centroid_flag(session, "city")
        if city_has_centroids:
            try:
                row = await session.execute(
                    select(
                        m.cities.centroid_lat,
                        m.cities.centroid_lon,
                    ).where(m.cities.id == city_id)
                )
            except ProgrammingError as exc:
                if _is_column_missing_error(exc):
                    globals()["HAS_CITY_CENTROIDS"] = False
                    await session.rollback()
                    city_has_centroids = False
                else:
                    raise
            else:
                data = row.mappings().first()
                if data:
                    lat_val = data.get("centroid_lat")
                    lon_val = data.get("centroid_lon")
                    if lat_val is not None and lon_val is not None:
                        return (
                            float(lat_val),
                            float(lon_val),
                            "city_centroid",
                            40,
                            resolved_district,
                        )

        return None, None, None, None, resolved_district

    async def create_order(self, data: NewOrderData) -> int:
            async with self._session_factory() as session:
                async with session.begin():
                    tz = await self._city_timezone(session, data.city_id)
                    _, workday_end = await _workday_window()
                    now_local = datetime.now(timezone.utc).astimezone(tz)
                    current_time = now_local.timetz()
                    if current_time.tzinfo is not None:
                        current_time = current_time.replace(tzinfo=None)
                    normalized_status = normalize_status(data.initial_status)
                    initial_status = normalized_status or m.OrderStatus.SEARCHING
                    status_provided = normalized_status is not None
                    if not status_provided and current_time >= workday_end:
                        initial_status = m.OrderStatus.DEFERRED
                    (
                        resolved_lat,
                        resolved_lon,
                        geocode_provider,
                        geocode_confidence,
                        resolved_district,
                    ) = await self._resolve_order_coordinates(
                        session,
                        city_id=data.city_id,
                        district_id=data.district_id,
                        street_id=data.street_id,
                        raw_lat=data.lat,
                        raw_lon=data.lon,
                    )
                    no_district_flag = bool(data.no_district or resolved_district is None)
                    order = m.orders(
                        city_id=data.city_id,
                        district_id=resolved_district,
                        street_id=data.street_id,
                        house=data.house,
                        apartment=data.apartment,
                        address_comment=data.address_comment,
                        client_name=data.client_name,
                        client_phone=data.client_phone,
                        category=data.category,
                        description=data.description,
                        type=_map_order_type_to_db(data.order_type),
                        timeslot_start_utc=data.timeslot_start_utc,
                        timeslot_end_utc=data.timeslot_end_utc,
                        lat=resolved_lat,
                        lon=resolved_lon,
                        geocode_provider=geocode_provider,
                        geocode_confidence=geocode_confidence,
                        no_district=no_district_flag,
                        preferred_master_id=data.preferred_master_id,
                        guarantee_source_order_id=data.guarantee_source_order_id,
                        company_payment=Decimal(data.company_payment or 0),
                        total_sum=Decimal(data.total_sum or 0),
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
    async def has_active_guarantee(self, source_order_id: int, *, city_ids: Optional[Iterable[int]] = None) -> bool:
            async with self._session_factory() as session:
                stmt = (
                    select(1)
                    .where(m.orders.guarantee_source_order_id == source_order_id)
                    .where(~m.orders.status.in_([m.OrderStatus.CANCELED, m.OrderStatus.CLOSED]))
                    .limit(1)
                )
                if city_ids is not None:
                    allowed = tuple(int(c) for c in city_ids)
                    if not allowed:
                        return False
                    stmt = stmt.where(m.orders.city_id.in_(allowed))
                row = await session.execute(stmt)
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

                    if _raw_order_type(source) == m.OrderType.GUARANTEE:
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
                        if _raw_order_type(order) == m.OrderType.GUARANTEE
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
                    # Cancel any active offers (SENT/VIEWED/ACCEPTED) and log how many were canceled
                    res = await session.execute(
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
                    try:
                        canceled_count = int(getattr(res, "rowcount", 0) or 0)
                    except Exception:
                        canceled_count = 0
                    _push_dist_log(
                        f"[dist] return_to_search order={order.id} canceled_offers={canceled_count}",
                        level="INFO",
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

    async def activate_deferred_order(self, order_id: int, staff_id: int) -> bool:
        """
         DEFERRED   PENDING (  ).
        
        Args:
            order_id: ID 
            staff_id: ID ,   
            
        Returns:
            True  , False   
        """
        async with self._session_factory() as session:
            async with session.begin():
                #    
                q = await session.execute(
                    select(m.orders)
                    .where(m.orders.id == order_id)
                    .with_for_update()
                )
                order = q.scalar_one_or_none()
                if not order:
                    return False
                
                #   
                staff = await _load_staff_access(session, staff_id or None)
                if not _staff_can_access_city(staff, order.city_id):
                    return False
                
                # ,     DEFERRED
                if order.status != m.OrderStatus.DEFERRED:
                    return False
                
                #   PENDING ( SEARCHING  , GUARANTEE  )
                prev_status = order.status
                order_type = _raw_order_type(order)
                if order_type == m.OrderType.GUARANTEE:
                    new_status = m.OrderStatus.GUARANTEE
                else:
                    new_status = m.OrderStatus.PENDING
                
                order.status = new_status
                order.updated_at = datetime.now(UTC)
                order.version = (order.version or 0) + 1
                
                #   
                session.add(
                    m.order_status_history(
                        order_id=order.id,
                        from_status=prev_status,
                        to_status=new_status,
                        reason="activated_by_admin",
                        changed_by_staff_id=staff.id if staff else None,
                    )
                )
                
                #  
                live_log.push(
                    "orders",
                    f"DEFERRED order #{order_id} activated  {new_status.value} by staff #{staff_id}",
                    level="INFO"
                )
        
        #       ( 30 )
        #     PENDING/SEARCHING/GUARANTEE    
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
                                actor_type=m.ActorType.AUTO_DISTRIBUTION,
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

                cfg = await dw._load_config(session)  # type: ignore[attr-defined]
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
                            "    ",
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
                    
                    # CR-2025-10-03-015:   
                    deadline_formatted = _format_datetime_local(deadline) or deadline.strftime("%d.%m %H:%M")
                    
                    return True, AutoAssignResult(
                        message=(
                            f"  \n\n"
                            f"  #{master_id}\n"
                            f" : {deadline_formatted}"
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
                            actor_type=m.ActorType.AUTO_DISTRIBUTION,
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
                    return False, "   "

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
                    return False, "    "

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
                    return False, "   "

                await session.execute(
                    update(m.orders)
                    .where(m.orders.id == order_id)
                    .values(
                        dist_escalated_logist_at=None,
                        dist_escalated_admin_at=None,
                    )
                )
        return True, " "



class DBFinanceService:
    """      ."""
    
    def __init__(self, session_factory=SessionLocal) -> None:
        self._session_factory = session_factory

    async def bulk_approve_commissions(
        self,
        start_date: date,
        end_date: date,
        by_staff_id: int,
        *,
        city_ids: Optional[Iterable[int]] = None,
    ) -> tuple[int, list[str]]:
        """
            .
        
        Args:
            start_date:  
            end_date:   ()
            by_staff_id: ID 
            city_ids:    (RBAC)
        
        Returns:
            ( ,  )
        """
        errors: list[str] = []
        approved_count = 0
        
        async with self._session_factory() as session:
            #    RBAC
            staff = await _load_staff_access(session, by_staff_id)
            if staff is None:
                return 0, ["  "]
            
            #    
            visible_cities = _visible_city_ids_for_staff(staff)
            if visible_cities is not None:
                if city_ids is not None:
                    allowed = frozenset(city_ids) & visible_cities
                else:
                    allowed = visible_cities
            elif city_ids is not None:
                allowed = frozenset(city_ids)
            else:
                allowed = None
            
            #   WAIT_PAY  
            stmt = (
                select(m.commissions.id)
                .join(m.orders, m.commissions.order_id == m.orders.id)
                .where(
                    m.commissions.status == m.CommissionStatus.WAIT_PAY,
                    func.date(m.commissions.created_at) >= start_date,
                    func.date(m.commissions.created_at) <= end_date,
                )
            )
            
            if allowed is not None:
                stmt = stmt.where(m.orders.city_id.in_(allowed))
            
            rows = await session.execute(stmt)
            commission_ids = [row[0] for row in rows]
            
            if not commission_ids:
                return 0, ["   "]
            
            #   
            for comm_id in commission_ids:
                try:
                    async with session.begin():
                        #    
                        comm_stmt = (
                            select(m.commissions)
                            .where(m.commissions.id == comm_id)
                            .with_for_update()
                        )
                        comm_row = await session.execute(comm_stmt)
                        commission = comm_row.scalar_one_or_none()
                        
                        if not commission:
                            errors.append(f" #{comm_id}  ")
                            continue
                        
                        if commission.status != m.CommissionStatus.WAIT_PAY:
                            errors.append(f" #{comm_id}    WAIT_PAY")
                            continue
                        
                        #  
                        commission.status = m.CommissionStatus.PAID
                        commission.approved_by_staff_id = by_staff_id
                        commission.approved_at = datetime.now(UTC)
                        commission.updated_at = datetime.now(UTC)
                        
                        #   
                        try:
                            await apply_rewards_for_commission(session, commission)
                        except Exception as exc:
                            logger.warning(
                                "Failed to apply rewards for commission %s: %s",
                                comm_id,
                                exc,
                            )
                        
                        approved_count += 1
                        
                except Exception as exc:
                    errors.append(f"   #{comm_id}: {exc}")
                    logger.exception("Bulk approve failed for commission %s", comm_id)
        
        return approved_count, errors


class DBMastersService:
    def __init__(self, session_factory=SessionLocal) -> None:
        self._session_factory = session_factory

    async def list_active_skills(self) -> list[dict[str, object]]:
        async with self._session_factory() as session:
            rows = await session.execute(
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
        value = await session.scalar(
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
        await session.execute(
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
            invited_total = int((await session.execute(invited_stmt)).scalar() or 0)

            pending_stmt = (
                select(func.count())
                .select_from(m.masters)
                .where(
                    m.masters.referred_by_master_id == master_id,
                    m.masters.verified.is_(False),
                )
            )
            invited_pending = int((await session.execute(pending_stmt)).scalar() or 0)

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
            rewards_row = (await session.execute(rewards_stmt)).first()
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
            rows = (await session.execute(stmt)).all()

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
            default_limit = await self._get_default_master_limit(session)
            row = await session.execute(
                select(m.masters, m.cities.name.label("city_name"))
                .join(m.cities, m.masters.city_id == m.cities.id, isouter=True)
                .where(m.masters.id == master_id)
            )
            result = row.first()
            if not result:
                return None
            master: m.masters = result.masters
            city_name = result.city_name

            active_orders = await session.scalar(
                select(func.count(m.orders.id)).where(
                    (m.orders.assigned_master_id == master.id)
                    & (m.orders.status.in_(ACTIVE_ORDER_STATUSES))
                )
            ) or 0

            avg_check_value = await session.scalar(
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
                await session.scalar(
                    select(m.orders.id)
                    .where(m.orders.assigned_master_id == master.id)
                    .limit(1)
                )
            )
            has_commissions = bool(
                await session.scalar(
                    select(m.commissions.id)
                    .where(m.commissions.master_id == master.id)
                    .limit(1)
                )
            )

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
                        full_name=full_name or f" #{int(master_id)}",
                    )
                )
        return recipients

    async def approve_master(self, master_id: int, by_staff_id: int) -> bool:
        """Mark a master as approved and log the action."""
        async with self._session_factory() as session:
            async with session.begin():
                result = await session.execute(
                    update(m.masters)
                    .where(m.masters.id == master_id)
                    .values(
                        verified=True,
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
        async with self._session_factory() as session:
            async with session.begin():
                result = await session.execute(
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
        async with self._session_factory() as session:
            async with session.begin():
                result = await session.execute(
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
        async with self._session_factory() as session:
            async with session.begin():
                result = await session.execute(
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
        async with self._session_factory() as session:
            async with session.begin():
                result = await session.execute(
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
        async with self._session_factory() as session:
            async with session.begin():
                row = await session.execute(
                    select(m.masters.tg_user_id).where(m.masters.id == master_id)
                )
                tg_user_id = row.scalar_one_or_none()

                if not tg_user_id:
                    logger.warning(f"Cannot notify master#{master_id}: no tg_user_id")
                    return

                await session.execute(
                    insert(m.notifications_outbox).values(
                        master_id=master_id,
                        event="moderation_update",
                        payload={"message": message},
                    )
                )
                live_log.push("moderation", f"notification queued for master#{master_id}")

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
                            actor_type=m.ActorType.ADMIN,
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

    async def get_owner_pay_snapshot(self) -> dict[str, Any]:
        keys = [setting_key for setting_key, _ in OWNER_PAY_SETTING_FIELDS.values()]
        async with self._session_factory() as session:
            rows = await session.execute(
                select(m.settings.key, m.settings.value, m.settings.value_type).where(
                    m.settings.key.in_(keys)
                )
            )
            raw_values = {row[0]: (row[1], row[2]) for row in rows}
        snapshot: dict[str, Any] = {}
        for field, (setting_key, expected_type) in OWNER_PAY_SETTING_FIELDS.items():
            value, stored_type = raw_values.get(setting_key, (None, expected_type))
            value_type = (stored_type or expected_type).upper()
            if value_type == 'JSON':
                try:
                    parsed = json.loads(value) if value else []
                except (TypeError, json.JSONDecodeError):
                    parsed = []
                snapshot[field] = parsed
            else:
                snapshot[field] = value or ''
        return owner_reqs.ensure_schema(snapshot)

    async def update_owner_pay_snapshot(self, **payload: Any) -> None:
        normalized = owner_reqs.ensure_schema(payload)
        values: dict[str, tuple[object, str]] = {}
        for field, (setting_key, value_type) in OWNER_PAY_SETTING_FIELDS.items():
            values[setting_key] = (normalized.get(field), value_type)
        await settings_store.set_values(values)

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


