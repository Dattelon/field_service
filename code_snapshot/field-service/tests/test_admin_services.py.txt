from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import insert, select

from field_service.bots.admin_bot.services_db import (
    DBDistributionService,
    DBFinanceService,
    DBOrdersService,
    DBSettingsService,
    PAYMENT_METHOD_LABELS,
)
from field_service.bots.admin_bot.dto import NewOrderData, OrderCategory, OrderType, OrderStatus
from field_service.db import models as m
from field_service.services import distribution_worker as dw, live_log
from field_service.services.guarantee_service import GuaranteeError
from field_service.data import cities as city_catalog
from field_service.services.referral_service import apply_rewards_for_commission

UTC = timezone.utc


def _tables(*items):
    return list(items)


async def _ensure_tables(session, tables):
    def _create(sync_session):
        for table in tables:
            table.create(sync_session.bind, checkfirst=True)

    await session.run_sync(_create)


@asynccontextmanager
async def existing_session(session):
    yield session


@pytest.mark.asyncio
async def test_list_cities_and_districts(async_session) -> None:
    await _ensure_tables(async_session, _tables(m.districts.__table__))
    primary_name = city_catalog.ALLOWED_CITIES[0]
    secondary_name = city_catalog.ALLOWED_CITIES[1]
    city = m.cities(name=primary_name)
    other_city = m.cities(name=secondary_name)
    async_session.add_all([city, other_city])
    await async_session.flush()

    district = m.districts(city_id=city.id, name="Central")
    async_session.add(district)
    await async_session.flush()

    orders_service = DBOrdersService(session_factory=lambda: existing_session(async_session))
    cities = await orders_service.list_cities(limit=5)
    assert [c.name for c in cities] == [primary_name, secondary_name]

    alias_result = await orders_service.list_cities(query="Питер")
    assert [c.name for c in alias_result] == [secondary_name]

    districts, has_next = await orders_service.list_districts(city.id, page=1, page_size=5)
    assert has_next is False
    assert any(d.name == "Central" for d in districts)


@pytest.mark.asyncio
async def test_search_streets(async_session) -> None:
    await _ensure_tables(async_session, _tables(m.districts.__table__, m.streets.__table__))
    city = m.cities(name="Street City")
    async_session.add(city)
    await async_session.flush()

    district = m.districts(city_id=city.id, name="District")
    async_session.add(district)
    await async_session.flush()

    street = m.streets(city_id=city.id, district_id=district.id, name="Baker Street")
    async_session.add(street)
    await async_session.flush()

    orders_service = DBOrdersService(session_factory=lambda: existing_session(async_session))
    results = await orders_service.search_streets(city.id, "Baker")
    assert any(r.name == "Baker Street" for r in results)




@pytest.mark.asyncio
async def test_create_guarantee_order(async_session) -> None:
    await _ensure_tables(async_session, _tables(m.cities.__table__, m.masters.__table__, m.orders.__table__))
    city = m.cities(name="Guarantee City")
    async_session.add(city)
    await async_session.flush()

    master = m.masters(
        tg_user_id=777,
        full_name="Guarantee Master",
        phone="+79990000077",
        city_id=city.id,
        is_active=True,
        is_on_shift=True,
        verified=True,
        shift_status=m.ShiftStatus.SHIFT_ON,
        moderation_status=m.ModerationStatus.APPROVED,
    )
    async_session.add(master)
    await async_session.flush()

    order = m.orders(
        city_id=city.id,
        status=m.OrderStatus.CLOSED,
        type=m.OrderType.NORMAL,
        assigned_master_id=master.id,
        client_name="",
        client_phone="+79990000078",
        category="ELECTRICS",
        description=" ",
        total_sum=Decimal("1500"),
    )
    async_session.add(order)
    await async_session.flush()

    service = DBOrdersService(session_factory=lambda: existing_session(async_session))
    new_id = await service.create_guarantee_order(order.id, by_staff_id=0)

    guarantee = await async_session.get(m.orders, new_id)
    assert guarantee is not None
    assert guarantee.type == m.OrderType.GUARANTEE
    assert guarantee.status == m.OrderStatus.GUARANTEE
    assert guarantee.preferred_master_id == master.id
    assert guarantee.guarantee_source_order_id == order.id
    assert Decimal(guarantee.company_payment) == Decimal("2500")
    assert Decimal(guarantee.total_sum) == Decimal("0")
    assert "" in guarantee.description.upper()

    assert await service.has_active_guarantee(order.id) is True
@pytest.mark.asyncio
async def test_commission_detail(async_session) -> None:
    await _ensure_tables(async_session, _tables(m.attachments.__table__))
    city = m.cities(name="Finance City")
    async_session.add(city)
    await async_session.flush()

    master = m.masters(
        tg_user_id=555,
        full_name="Finance Master",
        phone="+79990000001",
        city_id=city.id,
        is_active=True,
        is_on_shift=True,
        verified=True,
        shift_status=m.ShiftStatus.SHIFT_ON,
        moderation_status=m.ModerationStatus.APPROVED,
    )
    async_session.add(master)
    await async_session.flush()

    order = m.orders(
        city_id=city.id,
        district_id=None,
        status=m.OrderStatus.PAYMENT,
        total_sum=Decimal("2000"),
        assigned_master_id=master.id,
        client_name="Client",
        client_phone="+79990000002",
    )
    async_session.add(order)
    await async_session.flush()

    commission = m.commissions(
        order_id=order.id,
        master_id=master.id,
        amount=Decimal("1000"),
        rate=Decimal("0.5"),
        status=m.CommissionStatus.WAIT_PAY,
        deadline_at=datetime.now(UTC) + timedelta(hours=1),
        has_checks=True,
        pay_to_snapshot={"methods": ["card"], "card_number_last4": "1234", "card_holder": "Owner", "card_bank": "TestBank", "sbp_phone_masked": "+7*** *** ** 01"},
    )
    async_session.add(commission)
    await async_session.flush()

    attachment = m.attachments(
        entity_type=m.AttachmentEntity.COMMISSION,
        entity_id=commission.id,
        file_type=m.AttachmentFileType.DOCUMENT,
        file_id="file-id",
        file_name="check.pdf",
    )
    async_session.add(attachment)
    await async_session.flush()

    finance_service = DBFinanceService(session_factory=lambda: existing_session(async_session))
    detail = await finance_service.get_commission_detail(commission.id)
    assert detail is not None
    assert detail.amount == Decimal("1000")
    assert detail.attachments and detail.attachments[0].file_name == "check.pdf"
    assert detail.snapshot_methods == (PAYMENT_METHOD_LABELS["card"],)




@pytest.mark.asyncio
async def test_finance_approve_updates_order(async_session) -> None:
    await _ensure_tables(async_session, _tables(m.order_status_history.__table__))

    city = m.cities(name="Approve City")
    async_session.add(city)
    await async_session.flush()

    master = m.masters(
        tg_user_id=600,
        full_name="Approve Master",
        phone="+79990000010",
        city_id=city.id,
        is_active=True,
        is_on_shift=True,
        verified=True,
        shift_status=m.ShiftStatus.SHIFT_ON,
        moderation_status=m.ModerationStatus.APPROVED,
    )
    async_session.add(master)
    await async_session.flush()

    order = m.orders(
        city_id=city.id,
        district_id=None,
        status=m.OrderStatus.PAYMENT,
        total_sum=Decimal("3000"),
        assigned_master_id=master.id,
    )
    async_session.add(order)
    await async_session.flush()

    commission = m.commissions(
        order_id=order.id,
        master_id=master.id,
        amount=Decimal("1500"),
        rate=Decimal("0.5"),
        status=m.CommissionStatus.WAIT_PAY,
        deadline_at=datetime.now(UTC) + timedelta(hours=2),
    )
    async_session.add(commission)

    staff_row = m.staff_users(id=1, role=m.StaffRole.GLOBAL_ADMIN, is_active=True)
    async_session.add(staff_row)
    await async_session.flush()

    finance_service = DBFinanceService(session_factory=lambda: existing_session(async_session))
    ok = await finance_service.approve(commission.id, paid_amount=Decimal("1500"), by_staff_id=1)
    assert ok

    await async_session.refresh(commission)
    await async_session.refresh(order)

    assert commission.status == m.CommissionStatus.APPROVED
    assert commission.is_paid is True
    assert commission.paid_amount == Decimal("1500.00")
    assert order.status == m.OrderStatus.CLOSED

    history_rows = await async_session.execute(
        select(m.order_status_history.to_status).where(m.order_status_history.order_id == order.id)
    )
    history = history_rows.scalar_one()
    assert history == m.OrderStatus.CLOSED


@pytest.mark.asyncio
async def test_finance_reject_resets_state(async_session) -> None:
    city = m.cities(name="Reject City")
    async_session.add(city)
    await async_session.flush()

    master = m.masters(
        tg_user_id=601,
        full_name="Reject Master",
        phone="+79990000011",
        city_id=city.id,
        is_active=True,
        is_on_shift=True,
        verified=True,
        shift_status=m.ShiftStatus.SHIFT_ON,
        moderation_status=m.ModerationStatus.APPROVED,
    )
    async_session.add(master)
    await async_session.flush()

    order = m.orders(
        city_id=city.id,
        status=m.OrderStatus.PAYMENT,
        assigned_master_id=master.id,
    )
    async_session.add(order)
    await async_session.flush()

    commission = m.commissions(
        order_id=order.id,
        master_id=master.id,
        amount=Decimal("1200"),
        rate=Decimal("0.5"),
        status=m.CommissionStatus.REPORTED,
        deadline_at=datetime.now(UTC) + timedelta(hours=1),
        paid_reported_at=datetime.now(UTC),
        paid_amount=Decimal("1200"),
    )
    async_session.add(commission)
    await async_session.flush()

    finance_service = DBFinanceService(session_factory=lambda: existing_session(async_session))
    ok = await finance_service.reject(commission.id, reason="invalid receipt", by_staff_id=0)
    assert ok

    await async_session.refresh(commission)
    assert commission.status == m.CommissionStatus.WAIT_PAY
    assert commission.paid_reported_at is None
    assert commission.paid_amount is None
    assert commission.is_paid is False


@pytest.mark.asyncio
async def test_finance_block_master(async_session) -> None:
    city = m.cities(name="Block City")
    async_session.add(city)
    await async_session.flush()

    master = m.masters(
        tg_user_id=602,
        full_name="Block Master",
        phone="+79990000012",
        city_id=city.id,
        is_active=True,
        is_on_shift=True,
        verified=True,
        shift_status=m.ShiftStatus.SHIFT_ON,
        moderation_status=m.ModerationStatus.APPROVED,
    )
    async_session.add(master)
    await async_session.flush()

    finance_service = DBFinanceService(session_factory=lambda: existing_session(async_session))
    ok = await finance_service.block_master_for_overdue(master.id, by_staff_id=0)
    assert ok

    await async_session.refresh(master)
    assert master.is_blocked is True
    assert master.is_active is False
    assert master.blocked_reason == "manual_block_from_finance"
@pytest.mark.asyncio
async def test_db_settings_set_and_channels(async_session) -> None:
    service = DBSettingsService(session_factory=lambda: existing_session(async_session))
    await service.set_value("alerts_channel_id", "321", value_type="STR")
    await service.set_value("logs_channel_id", "", value_type="STR")

    values = await service.get_values(["alerts_channel_id", "logs_channel_id"])
    assert values["alerts_channel_id"][0] == "321"
    assert values["logs_channel_id"][0] == ""

    channels = await service.get_channel_settings()
    assert channels["alerts_channel_id"] == 321
    assert channels["logs_channel_id"] is None


def test_live_log_buffer() -> None:
    from field_service.services import live_log

    live_log.clear()
    live_log.push("dist", "message", level="INFO")
    entries = live_log.snapshot(10)
    assert entries
    assert entries[-1].message == "message"
    assert live_log.size() == 1
    live_log.clear()
    assert live_log.size() == 0



@pytest.mark.asyncio
async def test_distribution_assign_auto_no_district(async_session) -> None:
    live_log.clear()
    await _ensure_tables(async_session, _tables(m.order_status_history.__table__))

    city = m.cities(name="AutoCity")
    async_session.add(city)
    await async_session.flush()

    order = m.orders(
        city_id=city.id,
        district_id=None,
        status=m.OrderStatus.SEARCHING,
        category="ELECTRICS",
    )
    async_session.add(order)
    await async_session.commit()

    service = DBDistributionService(session_factory=lambda: existing_session(async_session))

    ok, result = await service.assign_auto(order.id, by_staff_id=0)
    await async_session.refresh(order)

    assert not ok
    assert result.code == "no_district"
    assert order.dist_escalated_logist_at is not None

    history_rows = await async_session.execute(
        select(m.order_status_history.reason).where(m.order_status_history.order_id == order.id)
    )
    reasons = [row[0] for row in history_rows]
    assert any(reason and "no_district" in reason for reason in reasons)

    entries = live_log.snapshot(5)
    assert any("skip_auto: no_district" in entry.message for entry in entries)


@pytest.mark.asyncio
async def test_distribution_assign_auto_success(async_session, monkeypatch) -> None:
    live_log.clear()
    await _ensure_tables(
        async_session,
        _tables(
            m.districts.__table__,
            m.skills.__table__,
            m.master_districts.__table__,
            m.master_skills.__table__,
            m.offers.__table__,
            m.order_status_history.__table__,
            m.settings.__table__,
        ),
    )

    city = m.cities(name="Metro City")
    async_session.add(city)
    await async_session.flush()

    district = m.districts(city_id=city.id, name="Center")
    async_session.add(district)

    skill = m.skills(code="ELEC", name="Electrics", is_active=True)
    async_session.add(skill)
    await async_session.flush()

    master = m.masters(
        tg_user_id=999,
        full_name=" ",
        phone="+79990000001",
        city_id=city.id,
        is_active=True,
        is_on_shift=True,
        verified=True,
        shift_status=m.ShiftStatus.SHIFT_ON,
        moderation_status=m.ModerationStatus.APPROVED,
        has_vehicle=True,
    )
    async_session.add(master)
    await async_session.flush()

    async_session.add(
        m.master_districts(master_id=master.id, district_id=district.id)
    )
    async_session.add(
        m.master_skills(master_id=master.id, skill_id=skill.id)
    )

    order = m.orders(
        city_id=city.id,
        district_id=district.id,
        status=m.OrderStatus.SEARCHING,
        category="ELECTRICS",
    )
    async_session.add(order)
    await async_session.commit()

    async def fake_load_config(_session):
        class _Cfg:
            rounds = 2
            sla_seconds = 120

        return _Cfg()

    async def fake_current_round(_session, _order_id):
        return 0

    async def fake_candidate_rows(**_kwargs):
        return [
            {
                "mid": master.id,
                "car": True,
                "avg_week": 8200,
                "rating": 4.7,
                "rnd": 0.05,
                "shift": True,
            }
        ]

    async def fake_send_offer(session, order_id, master_id, round_number, sla_seconds):
        await session.execute(
            insert(m.offers).values(
                order_id=order_id,
                master_id=master_id,
                round_number=round_number,
                state=m.OfferState.SENT,
                sent_at=datetime.now(UTC),
                expires_at=datetime.now(UTC) + timedelta(seconds=sla_seconds),
            )
        )
        return True

    monkeypatch.setattr(dw, "_load_config", fake_load_config)
    monkeypatch.setattr(dw, "current_round", fake_current_round)
    monkeypatch.setattr(dw, "candidate_rows", fake_candidate_rows)
    monkeypatch.setattr(dw, "send_offer", fake_send_offer)

    service = DBDistributionService(session_factory=lambda: existing_session(async_session))

    ok, result = await service.assign_auto(order.id, by_staff_id=0)

    assert ok
    assert result.code == "offer_sent"
    assert result.master_id == master.id
    assert result.deadline is not None

    offer_rows = await async_session.execute(
        select(m.offers.master_id, m.offers.state).where(m.offers.order_id == order.id)
    )
    offers = offer_rows.all()
    assert offers
    assert offers[0][0] == master.id
    assert offers[0][1] == m.OfferState.SENT

    await async_session.refresh(order)
    assert order.dist_escalated_logist_at is None

    entries = live_log.snapshot(10)
    assert any("decision=offer" in entry.message for entry in entries)
    assert not any("skip_auto" in entry.message for entry in entries)


@pytest.mark.asyncio
async def test_apply_rewards_for_commission(async_session) -> None:
    await _ensure_tables(
        async_session,
        _tables(
            m.masters.__table__,
            m.commissions.__table__,
            m.referrals.__table__,
            m.referral_rewards.__table__,
        ),
    )

    ref_l2 = m.masters(
        tg_user_id=701,
        full_name="Ref L2",
        phone="+79990000701",
        city_id=None,
        is_active=True,
        verified=True,
    )
    ref_l1 = m.masters(
        tg_user_id=702,
        full_name="Ref L1",
        phone="+79990000702",
        city_id=None,
        is_active=True,
        verified=True,
    )
    payer = m.masters(
        tg_user_id=703,
        full_name="Payer",
        phone="+79990000703",
        city_id=None,
        is_active=True,
        verified=True,
    )
    async_session.add_all([ref_l2, ref_l1, payer])
    await async_session.flush()

    async_session.add_all(
        [
            m.referrals(master_id=payer.id, referrer_id=ref_l1.id),
            m.referrals(master_id=ref_l1.id, referrer_id=ref_l2.id),
        ]
    )

    commission = m.commissions(
        order_id=1,
        master_id=payer.id,
        amount=Decimal("1000.00"),
        deadline_at=datetime.now(UTC),
        status=m.CommissionStatus.APPROVED,
        is_paid=True,
    )
    async_session.add(commission)
    await async_session.flush()

    await apply_rewards_for_commission(
        async_session,
        commission_id=commission.id,
        master_id=payer.id,
        base_amount=Decimal("1000.00"),
    )

    # idempotency check
    await apply_rewards_for_commission(
        async_session,
        commission_id=commission.id,
        master_id=payer.id,
        base_amount=Decimal("1000.00"),
    )

    rows = await async_session.execute(
        select(m.referral_rewards).order_by(m.referral_rewards.level)
    )
    rewards = rows.scalars().all()
    assert [r.level for r in rewards] == [1, 2]
    assert [r.referrer_id for r in rewards] == [ref_l1.id, ref_l2.id]
    assert [r.referred_master_id for r in rewards] == [payer.id, payer.id]
    assert [Decimal(r.amount) for r in rewards] == [Decimal("100.00"), Decimal("50.00")]
    assert [Decimal(r.percent) for r in rewards] == [Decimal("10.00"), Decimal("5.00")]


@pytest.mark.asyncio
async def test_finance_approve_creates_referral_rewards(async_session) -> None:
    await _ensure_tables(
        async_session,
        _tables(
            m.cities.__table__,
            m.masters.__table__,
            m.orders.__table__,
            m.commissions.__table__,
            m.order_status_history.__table__,
            m.referrals.__table__,
            m.referral_rewards.__table__,
        ),
    )

    city = m.cities(name="Referral City")
    async_session.add(city)
    await async_session.flush()

    ref_l2 = m.masters(
        tg_user_id=710,
        full_name="Ref L2",
        phone="+79990000710",
        city_id=city.id,
        is_active=True,
        verified=True,
    )
    ref_l1 = m.masters(
        tg_user_id=711,
        full_name="Ref L1",
        phone="+79990000711",
        city_id=city.id,
        is_active=True,
        verified=True,
    )
    payer = m.masters(
        tg_user_id=712,
        full_name="Payer",
        phone="+79990000712",
        city_id=city.id,
        is_active=True,
        verified=True,
    )
    async_session.add_all([ref_l2, ref_l1, payer])
    await async_session.flush()

    async_session.add_all(
        [
            m.referrals(master_id=payer.id, referrer_id=ref_l1.id),
            m.referrals(master_id=ref_l1.id, referrer_id=ref_l2.id),
        ]
    )

    order = m.orders(
        city_id=city.id,
        status=m.OrderStatus.PAYMENT,
        type=m.OrderType.NORMAL,
        assigned_master_id=payer.id,
        total_sum=Decimal("1500.00"),
        client_name="Client",
        client_phone="+79990000999",
    )
    async_session.add(order)
    await async_session.flush()

    commission = m.commissions(
        order_id=order.id,
        master_id=payer.id,
        amount=Decimal("800.00"),
        deadline_at=datetime.now(UTC) + timedelta(hours=3),
        status=m.CommissionStatus.WAIT_PAY,
        is_paid=False,
    )
    async_session.add(commission)
    await async_session.flush()

    finance_service = DBFinanceService(session_factory=lambda: existing_session(async_session))

    result = await finance_service.approve(
        commission.id, paid_amount=Decimal("750.50"), by_staff_id=1
    )
    assert result is True

    rows = await async_session.execute(
        select(m.referral_rewards).order_by(m.referral_rewards.level)
    )
    rewards = rows.scalars().all()
    assert len(rewards) == 2
    amounts = [Decimal(r.amount) for r in rewards]
    assert amounts == [Decimal("75.05"), Decimal("37.53")]
    assert [Decimal(r.percent) for r in rewards] == [Decimal("10.00"), Decimal("5.00")]
    assert [r.referrer_id for r in rewards] == [ref_l1.id, ref_l2.id]
    assert [r.referred_master_id for r in rewards] == [payer.id, payer.id]

@pytest.mark.asyncio
async def test_search_streets_deduplicates_similar(async_session) -> None:
    await _ensure_tables(async_session, _tables(m.districts.__table__, m.streets.__table__))
    city = m.cities(name=city_catalog.ALLOWED_CITIES[2])
    async_session.add(city)
    await async_session.flush()

    district = m.districts(city_id=city.id, name="North")
    async_session.add(district)
    await async_session.flush()

    async_session.add_all(
        [
            m.streets(city_id=city.id, district_id=district.id, name="Baker Street"),
            m.streets(city_id=city.id, district_id=district.id, name="Baker St."),
        ]
    )
    await async_session.flush()

    orders_service = DBOrdersService(session_factory=lambda: existing_session(async_session))
    results = await orders_service.search_streets(city.id, "Baker")

    names = [r.name for r in results]
    assert names.count("Baker Street") == 1
    assert not any(name == "Baker St." for name in names)


@pytest.mark.asyncio
async def test_create_order_uses_centroid_when_coordinates_missing(async_session) -> None:
    await _ensure_tables(
        async_session,
        _tables(
            m.districts.__table__,
            m.streets.__table__,
            m.orders.__table__,
            m.order_status_history.__table__,
        ),
    )
    city = m.cities(
        name="Geo City",
        timezone="Europe/Moscow",
        centroid_lat=55.75,
        centroid_lon=37.62,
    )
    async_session.add(city)
    await async_session.flush()

    district = m.districts(
        city_id=city.id,
        name="Center",
        centroid_lat=55.76,
        centroid_lon=37.6,
    )
    async_session.add(district)
    await async_session.flush()

    street = m.streets(
        city_id=city.id,
        district_id=district.id,
        name="Central Street",
        centroid_lat=55.761,
        centroid_lon=37.601,
    )
    async_session.add(street)
    await async_session.flush()

    orders_service = DBOrdersService(session_factory=lambda: existing_session(async_session))
    data = NewOrderData(
        city_id=city.id,
        district_id=None,
        street_id=street.id,
        house="10",
        apartment=None,
        address_comment=None,
        client_name="Ivan",
        client_phone="+79990000000",
        category=OrderCategory.ELECTRICS,
        description="Lamp issue",
        order_type=OrderType.NORMAL,
        timeslot_start_utc=None,
        timeslot_end_utc=None,
        timeslot_display=None,
        lat=None,
        lon=None,
        no_district=False,
        company_payment=None,
        total_sum=Decimal(0),
        created_by_staff_id=1,
    )
    order_id = await orders_service.create_order(data)

    row = await async_session.execute(select(m.orders).where(m.orders.id == order_id))
    order = row.scalar_one()
    assert order.district_id == district.id
    assert order.lat == pytest.approx(55.761)
    assert order.lon == pytest.approx(37.601)
    assert order.geocode_provider == "street_centroid"
    assert order.geocode_confidence == 80

@pytest.mark.asyncio
async def test_get_city_timezone_uses_city_value(async_session) -> None:
    await _ensure_tables(async_session, _tables())
    city = m.cities(name="Timezone City", timezone="Asia/Yekaterinburg")
    async_session.add(city)
    await async_session.flush()

    orders_service = DBOrdersService(session_factory=lambda: existing_session(async_session))
    tz_value = await orders_service.get_city_timezone(city.id)
    assert tz_value == "Asia/Yekaterinburg"
