from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from field_service.bots.admin_bot.services_db import DBFinanceService, DBSettingsService
from field_service.db import models as m

UTC = timezone.utc


@pytest.mark.asyncio
async def test_owner_requisites_update_and_fetch(async_session) -> None:
    admin_primary = m.staff_users(
        tg_user_id=101,
        role=m.StaffRole.ADMIN,
        full_name='Primary',
        phone='+70000000001',
        commission_requisites={},
    )
    admin_effective = m.staff_users(
        tg_user_id=102,
        role=m.StaffRole.ADMIN,
        full_name='Effective',
        phone='+70000000002',
        commission_requisites={
            'methods': ['card', 'sbp'],
            'card_number': '2200123456789012',
            'card_holder': 'Owner',
            'card_bank': 'T-Bank',
            'sbp_phone': '+79991234567',
            'sbp_bank': 'T-Bank',
            'sbp_qr_file_id': 'qr1',
            'other_text': '',
            'comment_template': 'Komissiya #<order_id> ot <master_fio>',
        },
    )
    async_session.add_all([admin_primary, admin_effective])
    await async_session.flush()
    await async_session.commit()

    session_maker = async_sessionmaker(async_session.bind, expire_on_commit=False)

    @asynccontextmanager
    async def factory():
        async with session_maker() as session:
            yield session

    service = DBSettingsService(session_factory=factory)

    effective = await service.get_owner_pay_requisites()
    assert effective['methods'] == ['card', 'sbp']

    fallback = await service.get_owner_pay_requisites(staff_id=admin_primary.id)
    assert fallback['methods'] == ['card', 'sbp']

    payload = {
        'methods': ['sbp'],
        'card_number': '',
        'card_holder': '',
        'card_bank': '',
        'sbp_phone': '+79990000000',
        'sbp_bank': 'New Bank',
        'sbp_qr_file_id': '',
        'other_text': 'cash only',
        'comment_template': 'Komissiya #<order_id>',
    }
    await service.update_owner_pay_requisites(admin_primary.id, payload)

    updated = await service.get_owner_pay_requisites(staff_id=admin_primary.id)
    assert updated['methods'] == ['sbp']
    assert updated['sbp_bank'] == 'New Bank'
    assert updated['other_text'] == 'cash only'


@pytest.mark.asyncio
async def test_wait_pay_recipients(async_session) -> None:
    city = m.cities(name='City')
    async_session.add(city)
    await async_session.flush()

    master_with_chat = m.masters(
        tg_user_id=555,
        full_name='With Chat',
        phone='+79990000011',
        city_id=city.id,
        is_active=True,
        verified=True,
    )
    master_no_chat = m.masters(
        tg_user_id=None,
        full_name='No Chat',
        phone='+79990000022',
        city_id=city.id,
        is_active=True,
        verified=True,
    )
    async_session.add_all([master_with_chat, master_no_chat])
    await async_session.flush()

    order1 = m.orders(city_id=city.id, status=m.OrderStatus.PAYMENT, assigned_master_id=master_with_chat.id)
    order2 = m.orders(city_id=city.id, status=m.OrderStatus.PAYMENT, assigned_master_id=master_no_chat.id)
    async_session.add_all([order1, order2])
    await async_session.flush()

    commission1 = m.commissions(
        order_id=order1.id,
        master_id=master_with_chat.id,
        amount=Decimal('100.00'),
        rate=Decimal('0.50'),
        status=m.CommissionStatus.WAIT_PAY,
        deadline_at=datetime.now(UTC) + timedelta(hours=1),
        is_paid=False,
        has_checks=False,
        pay_to_snapshot={},
    )
    commission2 = m.commissions(
        order_id=order2.id,
        master_id=master_no_chat.id,
        amount=Decimal('200.00'),
        rate=Decimal('0.50'),
        status=m.CommissionStatus.WAIT_PAY,
        deadline_at=datetime.now(UTC) + timedelta(hours=1),
        is_paid=False,
        has_checks=False,
        pay_to_snapshot={},
    )
    async_session.add_all([commission1, commission2])
    await async_session.flush()
    # Ensure data is visible to a new session used by service layer
    await async_session.commit()

    session_maker = async_sessionmaker(async_session.bind, expire_on_commit=False)

    @asynccontextmanager
    async def factory():
        async with session_maker() as session:
            yield session

    finance_service = DBFinanceService(session_factory=factory)
    recipients = await finance_service.list_wait_pay_recipients()

    assert len(recipients) == 1
    recipient = recipients[0]
    assert recipient.master_id == master_with_chat.id
    assert recipient.tg_user_id == master_with_chat.tg_user_id
