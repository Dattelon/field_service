"""Orders service: order management, creation, status changes."""
from __future__ import annotations

from datetime import datetime, timezone, date, timedelta
from decimal import Decimal
from typing import Iterable, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo

from sqlalchemy import and_, func, select, update
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession
from rapidfuzz import fuzz, process

from field_service.config import settings
from field_service.db import models as m
from field_service.db.session import SessionLocal
from field_service.services import (
    guarantee_service,
    live_log,
    operation_logger as oplog,
    time_service,
)
from field_service.services.guarantee_service import GuaranteeError
from field_service.services._session_utils import maybe_managed_session

from ..core.dto import (
    CityRef, DistrictRef, NewOrderData, OrderDetail, OrderCard,
    OrderListItem, OrderAttachment, OrderStatusHistoryItem,
    OrderStatus, StreetRef, WaitPayRecipient, OrderType, OrderCategory,
    DeclinedMasterInfo,
)


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
    _ensure_centroid_flag,
)

# Additional imports for orders module
from field_service.data import cities as city_catalog
from ..utils.normalizers import normalize_category, normalize_status


def _session_tx_id(session: AsyncSession) -> Optional[str]:
    """Best-effort identifier for the current SQLAlchemy transaction."""
    try:
        transaction = session.get_transaction()
        if transaction is None:
            return None
        connection = getattr(transaction, "_connection", None)
        if connection is None:
            return None
        raw = getattr(connection, "connection", None) or getattr(
            connection,
            "_dbapi_connection",
            None,
        )
        return str(raw or connection)
    except Exception:
        return None


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
            self, *, query: Optional[str] = None, limit: int = 20, city_ids: Optional[list[int]] = None
        ) -> list[CityRef]:
            matching = city_catalog.match_cities(query)
            if not matching:
                return []
            async with self._session_factory() as session:
                stmt = select(m.cities.id, m.cities.name).where(
                    m.cities.is_active == True,  # noqa: E712
                    m.cities.name.in_(matching),
                )
                # RBAC: Фильтрация по visible cities для CITY_ADMIN
                if city_ids is not None:
                    stmt = stmt.where(m.cities.id.in_(city_ids))
                rows = await session.execute(stmt)
                fetched = {row.name: int(row.id) for row in rows}
            ordered = [
                CityRef(id=fetched[name], name=name)
                for name in matching
                if name in fetched
            ]
            if limit is not None and limit > 0:
                return ordered[:limit]
            return ordered

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
            order_id: Optional[int] = None,  # P1: Поиск по ID заказа
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
                if order_id:  # P1: Фильтр по ID заказа
                    stmt = stmt.where(m.orders.id == order_id)
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

    async def get_card(self, order_id: int, *, city_ids: Optional[Iterable[int]] = None) -> Optional[OrderCard]:
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
                
                # Load all data
                attachments = await self._load_attachments(session, order.id)
                tz = await self._city_timezone(session, order.city_id)
                timeslot = time_service.format_timeslot_local(
                    order.timeslot_start_utc,
                    order.timeslot_end_utc,
                    tz=tz,
                )
                order_type = _order_type_from_db(_raw_order_type(order))
                
                # Load extended data for OrderCard
                status_history = await self._load_status_history(session, order.id, tz)
                declined_masters = await self._load_declined_masters(session, order.id)
                en_route_at, working_at, payment_at = await self._get_status_timestamps(session, order.id)
                
                # Create OrderDetail fields
                base_fields = dict(
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
                
                # Return OrderCard with extended fields
                return OrderCard(
                    **base_fields,
                    status_history=status_history,
                    declined_masters=declined_masters,
                    en_route_at_local=en_route_at,
                    working_at_local=working_at,
                    payment_at_local=payment_at,
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
                        m.order_status_history.actor_type,
                        m.order_status_history.context,
                        m.order_status_history.created_at,
                        m.staff_users.full_name.label("staff_name"),
                        m.masters.full_name.label("master_name"),
                    )
                    .select_from(m.order_status_history)
                    .join(m.orders, m.orders.id == m.order_status_history.order_id)
                    .outerjoin(m.staff_users, m.order_status_history.changed_by_staff_id == m.staff_users.id)
                    .outerjoin(m.masters, m.order_status_history.changed_by_master_id == m.masters.id)
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
                    # Определяем имя актора
                    actor_name = None
                    if row.staff_name:
                        actor_name = f"Админ: {row.staff_name}"
                    elif row.master_name:
                        actor_name = f"Мастер: {row.master_name}"
                    elif row.actor_type == m.ActorType.AUTO_DISTRIBUTION:
                        actor_name = "Автораспределение"
                    elif row.actor_type == m.ActorType.SYSTEM:
                        actor_name = "Система"
                    
                    items.append(
                        OrderStatusHistoryItem(
                            id=row.id,
                            from_status=row.from_status.value if row.from_status else None,
                            to_status=row.to_status.value if row.to_status else None,
                            reason=row.reason,
                            changed_by_staff_id=row.changed_by_staff_id,
                            changed_by_master_id=row.changed_by_master_id,
                            changed_at_local=_format_created_at(row.created_at) or "",
                            actor_type=row.actor_type.value if row.actor_type else "SYSTEM",
                            actor_name=actor_name,
                            context=dict(row.context) if row.context else {},
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

    async def _load_status_history(
            self, session: AsyncSession, order_id: int, tz: ZoneInfo
        ) -> tuple[OrderStatusHistoryItem, ...]:
            """Load order status change history with detailed context."""
            rows = await session.execute(
                select(
                    m.order_status_history.id,
                    m.order_status_history.from_status,
                    m.order_status_history.to_status,
                    m.order_status_history.reason,
                    m.order_status_history.changed_by_staff_id,
                    m.order_status_history.changed_by_master_id,
                    m.order_status_history.actor_type,
                    m.order_status_history.context,
                    m.order_status_history.created_at,
                    m.staff_users.full_name.label("staff_name"),
                    m.masters.full_name.label("master_name"),
                )
                .select_from(m.order_status_history)
                .outerjoin(m.staff_users, m.order_status_history.changed_by_staff_id == m.staff_users.id)
                .outerjoin(m.masters, m.order_status_history.changed_by_master_id == m.masters.id)
                .where(m.order_status_history.order_id == order_id)
                .order_by(m.order_status_history.created_at.asc())
            )
            items = []
            for row in rows:
                # Определяем имя актора
                actor_name = None
                if row.staff_name:
                    actor_name = f"Админ: {row.staff_name}"
                elif row.master_name:
                    actor_name = f"Мастер: {row.master_name}"
                elif row.actor_type == m.ActorType.AUTO_DISTRIBUTION:
                    actor_name = "Автораспределение"
                elif row.actor_type == m.ActorType.SYSTEM:
                    actor_name = "Система"
                
                items.append(
                    OrderStatusHistoryItem(
                        id=row.id,
                        from_status=row.from_status.value if row.from_status else None,
                        to_status=row.to_status.value if row.to_status else "",
                        reason=row.reason,
                        changed_by_staff_id=row.changed_by_staff_id,
                        changed_by_master_id=row.changed_by_master_id,
                        changed_at_local=_format_created_at(row.created_at) or "",
                        actor_type=row.actor_type.value if row.actor_type else "SYSTEM",
                        actor_name=actor_name,
                        context=dict(row.context) if row.context else {},
                    )
                )
            return tuple(items)

    async def _load_declined_masters(
            self, session: AsyncSession, order_id: int
        ) -> tuple:
            """Load information about masters who declined the order."""
            from ..core.dto import DeclinedMasterInfo
            
            rows = await session.execute(
                select(
                    m.offers.master_id,
                    m.masters.full_name,
                    m.offers.round_number,
                    m.offers.responded_at,
                )
                .select_from(m.offers)
                .join(m.masters, m.offers.master_id == m.masters.id)
                .where(
                    (m.offers.order_id == order_id)
                    & (m.offers.state == m.OfferState.DECLINED)
                )
                .order_by(m.offers.responded_at.asc())
            )
            items = []
            for row in rows:
                items.append(
                    DeclinedMasterInfo(
                        master_id=row.master_id,
                        master_name=row.full_name or f"Мастер {row.master_id}",
                        round_number=row.round_number,
                        declined_at_local=_format_created_at(row.responded_at) or "",
                    )
                )
            return tuple(items)

    async def _get_status_timestamps(
            self, session: AsyncSession, order_id: int
        ) -> tuple[Optional[str], Optional[str], Optional[str]]:
            """Get timestamps for EN_ROUTE, WORKING, and PAYMENT statuses."""
            rows = await session.execute(
                select(
                    m.order_status_history.to_status,
                    m.order_status_history.created_at,
                )
                .where(
                    (m.order_status_history.order_id == order_id)
                    & (
                        m.order_status_history.to_status.in_([
                            m.OrderStatus.EN_ROUTE,
                            m.OrderStatus.WORKING,
                            m.OrderStatus.PAYMENT,
                        ])
                    )
                )
                .order_by(m.order_status_history.created_at.asc())
            )
            
            en_route_at = None
            working_at = None
            payment_at = None
            
            for row in rows:
                timestamp = _format_created_at(row.created_at)
                if row.to_status == m.OrderStatus.EN_ROUTE and en_route_at is None:
                    en_route_at = timestamp
                elif row.to_status == m.OrderStatus.WORKING and working_at is None:
                    working_at = timestamp
                elif row.to_status == m.OrderStatus.PAYMENT and payment_at is None:
                    payment_at = timestamp
            
            return en_route_at, working_at, payment_at

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

    async def create_order(self, data: NewOrderData, *, session: Optional[AsyncSession] = None) -> int:
            request_id = oplog.generate_request_id()
            normalized_initial_status = normalize_status(data.initial_status)
            initial_status_hint = normalized_initial_status or data.initial_status or 'AUTO'
            category_hint = (
                data.category.value if hasattr(data.category, 'value') else data.category or 'UNKNOWN'
            )
            oplog.log_order_creation_start(
                request_id=request_id,
                staff_id=data.created_by_staff_id,
                city_id=data.city_id,
                category=category_hint,
                initial_status=initial_status_hint,
            )
            try:
                async with maybe_managed_session(session) as s:
                        tz = await self._city_timezone(s, data.city_id)
                        _, workday_end = await _workday_window()
                        now_local = datetime.now(timezone.utc).astimezone(tz)
                        current_time = now_local.timetz()
                        if current_time.tzinfo is not None:
                            current_time = current_time.replace(tzinfo=None)
                        initial_status = normalized_initial_status or m.OrderStatus.SEARCHING
                        status_provided = normalized_initial_status is not None
                        if not status_provided and current_time >= workday_end:
                            initial_status = m.OrderStatus.DEFERRED
                        (
                            resolved_lat,
                            resolved_lon,
                            geocode_provider,
                            geocode_confidence,
                            resolved_district,
                        ) = await self._resolve_order_coordinates(
                            s,
                            city_id=data.city_id,
                            district_id=data.district_id,
                            street_id=data.street_id,
                            raw_lat=data.lat,
                            raw_lon=data.lon,
                        )
                        no_district_flag = bool(data.no_district or resolved_district is None)
                        created_staff_id = None
                        if data.created_by_staff_id:
                            staff_row = await s.get(m.staff_users, data.created_by_staff_id)
                            created_staff_id = getattr(staff_row, "id", None)
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
                            created_by_staff_id=created_staff_id,
                            status=initial_status,
                        )
                        s.add(order)
                        await s.flush()
                        if data.attachments:
                            s.add_all(
                                m.attachments(
                                    entity_type=m.AttachmentEntity.ORDER,
                                    entity_id=order.id,
                                    file_type=_attachment_type_from_string(att.file_type),
                                    file_id=att.file_id,
                                    file_unique_id=att.file_unique_id,
                                    file_name=att.file_name,
                                    mime_type=att.mime_type,
                                    caption=att.caption,
                                    uploaded_by_staff_id=created_staff_id,
                                )
                                for att in data.attachments
                            )
                        staff_info = (
                            await _load_staff_access(s, data.created_by_staff_id)
                            if data.created_by_staff_id
                            else None
                        )
                        s.add(
                            m.order_status_history(
                                order_id=order.id,
                                from_status=None,
                                to_status=initial_status,
                                reason='created_by_staff',
                                changed_by_staff_id=created_staff_id,
                                actor_type=m.ActorType.ADMIN,
                                context={
                                    'staff_id': data.created_by_staff_id,
                                    'staff_name': staff_info.full_name if staff_info else None,
                                    'action': 'order_creation',
                                    'initial_status': getattr(initial_status, 'value', str(initial_status)),
                                    'deferred_reason': 'outside_working_hours'
                                    if initial_status == m.OrderStatus.DEFERRED
                                    else None,
                                    'has_preferred_master': data.preferred_master_id is not None,
                                    'is_guarantee': data.order_type == OrderType.GUARANTEE,
                                },
                            )
                        )
                        tx_id = _session_tx_id(s)
                        oplog.log_order_created(
                            request_id=request_id,
                            order_id=order.id,
                            status=order.status,
                            staff_id=data.created_by_staff_id,
                            tx_id=tx_id,
                        )
                        return order.id
            except Exception as exc:
                oplog.log_order_creation_error(
                    request_id=request_id,
                    error=str(exc),
                    staff_id=data.created_by_staff_id,
                )
                raise
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

    async def create_guarantee_order(self, source_order_id: int, by_staff_id: int, *, session: Optional[AsyncSession] = None) -> int:
            async with maybe_managed_session(session) as s:
                    src_query = await s.execute(
                        select(m.orders)
                        .where(m.orders.id == source_order_id)
                        .with_for_update()
                    )
                    source = src_query.scalar_one_or_none()
                    if source is None:
                        raise GuaranteeError("source order not found")

                    staff = await _load_staff_access(s, by_staff_id or None)
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

                    existing = await s.execute(
                        select(m.orders.id)
                        .where(m.orders.guarantee_source_order_id == source_order_id)
                        .where(~m.orders.status.in_([m.OrderStatus.CANCELED, m.OrderStatus.CLOSED]))
                        .limit(1)
                    )
                    if existing.first():
                        raise GuaranteeError("guarantee already exists")

                    created = await guarantee_service.create_from_closed_order(
                        s,
                        source_order_id,
                        source=source,
                        created_by_staff_id=staff.id if staff else None,
                    )
                    return created.id

    async def return_to_search(self, order_id: int, by_staff_id: int, *, session: Optional[AsyncSession] = None) -> bool:
            async with maybe_managed_session(session) as s:
                    q = await s.execute(
                        select(m.orders)
                        .where(m.orders.id == order_id)
                        .with_for_update()
                    )
                    order = q.scalar_one_or_none()
                    if not order:
                        return False
                    staff = await _load_staff_access(s, by_staff_id or None)
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
                    s.add(
                        m.order_status_history(
                            order_id=order.id,
                            from_status=prev_status,
                            to_status=m.OrderStatus.SEARCHING,
                            reason="manual_return",
                            changed_by_staff_id=staff.id if staff else None,
                        )
                    )
                    # Cancel any active offers (SENT/VIEWED/ACCEPTED) and log how many were canceled
                    res = await s.execute(
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

    async def cancel(self, order_id: int, reason: str, by_staff_id: int, *, session: Optional[AsyncSession] = None) -> bool:
            async with maybe_managed_session(session) as s:
                    q = await s.execute(
                        select(m.orders)
                        .where(m.orders.id == order_id)
                        .with_for_update()
                    )
                    order = q.scalar_one_or_none()
                    if not order:
                        return False
                    staff = await _load_staff_access(s, by_staff_id or None)
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
                    s.add(
                        m.order_status_history(
                            order_id=order.id,
                            from_status=prev_status,
                            to_status=m.OrderStatus.CANCELED,
                            reason=reason,
                            changed_by_staff_id=staff.id if staff else None,
                            actor_type=m.ActorType.ADMIN if staff else m.ActorType.SYSTEM,
                            context={
                                "staff_id": staff.id if staff else None,
                                "staff_name": staff.full_name if staff else None,
                                "cancel_reason": reason,
                                "action": "manual_cancel"
                            }
                        )
                    )
                    await s.execute(
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
            self, order_id: int, master_id: int, by_staff_id: int, *, request_id: Optional[str] = None, actor: str = 'ADMIN', session: Optional[AsyncSession] = None
        ) -> bool:
            tracking_id = request_id or oplog.generate_request_id()
            async with maybe_managed_session(session) as s:
                try:
                        order_q = await s.execute(
                            select(m.orders)
                            .where(m.orders.id == order_id)
                            .with_for_update()
                        )
                        order = order_q.scalar_one_or_none()
                        if not order:
                            return False
                        staff = await _load_staff_access(s, by_staff_id or None)
                        if not _staff_can_access_city(staff, order.city_id):
                            return False
                        master_q = await s.execute(
                            select(m.masters).where(m.masters.id == master_id)
                        )
                        master = master_q.scalar_one_or_none()
                        if not master:
                            return False
                        if master.city_id is not None and master.city_id != order.city_id:
                            return False
                        if order.district_id:
                            md_q = await s.execute(
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
                        oplog.log_assign_attempt(
                            request_id=tracking_id,
                            order_id=order.id,
                            old_status=prev_status,
                            new_status=m.OrderStatus.ASSIGNED,
                            master_id=master.id,
                            staff_id=by_staff_id,
                            actor=actor,
                        )
                        order.assigned_master_id = master.id
                        order.status = m.OrderStatus.ASSIGNED
                        order.updated_at = datetime.now(UTC)
                        order.version = (order.version or 0) + 1
                        order.cancel_reason = None

                        master_name = f"{master.last_name} {master.first_name}".strip()

                        s.add(
                            m.order_status_history(
                                order_id=order.id,
                                from_status=prev_status,
                                to_status=m.OrderStatus.ASSIGNED,
                                reason='manual_assign',
                                changed_by_staff_id=staff.id if staff else None,
                                actor_type=m.ActorType.ADMIN,
                                context={
                                    'staff_id': staff.id if staff else None,
                                    'staff_name': staff.full_name if staff else None,
                                    'master_id': master.id,
                                    'master_name': master_name,
                                    'action': 'manual_assignment',
                                    'method': 'admin_override',
                                },
                            )
                        )

                        try:
                            offer_stats = await s.execute(
                                select(
                                    func.max(m.offers.round_number).label('max_round'),
                                    func.count(func.distinct(m.offers.master_id)).label('total_candidates')
                                ).where(m.offers.order_id == order.id)
                            )
                            stats_row = offer_stats.first()

                            now_utc = datetime.now(UTC)
                            time_to_assign = (
                                int((now_utc - order.created_at).total_seconds())
                                if order.created_at
                                else None
                            )

                            s.add(
                                m.distribution_metrics(
                                    order_id=order.id,
                                    master_id=master.id,
                                    round_number=stats_row.max_round if stats_row and stats_row.max_round else 0,
                                    candidates_count=stats_row.total_candidates if stats_row and stats_row.total_candidates else 0,
                                    time_to_assign_seconds=time_to_assign,
                                    preferred_master_used=(master.id == order.preferred_master_id),
                                    was_escalated_to_logist=(order.dist_escalated_logist_at is not None),
                                    was_escalated_to_admin=(order.dist_escalated_admin_at is not None),
                                    city_id=order.city_id,
                                    district_id=order.district_id,
                                    category=order.category,
                                    order_type=order.type,
                                    metadata_json={
                                        'assigned_via': 'admin_manual',
                                        'from_status': prev_status.value if hasattr(prev_status, 'value') else str(prev_status),
                                        'staff_id': staff.id if staff else None,
                                    },
                                )
                            )
                        except Exception:
                            pass

                        offer_result = await s.execute(
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
                        rows_affected = int(getattr(offer_result, 'rowcount', 0) or 0)
                        oplog.log_assign_sql_result(
                            request_id=tracking_id,
                            order_id=order.id,
                            operation='cancel_offers',
                            rows_affected=rows_affected,
                        )
                        tx_id = _session_tx_id(s)
                        oplog.log_assign_success(
                            request_id=tracking_id,
                            order_id=order.id,
                            master_id=master.id,
                            old_status=prev_status,
                            new_status=order.status,
                            staff_id=by_staff_id,
                            tx_id=tx_id,
                        )
                        return True
                except Exception as exc:
                    oplog.log_assign_error(
                        request_id=tracking_id,
                        order_id=order_id,
                        error=str(exc),
                        staff_id=by_staff_id,
                        callback_data=None,
                    )
                    raise
    async def activate_deferred_order(self, order_id: int, staff_id: int, *, session: Optional[AsyncSession] = None) -> bool:
        """
        Перевести DEFERRED заказ в SEARCHING (активировать поиск мастера).
        
        Args:
            order_id: ID заказа
            staff_id: ID сотрудника, который активирует заказ
            
        Returns:
            True если успешно, False если не удалось
        """
        async with maybe_managed_session(session) as s:
                # Загружаем заказ с блокировкой
                q = await s.execute(
                    select(m.orders)
                    .where(m.orders.id == order_id)
                    .with_for_update()
                )
                order = q.scalar_one_or_none()
                if not order:
                    return False
                
                # Проверяем доступ админа
                staff = await _load_staff_access(s, staff_id or None)
                if not _staff_can_access_city(staff, order.city_id):
                    return False
                
                # Проверяем, что заказ в статусе DEFERRED
                if order.status != m.OrderStatus.DEFERRED:
                    return False
                
                # Переводим в SEARCHING (или GUARANTEE для гарантийных)
                prev_status = order.status
                order_type = _raw_order_type(order)
                if order_type == m.OrderType.GUARANTEE:
                    new_status = m.OrderStatus.GUARANTEE
                else:
                    new_status = m.OrderStatus.SEARCHING
                
                order.status = new_status
                order.updated_at = datetime.now(UTC)
                order.version = (order.version or 0) + 1
                
                # Записываем в историю
                s.add(
                    m.order_status_history(
                        order_id=order.id,
                        from_status=prev_status,
                        to_status=new_status,
                        reason="activated_by_admin",
                        changed_by_staff_id=staff.id if staff else None,
                        actor_type=m.ActorType.ADMIN,
                    )
                )
                
                # Логируем активацию
                live_log.push(
                    "orders",
                    f"DEFERRED order #{order_id} activated → {new_status.value} by staff #{staff_id}",
                    level="INFO"
                )
        
        # Автораспределение будет запущено в следующем тике (каждые 30 секунд)
        # Заказ перешёл в статус SEARCHING/GUARANTEE и будет обработан автоматически
        return True


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

    async def manual_candidates(
        self,
        order_id: int,
        *,
        page: int,
        page_size: int,
        city_ids: Optional[Iterable[int]] = None,
    ) -> tuple[list, bool]:
        """Wrapper for masters_service.manual_candidates with city access check."""
        # Проверяем доступ к городу заказа
        if city_ids is not None:
            city_filter = list(city_ids)
            if city_filter:
                async with self._session_factory() as session:
                    row = await session.execute(
                        select(m.orders.city_id).where(m.orders.id == order_id)
                    )
                    order_city_id = row.scalar_one_or_none()
                    if order_city_id is None or order_city_id not in city_filter:
                        return [], False
        
        # Импортируем masters_service для вызова
        from .masters import DBMastersService
        masters_service = DBMastersService(self._session_factory)
        
        return await masters_service.manual_candidates(
            order_id,
            page=page,
            page_size=page_size,
        )






