"""Staff management service: users, access codes, permissions."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta, time
from typing import Any, Iterable, Optional, Sequence
import json
import secrets
import string

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from field_service.db import models as m
from field_service.db.session import SessionLocal
from field_service.services import live_log
from field_service.services._session_utils import maybe_managed_session
from field_service.config import settings

from ..core.dto import StaffAccessCode, StaffMember, StaffRole, StaffUser, OrderListItem, WaitPayRecipient, OrderType


# Additional dataclass for staff module
@dataclass(slots=True)
class _StaffAccess:
    id: int
    role: m.StaffRole
    is_active: bool
    city_ids: frozenset[int]
    full_name: Optional[str] = None


class AccessCodeError(RuntimeError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason

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

    async def seed_global_admins(self, tg_ids: Sequence[int], *, session: Optional[AsyncSession] = None) -> int:
        unique_ids = sorted({int(tg) for tg in tg_ids if tg})
        if not unique_ids:
            return 0
        
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
        
        async with maybe_managed_session(session) as s:
            total = await s.scalar(select(func.count()).select_from(m.staff_users))
            if total and int(total) > 0:
                return 0
            await s.execute(insert(m.staff_users), payload)
        
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
        *,
        session: Optional[AsyncSession] = None,
    ) -> Optional[StaffUser]:
        """Найти сотрудника по Telegram ID ИЛИ username."""
        if tg_id is None:
            return None
        
        async with maybe_managed_session(session) as s:
            # 1. Пытаемся найти по tg_user_id
            row = await s.execute(
                select(m.staff_users).where(m.staff_users.tg_user_id == tg_id)
            )
            staff = row.scalar_one_or_none()
            
            # 2. Если не нашли по tg_id, пытаемся по username
            if not staff and username:
                normalized_username = username.lower().lstrip("@")
                row = await s.execute(
                    select(m.staff_users).where(
                        m.staff_users.username == normalized_username
                    )
                )
                staff = row.scalar_one_or_none()
                
                # 3. Если нашли по username и tg_user_id=NULL - обновляем
                if staff and staff.tg_user_id is None and update_tg_id:
                    staff.tg_user_id = tg_id
                    await s.flush()  # Используем flush вместо commit
                    live_log.push(
                        "staff",
                        f"tg_id linked: staff_id={staff.id} username={normalized_username} tg_id={tg_id}"
                    )
            
            if not staff:
                return None
            
            # Загружаем города
            city_rows = await s.execute(
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
        *,
        session: Optional[AsyncSession] = None,
    ) -> Optional[StaffUser]:
        normalized_username = username.lower().lstrip("@")
    
        async with maybe_managed_session(session) as s:
            stmt = (
                select(m.staff_users)
                .where(
                    m.staff_users.username == normalized_username,
                    m.staff_users.tg_user_id.is_(None)
                )
                .with_for_update()
            )
            row = await s.execute(stmt)
            staff = row.scalar_one_or_none()
            
            if not staff:
                return None
            
            staff.tg_user_id = tg_user_id
            if full_name:
                staff.full_name = full_name
            
            await s.flush()
            
            city_rows = await s.execute(
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
        self, staff_id: int, city_ids: Iterable[int], *, session: Optional[AsyncSession] = None
    ) -> None:
        normalized = _sorted_city_tuple(city_ids)
        async with maybe_managed_session(session) as s:
            await s.execute(
                delete(m.staff_cities).where(m.staff_cities.staff_user_id == staff_id)
            )
            s.add_all(
                m.staff_cities(staff_user_id=staff_id, city_id=cid)
                for cid in normalized
            )

    async def set_staff_role(self, staff_id: int, role: StaffRole, *, session: Optional[AsyncSession] = None) -> None:
        async with maybe_managed_session(session) as s:
            await s.execute(
                update(m.staff_users)
                .where(m.staff_users.id == staff_id)
                .values(role=_map_staff_role_to_db(role))
            )

    async def set_staff_active(self, staff_id: int, is_active: bool, *, session: Optional[AsyncSession] = None) -> None:
        async with maybe_managed_session(session) as s:
            await s.execute(
                update(m.staff_users)
                .where(m.staff_users.id == staff_id)
                .values(is_active=is_active)
            )

    async def update_staff_profile(
        self, staff_id: int, *, full_name: str, phone: str, username: Optional[str] | None = None, session: Optional[AsyncSession] = None
    ) -> None:
        values: dict[str, Any] = {"full_name": full_name, "phone": phone}
        if username is not None:
            values["username"] = username
        async with maybe_managed_session(session) as s:
            await s.execute(
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
        session: Optional[AsyncSession] = None,
    ) -> StaffAccessCode:
        unique_cities = _sorted_city_tuple(city_ids)
        expires_at_value = expires_at
        ttl_hours = max(0, self._access_code_ttl_hours)
        if expires_at_value is None and ttl_hours > 0:
            expires_at_value = datetime.now(UTC) + timedelta(hours=ttl_hours)
        
        async with maybe_managed_session(session) as s:
            code_value = await self._generate_unique_code(s)
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
            s.add(code_row)
            await s.flush()
            s.add_all(
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
        session: Optional[AsyncSession] = None,
    ) -> StaffUser:
        """Create staff user without requiring an access code."""
        if tg_id is None and (username is None or not username.strip()):
            raise ValueError("Either tg_id or username must be provided")

        unique_cities = _sorted_city_tuple(city_ids)

        async with maybe_managed_session(session) as s:
            if tg_id is not None:
                existing = await s.execute(
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
            s.add(staff_row)
            await s.flush()

            if unique_cities:
                s.add_all(
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
        session: Optional[AsyncSession] = None,
    ) -> StaffUser:
        normalized = (code_value or "").strip().upper()
        if not normalized:
            raise AccessCodeError("invalid_code")
        now = datetime.now(UTC)
        
        async with maybe_managed_session(session) as s:
            code_stmt = (
                select(m.staff_access_codes)
                .where(
                    m.staff_access_codes.code == normalized,
                    m.staff_access_codes.is_revoked == False,
                    m.staff_access_codes.used_at.is_(None),
                )
                .with_for_update()
            )
            code_row = (await s.execute(code_stmt)).scalar_one_or_none()
            if not code_row:
                raise AccessCodeError("invalid_code")
            expires_at = code_row.expires_at
            if expires_at and expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)
            if expires_at and expires_at < now:
                raise AccessCodeError("expired")
            link_map = await _collect_code_cities(s, [code_row.id])
            city_ids = _sorted_city_tuple(
                link_map.get(code_row.id) or ([code_row.city_id] if code_row.city_id else [])
            )
            role = _map_staff_role(code_row.role)
            if role in (StaffRole.CITY_ADMIN, StaffRole.LOGIST) and not city_ids:
                raise AccessCodeError("no_cities")
            existing = await s.execute(
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
            s.add(staff_row)
            await s.flush()
            s.add_all(
                m.staff_cities(staff_user_id=staff_row.id, city_id=cid)
                for cid in city_ids
            )
            await s.execute(
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
                        timeslot_local=f"Гарантия: {days_left} дн.",
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
                        timeslot_local=f"Закрыта: {closed_date}",
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
        self, code_id: int, *, by_staff_id: Optional[int] = None, session: Optional[AsyncSession] = None
    ) -> bool:
        async with maybe_managed_session(session) as s:
            result = await s.execute(
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


