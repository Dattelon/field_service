from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timezone
from decimal import Decimal
import json
import secrets
import string
from typing import Any, Iterable, Mapping, Optional, Sequence, Tuple

from sqlalchemy import and_, delete, func, insert, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from rapidfuzz import fuzz, process
from field_service.config import settings

from field_service.db import models as m
from field_service.db.session import SessionLocal
from field_service.services import distribution_worker as dw
from field_service.services import settings_service as settings_store

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
    OrderListItem,
    OrderType,
    StaffAccessCode,
    StaffMember,
    StaffRole,
    StaffUser,
    StreetRef,
    TimeslotOption,
)

UTC = timezone.utc
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


WORKDAY_START = _parse_env_time(settings.working_hours_start, time(10, 0))
WORKDAY_END = _parse_env_time(settings.working_hours_end, time(20, 0))
LATE_ASAP_THRESHOLD = time(19, 30)

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


def _staff_can_access_city(
    staff: Optional[_StaffAccess], city_id: Optional[int]
) -> bool:
    if city_id is None:
        return False
    if staff is None:
        return True
    if staff.role == m.StaffRole.ADMIN:
        return True
    if hasattr(m.StaffRole, "CITY_ADMIN") and staff.role == getattr(
        m.StaffRole, "CITY_ADMIN"
    ):
        return city_id in staff.city_ids
    return city_id in staff.city_ids

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


_format_created_at(dt: Optional[datetime]) -> str:
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
    def __init__(self, session_factory=SessionLocal) -> None:
        self._session_factory = session_factory

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
                    expires_at=expires_at,
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

    async def list_access_codes(
        self,
        *,
        state: str,
        page: int,
        page_size: int,
    ) -> tuple[list[StaffAccessCode], bool]:
        offset = max(page - 1, 0) * page_size
        async with self._session_factory() as session:
            stmt = select(m.staff_access_codes).order_by(
                m.staff_access_codes.created_at.desc()
            )
            if state == "active":
                stmt = stmt.where(
                    (m.staff_access_codes.is_revoked == False)  # noqa: E712
                    & (m.staff_access_codes.used_at.is_(None))
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

    async def revoke_access_code(self, code_id: int) -> bool:
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
                    .returning(m.staff_access_codes.id)
                )
                row = result.first()
                return row is not None

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
    ) -> tuple[list[OrderListItem], bool]:
        offset = max(page - 1, 0) * page_size
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
                .where(m.orders.status.in_([status.value for status in QUEUE_STATUSES]))
                .group_by(
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
            if city_ids:
                stmt = stmt.where(m.orders.city_id.in_(list(city_ids)))
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
                now_local = datetime.now(LOCAL_TZ)
                current_time = now_local.time()
                initial_status = m.OrderStatus.SEARCHING
                if current_time >= WORKDAY_END:
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
                order.status = m.OrderStatus.SEARCHING
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

class DBDistributionService:
    def __init__(self, session_factory=SessionLocal) -> None:
        self._session_factory = session_factory

    async def assign_auto(self, order_id: int, by_staff_id: int) -> tuple[bool, str]:
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
                    ).where(m.orders.id == order_id)
                )
                data = order_q.first()
                if not data:
                    return False, "Заявка не найдена"
                staff = await _load_staff_access(session, by_staff_id or None)
                if not _staff_can_access_city(staff, data.city_id):
                    return False, "Недостаточно прав для города"
                if data.district_id is None:
                    return False, "Для заявки не выбран район"
                category = getattr(data, "category", None)
                skill_code = dw._skill_code_for_category(category)
                if skill_code is None:
                    return False, "Категория заказа не поддерживается для автоназначения"
                status = getattr(data, "status", None)
                order_type = getattr(data, "order_type", None)
                is_guarantee = False
                if status is not None and str(status) == m.OrderStatus.GUARANTEE.value:
                    is_guarantee = True
                if not is_guarantee and order_type is not None:
                    try:
                        is_guarantee = str(order_type) == m.OrderType.GUARANTEE.value
                    except AttributeError:
                        is_guarantee = str(order_type).upper() == 'GUARANTEE'
                cfg = await dw._load_config(session)  # type: ignore[attr-defined]
                current_round = await dw.current_round(session, order_id)
                if current_round >= cfg.rounds:
                    return False, "Лимит автоматических попыток исчерпан"
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
                if not candidates:
                    return False, "Нет доступных мастеров"
                next_round = current_round + 1
                top = candidates[0]
                ok = await dw.send_offer(
                    session,
                    order_id,
                    int(top["mid"]),
                    next_round,
                    cfg.sla_seconds,
                )
                if not ok:
                    return False, "Не удалось отправить оффер мастеру"
        return True, "Оффер отправлен"


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
                    full_name=row.full_name or f"Мастер #{row.id}",
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
            status = getattr(order_row, "status", None)
            order_type = getattr(order_row, "order_type", None)
            is_guarantee = False
            if status is not None and str(status) == m.OrderStatus.GUARANTEE.value:
                is_guarantee = True
            if not is_guarantee and order_type is not None:
                try:
                    is_guarantee = str(order_type) == m.OrderType.GUARANTEE.value
                except AttributeError:
                    is_guarantee = str(order_type).upper() == 'GUARANTEE'
            candidates = await dw.candidate_rows(
                session=session,
                order_id=order_id,
                city_id=order_row.city_id,
                district_id=order_row.district_id,
                preferred_master_id=order_row.preferred_master_id,
                skill_code=skill_code,
                limit=50,
                force_preferred_first=is_guarantee,
            )
            subset = candidates[start : start + page_size]
            has_next = len(candidates) > start + page_size
            ids = [int(c["mid"]) for c in subset]
            if not ids:
                return [], False
            masters_q = await session.execute(
                select(
                    m.masters.id,
                    m.masters.full_name,
                    m.masters.city_id,
                    m.masters.has_vehicle,
                    m.masters.rating,
                    m.masters.is_on_shift,
                    m.masters.is_active,
                    m.masters.verified,
                ).where(m.masters.id.in_(ids))
            )
            master_map = {row.id: row for row in masters_q}
        briefs: list[MasterBrief] = []
        for cand in subset:
            mid = int(cand["mid"])
            info = master_map.get(mid)
            if not info:
                continue
            briefs.append(
                MasterBrief(
                    id=mid,
                    full_name=info.full_name or f"Мастер #{mid}",
                    city_id=info.city_id,
                    has_car=bool(info.has_vehicle),
                    avg_week_check=float(cand.get("avg_week") or 0),
                    rating_avg=float(info.rating or 0),
                    is_on_shift=bool(info.is_on_shift),
                    is_active=bool(info.is_active),
                    verified=bool(info.verified),
                    in_district=True,
                )
            )
        return briefs, has_next

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
            if city_ids:
                stmt = stmt.where(m.orders.city_id.in_(list(city_ids)))
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
                    file_type=str(att.file_type),
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
            methods = tuple(str(meth) for meth in snapshot.get("methods", []))
            snapshot_map: dict[str, Optional[str]] = {
                key: snapshot.get(key)
                for key in (
                    "card_number",
                    "card_holder",
                    "card_bank",
                    "sbp_phone",
                    "sbp_bank",
                    "sbp_comment",
                    "other_text",
                )
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

    async def approve(self, commission_id: int, by_staff_id: int) -> bool:
        async with self._session_factory() as session:
            async with session.begin():
                await session.execute(
                    update(m.commissions)
                    .where(m.commissions.id == commission_id)
                    .values(
                        status=m.CommissionStatus.APPROVED,
                        is_paid=True,
                        paid_approved_at=datetime.now(UTC),
                    )
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
                        blocked_at=datetime.now(UTC),
                        blocked_reason="manual_block_from_finance",
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
        await settings_store.set_value(key, value, value_type=value_type)


    async def get_owner_pay_snapshot(self) -> dict[str, object]:
        async with self._session_factory() as session:
            row = await session.execute(
                select(m.settings.value).where(m.settings.key == "owner_pay_snapshot")
            )
            snap = row.scalar_one_or_none()
            return snap or {}

    async def update_owner_pay_snapshot(self, **kwargs: object) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                await session.execute(
                    update(m.settings)
                    .where(m.settings.key == "owner_pay_snapshot")
                    .values(value=kwargs, value_type="json")
                )

