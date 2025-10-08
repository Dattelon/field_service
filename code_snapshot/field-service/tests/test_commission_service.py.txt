from __future__ import annotations

import sqlalchemy as sa

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from field_service.db import models as m
from field_service.services.commission_service import CommissionService

UTC = timezone.utc


@pytest.mark.asyncio
async def test_compute_rate_thresholds() -> None:
    assert CommissionService.compute_rate(Decimal("6999.99")) == Decimal("0.50")
    assert CommissionService.compute_rate(Decimal("7000")) == Decimal("0.40")
    assert CommissionService.compute_rate("7000.00") == Decimal("0.40")
    assert CommissionService.compute_rate(None) == Decimal("0.50")


@pytest.mark.asyncio
async def test_create_commission_basic_flow(async_session) -> None:
    await _seed_owner_staff(async_session)

    city = m.cities(name="Testopolis")
    async_session.add(city)
    await async_session.flush()

    master = m.masters(
        tg_user_id=111,
        full_name=" ",
        phone="+79990001122",
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
        type=m.OrderType.NORMAL,
    )
    async_session.add(order)
    await async_session.flush()

    service = CommissionService(async_session)

    before = datetime.now(UTC)
    commission = await service.create_for_order(order.id)
    after = datetime.now(UTC)

    assert commission is not None
    assert commission.rate == Decimal("0.50")
    assert commission.amount == Decimal("1500.00")
    assert commission.status == m.CommissionStatus.WAIT_PAY
    assert commission.pay_to_snapshot.get("card_number_last4") == "9012"
    assert commission.pay_to_snapshot.get("methods") == ["card", "sbp"]

    expected_lower = before + timedelta(hours=3)
    expected_upper = after + timedelta(hours=3, seconds=1)
    assert expected_lower <= commission.deadline_at <= expected_upper

    # idempotent check
    same = await service.create_for_order(order.id)
    assert same.id == commission.id


@pytest.mark.asyncio
async def test_create_commission_high_avg_rate(async_session) -> None:
    await _seed_owner_staff(async_session)

    city = m.cities(name="Rate City")
    async_session.add(city)
    await async_session.flush()

    master = m.masters(
        tg_user_id=222,
        full_name=" ϸ",
        phone="+79991111111",
        city_id=city.id,
        is_active=True,
        is_on_shift=True,
        verified=True,
        shift_status=m.ShiftStatus.SHIFT_ON,
        moderation_status=m.ModerationStatus.APPROVED,
    )
    async_session.add(master)
    await async_session.flush()

    # closed order within 7 days to bump avg_week_check
    closed_order = m.orders(
        city_id=city.id,
        district_id=None,
        status=m.OrderStatus.CLOSED,
        total_sum=Decimal("8000"),
        assigned_master_id=master.id,
        type=m.OrderType.NORMAL,
        created_at=datetime.now(UTC) - timedelta(days=1),
    )
    async_session.add(closed_order)
    await async_session.flush()

    new_order = m.orders(
        city_id=city.id,
        district_id=None,
        status=m.OrderStatus.PAYMENT,
        total_sum=Decimal("4000"),
        assigned_master_id=master.id,
        type=m.OrderType.NORMAL,
    )
    async_session.add(new_order)
    await async_session.flush()

    commission = await CommissionService(async_session).create_for_order(new_order.id)

    assert commission is not None
    assert commission.rate == Decimal("0.40")
    assert commission.amount == Decimal("1600.00")


@pytest.mark.asyncio
async def test_create_commission_skips_guarantee(async_session) -> None:
    await _seed_owner_staff(async_session)

    city = m.cities(name="Warranty City")
    async_session.add(city)
    await async_session.flush()

    master = m.masters(
        tg_user_id=333,
        full_name=" ",
        phone="+79992223344",
        city_id=city.id,
        is_active=True,
        is_on_shift=True,
        verified=True,
        shift_status=m.ShiftStatus.SHIFT_ON,
        moderation_status=m.ModerationStatus.APPROVED,
    )
    async_session.add(master)
    await async_session.flush()

    guarantee_order = m.orders(
        city_id=city.id,
        district_id=None,
        status=m.OrderStatus.PAYMENT,
        total_sum=Decimal("0"),
        company_payment=Decimal("2500"),
        assigned_master_id=master.id,
        type=m.OrderType.GUARANTEE,
    )
    async_session.add(guarantee_order)
    await async_session.flush()

    commission = await CommissionService(async_session).create_for_order(guarantee_order.id)
    assert commission is None

    # Ensure nothing was created
    count = (
        await async_session.execute(
            sa.select(m.commissions).where(m.commissions.order_id == guarantee_order.id)
        )
    ).scalars().all()
    assert count == []


async def _seed_owner_staff(session) -> None:
    session.add(
        m.staff_users(
            tg_user_id=9001,
            role=m.StaffRole.ADMIN,
            full_name='Owner',
            phone='+70000000000',
            is_active=True,
            commission_requisites={
                'methods': ['card', 'sbp'],
                'card_number': '2200123456789012',
                'card_holder': 'Ivanov I.I.',
                'card_bank': 'T-Bank',
                'sbp_phone': '+79991234567',
                'sbp_bank': 'T-Bank',
                'sbp_qr_file_id': 'qr123',
                'other_text': 'cash',
                'comment_template': 'Komissiya #<order_id> ot <master_fio>',
            },
        )
    )
    await session.flush()
