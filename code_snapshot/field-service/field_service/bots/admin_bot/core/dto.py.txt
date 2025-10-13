from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any, FrozenSet, Mapping, Optional, Sequence, Tuple

from field_service.db import OrderCategory
from field_service.db.models import OrderStatus, OrderType, StaffRole


@dataclass(frozen=True)
class StaffUser:
    """Minimal staff context injected into handlers."""

    id: int
    tg_id: int
    role: StaffRole
    is_active: bool
    city_ids: FrozenSet[int]
    full_name: str = ""
    phone: str = ""


@dataclass(frozen=True)
class StaffMember:
    """Detailed staff row for listing/edit screens."""

    id: int
    tg_id: Optional[int]
    username: Optional[str]
    full_name: str
    phone: Optional[str]
    role: StaffRole
    is_active: bool
    city_ids: Tuple[int, ...]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class StaffAccessCode:
    id: int
    code: str
    role: StaffRole
    city_ids: Tuple[int, ...]
    issued_by_staff_id: Optional[int]
    used_by_staff_id: Optional[int]
    expires_at: Optional[datetime]
    used_at: Optional[datetime]
    revoked_at: Optional[datetime]
    is_revoked: bool
    comment: Optional[str]
    created_at: datetime



@dataclass(frozen=True)
class WaitPayRecipient:
    master_id: int
    tg_user_id: Optional[int]
    full_name: str


@dataclass(frozen=True)
class CityRef:
    id: int
    name: str


@dataclass(frozen=True)
class DistrictRef:
    id: int
    city_id: int
    name: str


@dataclass(frozen=True)
class StreetRef:
    id: int
    city_id: int
    district_id: Optional[int]
    name: str
    score: Optional[float] = None


@dataclass(frozen=True)
class TimeslotOption:
    key: str
    label: str
    start_utc: Optional[datetime]
    end_utc: Optional[datetime]
    is_asap: bool = False


@dataclass(frozen=True)
class OrderAttachment:
    id: int
    file_type: str
    file_id: str
    file_name: Optional[str]
    caption: Optional[str]


@dataclass(frozen=True)
class OrderListItem:
    id: int
    city_id: int
    city_name: str
    district_id: Optional[int]
    district_name: Optional[str]
    street_name: Optional[str]
    house: Optional[str]
    status: str
    order_type: OrderType
    category: OrderCategory
    created_at_local: str
    timeslot_local: Optional[str]
    master_id: Optional[int]
    master_name: Optional[str]
    master_phone: Optional[str]
    has_attachments: bool

    @property
    def type(self) -> str:
        return self.order_type.value


@dataclass(frozen=True)
class OrderDetail(OrderListItem):
    client_name: Optional[str]
    client_phone: Optional[str]
    apartment: Optional[str]
    address_comment: Optional[str]
    description: Optional[str]
    lat: Optional[float]
    lon: Optional[float]
    company_payment: Optional[Decimal]
    total_sum: Decimal
    attachments: Tuple[OrderAttachment, ...]


@dataclass(frozen=True)
class OrderStatusHistoryItem:
    id: int
    from_status: Optional[str]
    to_status: str
    reason: Optional[str]
    changed_by_staff_id: Optional[int]
    changed_by_master_id: Optional[int]
    changed_at_local: str
    actor_type: str = "SYSTEM"
    actor_name: Optional[str] = None  # Имя админа/мастера для отображения
    context: Mapping[str, Any] = field(default_factory=dict)  # Дополнительные детали


@dataclass(frozen=True)
class DeclinedMasterInfo:
    """Information about master who declined an order."""
    master_id: int
    master_name: str
    round_number: int
    declined_at_local: str


@dataclass(frozen=True)
class OrderCard(OrderDetail):
    """Extended order detail with history and timing info."""
    status_history: Tuple[OrderStatusHistoryItem, ...] = ()
    declined_masters: Tuple[DeclinedMasterInfo, ...] = ()
    en_route_at_local: Optional[str] = None
    working_at_local: Optional[str] = None
    payment_at_local: Optional[str] = None


@dataclass(frozen=True)
class MasterBrief:
    id: int
    full_name: str
    city_id: int
    has_car: bool
    avg_week_check: float
    rating_avg: float
    is_on_shift: bool
    is_active: bool
    verified: bool
    in_district: bool
    active_orders: int
    max_active_orders: int
    on_break: bool


@dataclass(frozen=True)
class MasterListItem:
    id: int
    full_name: str
    city_name: Optional[str]
    skills: Tuple[str, ...]
    rating: float
    has_vehicle: bool
    is_on_shift: bool
    shift_status: str
    on_break: bool
    verified: bool
    is_active: bool
    is_deleted: bool
    active_orders: int
    max_active_orders: Optional[int]
    avg_check: Optional[Decimal]


@dataclass(frozen=True)
class MasterDocument:
    id: int
    file_type: str
    file_id: str
    file_name: Optional[str]
    caption: Optional[str]
    document_type: Optional[str]


@dataclass(frozen=True)
class MasterDetail:
    id: int
    full_name: str
    phone: Optional[str]
    city_id: Optional[int]
    city_name: Optional[str]
    rating: float
    has_vehicle: bool
    is_active: bool
    is_blocked: bool
    is_deleted: bool
    blocked_reason: Optional[str]
    blocked_at_local: Optional[str]
    moderation_status: str
    moderation_reason: Optional[str]
    verified: bool
    verified_at_local: Optional[str]
    verified_by: Optional[int]
    is_on_shift: bool
    shift_status: str
    payout_method: Optional[str]
    payout_data: Mapping[str, Optional[str]]
    referral_code: Optional[str]
    referred_by_master_id: Optional[int]
    current_limit: Optional[int]
    active_orders: int
    avg_check: Optional[Decimal]
    moderation_history: Optional[str]
    has_orders: bool
    has_commissions: bool
    created_at_local: str
    updated_at_local: str
    district_names: Tuple[str, ...]
    skill_names: Tuple[str, ...]
    documents: Tuple[MasterDocument, ...]


@dataclass(frozen=True)
class CommissionListItem:
    id: int
    order_id: int
    master_id: Optional[int]
    master_name: Optional[str]
    status: str
    amount: Decimal
    deadline_at_local: Optional[str]


@dataclass(frozen=True)
class CommissionAttachment:
    id: int
    file_type: str
    file_id: str
    file_name: Optional[str]
    caption: Optional[str]


@dataclass(frozen=True)
class CommissionDetail:
    id: int
    order_id: int
    master_id: Optional[int]
    master_name: Optional[str]
    master_phone: Optional[str]
    status: str
    amount: Decimal
    rate: Decimal
    deadline_at_local: Optional[str]
    created_at_local: str
    paid_reported_at_local: Optional[str]
    paid_approved_at_local: Optional[str]
    paid_amount: Optional[Decimal]
    has_checks: bool
    snapshot_methods: Tuple[str, ...]
    snapshot_data: Mapping[str, Optional[str]]
    attachments: Tuple[CommissionAttachment, ...]


@dataclass(frozen=True)
class NewOrderAttachment:
    file_id: str
    file_unique_id: Optional[str]
    file_type: str
    file_name: Optional[str]
    mime_type: Optional[str]
    caption: Optional[str]


@dataclass(frozen=True)
class NewOrderData:
    city_id: int
    district_id: Optional[int]
    street_id: Optional[int]
    house: Optional[str]
    apartment: Optional[str]
    address_comment: Optional[str]
    client_name: str
    client_phone: str
    category: OrderCategory
    description: str
    order_type: OrderType
    timeslot_start_utc: Optional[datetime]
    timeslot_end_utc: Optional[datetime]
    timeslot_display: Optional[str]
    lat: Optional[float]
    lon: Optional[float]
    no_district: bool
    company_payment: Optional[Decimal]
    total_sum: Decimal
    created_by_staff_id: Optional[int]
    preferred_master_id: Optional[int] = None
    guarantee_source_order_id: Optional[int] = None
    initial_status: Optional[OrderStatus] = None
    attachments: Sequence[NewOrderAttachment] = ()


__all__ = [
    'CityRef',
    'CommissionAttachment',
    'CommissionDetail',
    'CommissionListItem',
    'DeclinedMasterInfo',
    'DistrictRef',
    'MasterBrief',
    'MasterListItem',
    'MasterDocument',
    'MasterDetail',
    'NewOrderAttachment',
    'NewOrderData',
    'OrderAttachment',
    'OrderDetail',
    'OrderCard',
    'OrderListItem',
    'OrderStatusHistoryItem',
    'OrderCategory',
    'OrderType',
    'OrderStatus',
    'StaffAccessCode',
    'StaffMember',
    'StaffRole',
    'StaffUser',
    'StreetRef',
    'TimeslotOption',
    'WaitPayRecipient',
]
