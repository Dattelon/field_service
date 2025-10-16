from __future__ import annotations
import enum
from datetime import datetime, time
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
    text,  # SQL text() helper
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship, synonym

from .base import Base, metadata
from .pg_enums import OrderCategory

# ===== Enums =====


class ModerationStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class ShiftStatus(str, enum.Enum):
    SHIFT_OFF = "SHIFT_OFF"
    SHIFT_ON = "SHIFT_ON"
    BREAK = "BREAK"


class PayoutMethod(str, enum.Enum):
    CARD = "CARD"
    SBP = "SBP"
    YOOMONEY = "YOOMONEY"
    BANK_ACCOUNT = "BANK_ACCOUNT"


class OrderStatus(str, enum.Enum):
    """Canonical order statuses per TZ v1.2."""

    CREATED = "CREATED"
    # Backward-compatible alias used by some tests/fixtures
    NEW = CREATED
    SEARCHING = "SEARCHING"
    ASSIGNED = "ASSIGNED"
    EN_ROUTE = "EN_ROUTE"
    WORKING = "WORKING"
    PAYMENT = "PAYMENT"
    CLOSED = "CLOSED"
    DEFERRED = "DEFERRED"
    GUARANTEE = "GUARANTEE"
    CANCELED = "CANCELED"


class OrderType(str, enum.Enum):
    NORMAL = "NORMAL"
    GUARANTEE = "GUARANTEE"


class ActorType(str, enum.Enum):
    """Type of actor that changed order status."""
    SYSTEM = "SYSTEM"
    ADMIN = "ADMIN"
    MASTER = "MASTER"
    AUTO_DISTRIBUTION = "AUTO_DISTRIBUTION"


class OfferState(str, enum.Enum):
    SENT = "SENT"
    VIEWED = "VIEWED"
    ACCEPTED = "ACCEPTED"
    DECLINED = "DECLINED"
    EXPIRED = "EXPIRED"
    CANCELED = "CANCELED"


class AttachmentEntity(str, enum.Enum):
    ORDER = "ORDER"
    OFFER = "OFFER"
    COMMISSION = "COMMISSION"
    MASTER = "MASTER"  #    0002


class AttachmentFileType(str, enum.Enum):
    PHOTO = "PHOTO"
    DOCUMENT = "DOCUMENT"
    AUDIO = "AUDIO"
    VIDEO = "VIDEO"
    OTHER = "OTHER"


class CommissionStatus(str, enum.Enum):
    WAIT_PAY = "WAIT_PAY"
    REPORTED = "REPORTED"
    APPROVED = "APPROVED"
    OVERDUE = "OVERDUE"


class ReferralRewardStatus(str, enum.Enum):
    ACCRUED = "ACCRUED"
    PAID = "PAID"
    CANCELED = "CANCELED"


class StaffRole(str, enum.Enum):
    GLOBAL_ADMIN = "GLOBAL_ADMIN"
    CITY_ADMIN = "CITY_ADMIN"
    LOGIST = "LOGIST"
    # Backward-compat alias for legacy name
    ADMIN = GLOBAL_ADMIN
    SUPER_ADMIN = GLOBAL_ADMIN


# ===== Geo =====


class cities(Base):
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    centroid_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    centroid_lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    districts: Mapped[list["districts"]] = relationship(
        back_populates="city", cascade="all, delete-orphan"
    )


class districts(Base):
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    city_id: Mapped[int] = mapped_column(
        ForeignKey("cities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    centroid_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    centroid_lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    city: Mapped["cities"] = relationship(back_populates="districts")
    streets: Mapped[list["streets"]] = relationship(
        back_populates="district", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("city_id", "name", name="uq_districts__city_name"),
    )


class streets(Base):
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    city_id: Mapped[int] = mapped_column(
        ForeignKey("cities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    district_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("districts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    centroid_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    centroid_lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    city: Mapped["cities"] = relationship()
    district: Mapped[Optional["districts"]] = relationship()

    __table_args__ = (
        UniqueConstraint(
            "city_id", "district_id", "name", name="uq_streets__city_district_name"
        ),
    )



class geocache(Base):
    query: Mapped[str] = mapped_column(String(255), primary_key=True)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    confidence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# ===== Users (Masters & Staff) =====


class masters(Base):
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tg_user_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, unique=True, index=True
    )
    # Дополнительные поля совместимости для тестов истории/интерфейса
    telegram_username: Mapped[Optional[str]] = mapped_column(String(64))
    first_name: Mapped[Optional[str]] = mapped_column(String(80))
    last_name: Mapped[Optional[str]] = mapped_column(String(120))
    full_name: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    city_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("cities.id", ondelete="SET NULL"), nullable=True, index=True
    )
    rating: Mapped[float] = mapped_column(
        Float, nullable=False, default=5.0, server_default="5.0"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    is_blocked: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    is_deleted: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    is_on_shift: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    blocked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    blocked_reason: Mapped[Optional[str]] = mapped_column(Text)
    referral_code: Mapped[Optional[str]] = mapped_column(
        String(32), unique=True, index=True
    )
    referred_by_master_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("masters.id", ondelete="SET NULL"), nullable=True, index=True
    )
    last_heartbeat_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )

    # ----    0002 ----
    moderation_status: Mapped[ModerationStatus] = mapped_column(
        Enum(ModerationStatus, name="moderation_status"),
        nullable=False,
        default=ModerationStatus.PENDING,
        server_default="PENDING",
    )
    moderation_note: Mapped[Optional[str]] = mapped_column(Text)
    moderation_reason: Mapped[Optional[str]] = mapped_column(Text)
    shift_status: Mapped[ShiftStatus] = mapped_column(
        Enum(ShiftStatus, name="shift_status"),
        nullable=False,
        default=ShiftStatus.SHIFT_OFF,
        server_default="SHIFT_OFF",
    )
    break_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    max_active_orders_override: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    pdn_accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    payout_method: Mapped[Optional[PayoutMethod]] = mapped_column(
        Enum(PayoutMethod, name="payout_method")
    )
    payout_data: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB)
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    verified_by: Mapped[Optional[int]] = mapped_column(
        ForeignKey("staff_users.id", ondelete="SET NULL"), nullable=True
    )
    has_vehicle: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    vehicle_plate: Mapped[Optional[str]] = mapped_column(String(16))
    home_latitude: Mapped[Optional[float]] = mapped_column(Numeric(9, 6))
    home_longitude: Mapped[Optional[float]] = mapped_column(Numeric(9, 6))

    @property
    def telegram_id(self) -> Optional[int]:
        return self.tg_user_id

    @telegram_id.setter
    def telegram_id(self, value: Optional[int]) -> None:
        self.tg_user_id = value

    @property
    def phone_number(self) -> Optional[str]:
        return self.phone

    @phone_number.setter
    def phone_number(self, value: Optional[str]) -> None:
        self.phone = value

    # Compatibility aliases for legacy field names used in tests
    telegram_user_id = synonym("tg_user_id")
    tg_id = synonym("tg_user_id")  # Additional backward-compat alias

    # Patronymic property for backward compatibility (no DB column)
    @property
    def patronymic(self) -> Optional[str]:
        """Backward-compat property for tests using patronymic field."""
        return getattr(self, "_patronymic", None)

    @patronymic.setter
    def patronymic(self, value: Optional[str]) -> None:
        """Accept patronymic in constructor and auto-build full_name if needed."""
        # Store in memory (not persisted to DB)
        self._patronymic = value
        # If full_name not set yet, try to build it from name parts
        if not getattr(self, "full_name", None):
            parts = [
                getattr(self, "first_name", None),
                value,  # patronymic
                getattr(self, "last_name", None),
            ]
            parts = [p for p in parts if p]
            if parts:
                self.full_name = " ".join(parts)

    __table_args__ = (
        Index("ix_masters__mod_shift", "moderation_status", "shift_status"),
        Index("ix_masters__onshift_verified", "is_on_shift", "verified"),
        Index(
            "ix_masters__verified_active_deleted_city",
            "verified",
            "is_active",
            "is_deleted",
            "city_id",
        ),
    )


class staff_users(Base):
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tg_user_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, unique=True, index=True
    )
    telegram_id = synonym("tg_user_id")
    username: Mapped[Optional[str]] = mapped_column(String(64))
    full_name: Mapped[Optional[str]] = mapped_column(String(160))
    phone: Mapped[Optional[str]] = mapped_column(String(32))
    phone_number = synonym("phone")
    role: Mapped[StaffRole] = mapped_column(
        Enum(StaffRole, name="staff_role"), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    commission_requisites: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )


class staff_cities(Base):
    staff_user_id: Mapped[int] = mapped_column(
        ForeignKey("staff_users.id", ondelete="CASCADE"), primary_key=True
    )
    city_id: Mapped[int] = mapped_column(
        ForeignKey("cities.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class staff_access_codes(Base):
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(16), nullable=False, unique=True)
    role: Mapped[StaffRole] = mapped_column(
        Enum(StaffRole, name="staff_role"), nullable=False
    )
    city_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("cities.id", ondelete="SET NULL"), nullable=True
    )
    created_by_staff_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("staff_users.id", ondelete="SET NULL"), nullable=True
    )
    # Алиас для обратной совместимости
    issued_by_staff_id = synonym("created_by_staff_id")
    used_by_staff_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("staff_users.id", ondelete="SET NULL"), nullable=True
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    comment: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    city: Mapped[Optional["cities"]] = relationship()
    created_by_staff: Mapped[Optional["staff_users"]] = relationship(
        foreign_keys=[created_by_staff_id]
    )
    # Алиас для обратной совместимости
    issued_by_staff = synonym("created_by_staff")
    used_by_staff: Mapped[Optional["staff_users"]] = relationship(
        foreign_keys=[used_by_staff_id]
    )
    city_links: Mapped[list["staff_access_code_cities"]] = relationship(
        back_populates="access_code", cascade="all, delete-orphan"
    )


class staff_access_code_cities(Base):
    access_code_id: Mapped[int] = mapped_column(
        ForeignKey("staff_access_codes.id", ondelete="CASCADE"), primary_key=True
    )
    city_id: Mapped[int] = mapped_column(
        ForeignKey("cities.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    access_code: Mapped["staff_access_codes"] = relationship(
        back_populates="city_links"
    )
    city: Mapped["cities"] = relationship()


# ===== Orders & History =====


class orders(Base):
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    city_id: Mapped[int] = mapped_column(
        ForeignKey("cities.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    district_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("districts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    street_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("streets.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Convenient relationships for eager access in UI/tests
    city: Mapped[Optional["cities"]] = relationship(lazy="raise_on_sql")
    district: Mapped[Optional["districts"]] = relationship(lazy="raise_on_sql")

    lat: Mapped[Optional[float]] = mapped_column(Float(asdecimal=False))
    lon: Mapped[Optional[float]] = mapped_column(Float(asdecimal=False))
    geocode_provider: Mapped[Optional[str]] = mapped_column(String(32))
    geocode_confidence: Mapped[Optional[int]] = mapped_column(Integer)

    house: Mapped[Optional[str]] = mapped_column(String(32))
    apartment: Mapped[Optional[str]] = mapped_column(String(32))
    address_comment: Mapped[Optional[str]] = mapped_column(Text)

    client_name: Mapped[Optional[str]] = mapped_column(String(160))
    client_phone: Mapped[Optional[str]] = mapped_column(String(32), index=True)

    category: Mapped[OrderCategory] = mapped_column(
        Enum(OrderCategory, name="order_category"),
        nullable=False,
        server_default=OrderCategory.ELECTRICS.value,
    )
    description: Mapped[Optional[str]] = mapped_column(Text)

    status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus, name="order_status"),
        nullable=False,
        default=OrderStatus.CREATED,
        server_default="CREATED",
        index=True,
    )

    timeslot_start_utc: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    timeslot_end_utc: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    type: Mapped[OrderType] = mapped_column(
        Enum(OrderType, name="order_type"),
        nullable=False,
        default=OrderType.NORMAL,
        server_default="NORMAL",
    )

    preferred_master_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("masters.id", ondelete="SET NULL"), nullable=True, index=True
    )
    assigned_master_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("masters.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Совместимость со старыми тестами/фикстурами
    master_id = synonym("assigned_master_id")

    total_sum: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=Decimal("0"), server_default="0"
    )
    company_payment: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=0, server_default="0"
    )
    cancel_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    late_visit: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    no_district: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    dist_escalated_logist_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    dist_escalated_admin_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Step 1.4: Tracking escalation notifications to prevent duplicate sends
    escalation_logist_notified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    escalation_admin_notified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    guarantee_source_order_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("orders.id", ondelete="SET NULL"), nullable=True
    )

    created_by_staff_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("staff_users.id", ondelete="SET NULL"), index=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )  # optimistic lock

    # Optional: relationship to the source order for guarantee cases
    source_order: Mapped[Optional["orders"]] = relationship(remote_side="orders.id")

    # --- Compatibility aliases (legacy fields used by tests/old code) ---
    # Monetary amount alias
    final_amount = synonym("total_sum")
    # Timeslot convenience aliases
    timeslot_start = synonym("timeslot_start_utc")
    timeslot_end = synonym("timeslot_end_utc")
    # Address/geo aliases
    house_number = synonym("house")
    apartment_number = synonym("apartment")
    street_address = synonym("address_comment")
    # Generic address alias
    address = synonym("address_comment")
    # Additional legacy aliases used in tests
    address_street = synonym("address_comment")
    address_house = synonym("house")

    # Legacy input helpers: visit_date + slot_start/slot_end
    @property
    def visit_date(self):  # type: ignore[override]
        ts = getattr(self, "timeslot_start_utc", None)
        return ts.date() if ts is not None else None

    @visit_date.setter  # type: ignore[override]
    def visit_date(self, value):
        setattr(self, "_compat_visit_date", value)
        self._update_timeslot_from_compat()

    @property
    def slot_start(self):  # type: ignore[override]
        ts = getattr(self, "timeslot_start_utc", None)
        return ts.strftime("%H:%M") if ts is not None else None

    @slot_start.setter  # type: ignore[override]
    def slot_start(self, value: str):
        setattr(self, "_compat_slot_start", value)
        self._update_timeslot_from_compat()

    @property
    def slot_end(self):  # type: ignore[override]
        te = getattr(self, "timeslot_end_utc", None)
        return te.strftime("%H:%M") if te is not None else None

    @slot_end.setter  # type: ignore[override]
    def slot_end(self, value: str):
        setattr(self, "_compat_slot_end", value)
        self._update_timeslot_from_compat()

    def _update_timeslot_from_compat(self) -> None:
        try:
            vd = getattr(self, "_compat_visit_date", None)
            ss = getattr(self, "_compat_slot_start", None)
            se = getattr(self, "_compat_slot_end", None)
            if vd is None or ss is None or se is None:
                return
            from datetime import datetime as _dt, time as _time, timezone as _tz

            st = _time.fromisoformat(ss)
            et = _time.fromisoformat(se)
            self.timeslot_start_utc = _dt.combine(vd, st).replace(tzinfo=_tz.utc)
            self.timeslot_end_utc = _dt.combine(vd, et).replace(tzinfo=_tz.utc)
        except Exception:
            # best-effort: ignore parse/assignment issues
            pass

    __table_args__ = (
        CheckConstraint(
            "(timeslot_start_utc IS NULL AND timeslot_end_utc IS NULL) OR (timeslot_start_utc < timeslot_end_utc)",
            name="ck_orders__timeslot_range",
        ),
        Index("ix_orders__status_city", "status", "city_id"),
        Index("ix_orders__city_status", "city_id", "status"),
        Index("ix_orders__category", "category"),
        Index("ix_orders__assigned_master", "assigned_master_id"),
        Index("ix_orders__preferred_master", "preferred_master_id"),
        Index(
            "ix_orders__status_city_timeslot_start",
            "status",
            "city_id",
            "timeslot_start_utc",
        ),
    )
class order_status_history(Base):
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    from_status: Mapped[Optional[OrderStatus]] = mapped_column(
        Enum(OrderStatus, name="order_status"), nullable=True
    )
    to_status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus, name="order_status"), nullable=False
    )
    reason: Mapped[Optional[str]] = mapped_column(Text)
    changed_by_staff_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("staff_users.id", ondelete="SET NULL")
    )
    changed_by_master_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("masters.id", ondelete="SET NULL")
    )
    actor_type: Mapped[ActorType] = mapped_column(
        Enum(ActorType, name="actor_type"),
        nullable=False,
        default=ActorType.SYSTEM,
        index=True
    )
    context: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    __table_args__ = (
        Index("ix_order_status_history__order_created_at", "order_id", "created_at"),
    )


# ===== Offers =====


class offers(Base):
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # FK на masters.id восстановлен для целостности данных
    master_id: Mapped[int] = mapped_column(
        ForeignKey("masters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    round_number: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=1, server_default="1"
    )
    state: Mapped[OfferState] = mapped_column(
        Enum(OfferState, name="offer_state"), nullable=False, index=True
    )
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    responded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    order: Mapped["orders"] = relationship(lazy="raise_on_sql")
    master: Mapped["masters"] = relationship(lazy="raise_on_sql")

    __table_args__ = (
        # Partial unique index: активные офферы уникальны по (order_id, master_id)
        # для state IN ('SENT', 'VIEWED', 'ACCEPTED')
        Index(
            "uq_offers__order_master_active",
            "order_id",
            "master_id",
            unique=True,
            postgresql_where=text("state IN ('SENT', 'VIEWED', 'ACCEPTED')"),
        ),
        Index("ix_offers__order_state", "order_id", "state"),
        Index("ix_offers__master_state", "master_id", "state"),
        # Уникальность ACCEPTED оффера: только один принятый оффер на заказ
        Index(
            "uix_offers__order_accepted_once",
            "order_id",
            unique=True,
            postgresql_where=text("state = 'ACCEPTED'"),
        ),
    )


# ===== Attachments =====


class attachments(Base):
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_type: Mapped[AttachmentEntity] = mapped_column(
        Enum(AttachmentEntity, name="attachment_entity"), nullable=False, index=True
    )
    entity_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    file_type: Mapped[AttachmentFileType] = mapped_column(
        Enum(AttachmentFileType, name="attachment_file_type"), nullable=False
    )
    file_id: Mapped[str] = mapped_column(
        String(256), nullable=False
    )  # Telegram file_id
    file_unique_id: Mapped[Optional[str]] = mapped_column(String(256))
    file_name: Mapped[Optional[str]] = mapped_column(String(256))
    mime_type: Mapped[Optional[str]] = mapped_column(String(128))
    size: Mapped[Optional[int]] = mapped_column(Integer)
    caption: Mapped[Optional[str]] = mapped_column(Text)
    document_type: Mapped[Optional[str]] = mapped_column(String(32))
    uploaded_by_master_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("masters.id", ondelete="SET NULL")
    )
    uploaded_by_staff_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("staff_users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (Index("ix_attachments__etype_eid", "entity_type", "entity_id"),)


# ===== Commissions =====


class commissions(Base):
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # FK на orders с UNIQUE constraint - каждый заказ имеет только одну комиссию
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    # Алиас для обратной совместимости с тестами
    order_id_raw = synonym("order_id")
    master_id: Mapped[int] = mapped_column(
        ForeignKey("masters.id", ondelete="CASCADE"), nullable=False, index=True
    )
    amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    percent: Mapped[Optional[float]] = mapped_column(Numeric(5, 2))
    rate: Mapped[Optional[float]] = mapped_column(Numeric(5, 2))
    status: Mapped[CommissionStatus] = mapped_column(
        Enum(CommissionStatus, name="commission_status"), nullable=False, index=True
    )
    deadline_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    paid_reported_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    paid_approved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    paid_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    paid_amount: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    is_paid: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    has_checks: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    pay_to_snapshot: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB)
    blocked_applied: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    blocked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    payment_reference: Mapped[Optional[str]] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_commissions__status_deadline", "status", "deadline_at"),
        Index("ix_commissions__master_status", "master_id", "status"),
        Index("ix_commissions__ispaid_deadline", "is_paid", "deadline_at"),
    )


# ===== Referrals =====


class referrals(Base):
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    master_id: Mapped[int] = mapped_column(
        ForeignKey("masters.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )  # 
    referrer_id: Mapped[int] = mapped_column(
        ForeignKey("masters.id", ondelete="CASCADE"), nullable=False, index=True
    )  #  (L1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class referral_rewards(Base):
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    referrer_id: Mapped[int] = mapped_column(
        ForeignKey("masters.id", ondelete="CASCADE"), nullable=False, index=True
    )
    referred_master_id: Mapped[int] = mapped_column(
        ForeignKey("masters.id", ondelete="CASCADE"), nullable=False, index=True
    )
    commission_id: Mapped[int] = mapped_column(
        ForeignKey("commissions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    level: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    percent: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    status: Mapped[ReferralRewardStatus] = mapped_column(
        Enum(ReferralRewardStatus, name="referral_reward_status"),
        nullable=False,
        index=True,
    )
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "commission_id",
            "level",
            name="uq_referral_rewards__commission_level",
        ),
        Index("ix_ref_rewards__referrer_status", "referrer_id", "status"),
        Index("ix_ref_rewards__referrer_created", "referrer_id", "created_at"),
    )


# ===== Settings (K/V) =====# ===== Settings (K/V) =====


class settings(Base):
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    value_type: Mapped[str] = mapped_column(
        String(16), nullable=False, default="STR", server_default="STR"
    )  # INT/FLOAT/BOOL/STR/JSON/TIME
    description: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


# ===== Skills & Master mappings (  0002) =====
class skills(Base):
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class master_skills(Base):
    master_id: Mapped[int] = mapped_column(
        ForeignKey("masters.id", ondelete="CASCADE"), primary_key=True
    )
    skill_id: Mapped[int] = mapped_column(
        ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class master_districts(Base):
    master_id: Mapped[int] = mapped_column(
        ForeignKey("masters.id", ondelete="CASCADE"), primary_key=True
    )
    district_id: Mapped[int] = mapped_column(
        ForeignKey("districts.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class master_invite_codes(Base):
    """Invite codes for master onboarding (issued by staff)."""

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(
        String(32), nullable=False, unique=True, index=True
    )
    issued_by_staff_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("staff_users.id", ondelete="SET NULL"), nullable=True
    )
    city_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("cities.id", ondelete="SET NULL"), nullable=True, index=True
    )
    is_revoked: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    used_by_master_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("masters.id", ondelete="SET NULL"), nullable=True, index=True
    )
    comment: Mapped[Optional[str]] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class admin_audit_log(Base):
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    admin_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("staff_users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    master_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("masters.id", ondelete="SET NULL"), nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class notifications_outbox(Base):
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    master_id: Mapped[int] = mapped_column(
        ForeignKey("masters.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    attempt_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    last_error: Mapped[Optional[str]] = mapped_column(Text)


# P1-01: Autoclose queue
class order_autoclose_queue(Base):
    """Очередь для автозакрытия заказов через 24ч после CLOSED."""
    __tablename__ = 'order_autoclose_queue'
    
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"),
        primary_key=True
    )
    closed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False
    )
    autoclose_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False
    )
    processed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )
    
    __table_args__ = (
        Index(
            "ix_order_autoclose_queue__pending",
            "autoclose_at",
            postgresql_where=text("processed_at IS NULL")
        ),
    )


class distribution_metrics(Base):
    """Метрики процесса распределения заказов для аналитики и оптимизации."""
    __tablename__ = 'distribution_metrics'
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    master_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    
    # Метрики назначения
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True
    )
    round_number: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    candidates_count: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    time_to_assign_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Флаги процесса
    preferred_master_used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    was_escalated_to_logist: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    was_escalated_to_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    
    # География и категория
    city_id: Mapped[int] = mapped_column(
        ForeignKey("cities.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    district_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("districts.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    # В БД хранятся как VARCHAR, поэтому используем String
    category: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    order_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    
    # Дополнительные данные
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb")
    )
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )
    
    def __init__(self, **kwargs):
        """Конвертируем Enum в строки для category и order_type."""
        # Конвертация category
        if 'category' in kwargs and hasattr(kwargs['category'], 'value'):
            kwargs['category'] = kwargs['category'].value
        # Конвертация order_type  
        if 'order_type' in kwargs and hasattr(kwargs['order_type'], 'value'):
            kwargs['order_type'] = kwargs['order_type'].value
        super().__init__(**kwargs)
    
    __table_args__ = (
        Index("ix_distribution_metrics__assigned_at_desc", "assigned_at", postgresql_using="btree"),
        Index("ix_distribution_metrics__city_assigned", "city_id", "assigned_at"),
        Index("ix_distribution_metrics__performance", "round_number", "time_to_assign_seconds"),
    )





# ===== Commission Deadline Notifications (P1-21) =====


class commission_deadline_notifications(Base):
    """Tracks sent deadline reminders to avoid duplicates."""
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    commission_id: Mapped[int] = mapped_column(
        ForeignKey("commissions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    hours_before: Mapped[int] = mapped_column(
        SmallInteger, 
        nullable=False,
        comment="Hours before deadline (24, 6, or 1)"
    )
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    
    __table_args__ = (
        UniqueConstraint(
            "commission_id", 
            "hours_before", 
            name="uq_commission_deadline_notifications__commission_hours"
        ),
        Index("ix_commission_deadline_notifications__commission", "commission_id"),
    )
