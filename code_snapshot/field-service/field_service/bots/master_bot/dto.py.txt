from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional, Sequence

from field_service.db import models as m


@dataclass(slots=True)
class MasterProfile:
    id: int
    tg_user_id: int
    full_name: str
    phone: Optional[str]
    verified: bool
    is_active: bool
    shift_status: m.ShiftStatus
    break_until: Optional[datetime]
    has_vehicle: bool
    city_id: Optional[int]


@dataclass(slots=True)
class OfferPreview:
    order_id: int
    city: str
    district: Optional[str]
    category: m.OrderCategory
    description: str
    sent_at: datetime
    timeslot_start_utc: Optional[datetime]
    timeslot_end_utc: Optional[datetime]
    timeslot_display: Optional[str]


@dataclass(slots=True)
class CommissionListItem:
    id: int
    order_id: int
    amount: Decimal
    rate: Decimal
    status: m.CommissionStatus
    deadline_at: datetime
    created_at: datetime
    has_checks: bool


@dataclass(slots=True)
class CommissionDetails(CommissionListItem):
    paid_reported_at: Optional[datetime]
    paid_approved_at: Optional[datetime]
    paid_amount: Optional[Decimal]
    pay_to_snapshot: Optional[dict]


@dataclass(slots=True)
class ReferralStats:
    code: Optional[str]
    level_one_total: Decimal
    level_two_total: Decimal
    recent_rewards: Sequence[m.referral_rewards]
