"""Common imports and utility functions for admin services."""
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

from ..core.dto import (
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
from ..utils.normalizers import normalize_category, normalize_status

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

STREET_DUPLICATE_THRESHOLD = 93
STREET_MIN_SCORE = 60

WORKDAY_START_DEFAULT = time_service.parse_time_string(settings.workday_start, default=time(10, 0))
WORKDAY_END_DEFAULT = time_service.parse_time_string(settings.workday_end, default=time(20, 0))
LATE_ASAP_THRESHOLD = time_service.parse_time_string(settings.asap_late_threshold, default=time(19, 30))

QUEUE_STATUSES = {
    m.OrderStatus.SEARCHING,
    m.OrderStatus.ASSIGNED,
    m.OrderStatus.EN_ROUTE,
    m.OrderStatus.WORKING,
    m.OrderStatus.PAYMENT,
    m.OrderStatus.GUARANTEE,
    m.OrderStatus.DEFERRED,
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


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

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
    m.OrderStatus.DEFERRED,
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





async def _ensure_centroid_flag(session: AsyncSession, scope: str) -> bool:
    """Check if centroid columns exist for given scope (street/district/city)."""
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
