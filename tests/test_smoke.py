from __future__ import annotations

import types
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import sqlalchemy as sa

import pytest

from field_service.db import models as m
from field_service.services import distribution_worker as dw
from field_service.services.commission_service import (
    apply_overdue_commissions,
    CommissionOverdueEvent,
    CommissionService,
)
from field_service.services.onboarding_service import (
    ensure_master,
    mark_code_used,
    normalize_phone,
    parse_name,
    validate_access_code,
)

UTC = timezone.utc


@pytest.mark.asyncio
async def test_distribution_two_rounds_and_escalation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = types.SimpleNamespace(
        rounds_sent=0,
        active_offer=False,
        offer_history=[],
        escalated=False,
    )

    async def fake_has_active_sent_offer(session, order_id: int) -> bool:
        return state.active_offer

    async def fake_finalize(session, order_id: int) -> bool:
        return False

    async def fake_current_round(session, order_id: int) -> int:
        return state.rounds_sent

    async def fake_candidate_rows(
        session,
        order_id: int,
        city_id: int,
        district_id: int,
        preferred_master_id,
        skill_code: str,
        limit: int,
        force_preferred_first: bool = False,
    ):
        if state.rounds_sent == 0:
            return [
                {"mid": 1, "car": False, "avg_week": 0.0, "rating": 5.0, "rnd": 0.1},
                {"mid": 2, "car": True, "avg_week": 0.0, "rating": 4.5, "rnd": 0.2},
            ]
        if state.rounds_sent == 1:
            return [
                {"mid": 2, "car": True, "avg_week": 0.0, "rating": 4.5, "rnd": 0.2},
            ]
        return []

    async def fake_send_offer(
        session, order_id: int, master_id: int, round_number: int, sla_seconds: int
    ) -> bool:
        state.offer_history.append(round_number)
        state.rounds_sent = round_number
        state.active_offer = True
        return True

    def fake_log_escalate(order_id: int) -> str:
        state.escalated = True
        return f"escalate {order_id}"

    monkeypatch.setattr(dw, "has_active_sent_offer", fake_has_active_sent_offer)
    monkeypatch.setattr(dw, "finalize_accepted_if_any", fake_finalize)
    monkeypatch.setattr(dw, "current_round", fake_current_round)
    monkeypatch.setattr(dw, "candidate_rows", fake_candidate_rows)
    monkeypatch.setattr(dw, "send_offer", fake_send_offer)
    monkeypatch.setattr(dw, "log_escalate", fake_log_escalate)

    cfg = dw.DistConfig(sla_seconds=120, rounds=2, escalate_to_admin_after_min=10)
    order = types.SimpleNamespace(
        id=101,
        city_id=1,
        district_id=1,
        preferred_master_id=None,
        status=m.OrderStatus.SEARCHING,
        category="ELECTRICS",
    )

    await dw.process_one_order(session=None, cfg=cfg, o=order)
    assert state.offer_history == [1]

    state.active_offer = False  # simulate SLA expiration
    await dw.process_one_order(session=None, cfg=cfg, o=order)
    assert state.offer_history == [1, 2]

    state.active_offer = False
    await dw.process_one_order(session=None, cfg=cfg, o=order)
    assert state.offer_history == [1, 2]
    assert state.escalated is True


@pytest.mark.asyncio
async def test_onboarding_validations(async_session) -> None:
    invite = m.master_invite_codes(
        code="ABC123",
        issued_by_staff_id=None,
        city_id=None,
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    async_session.add(invite)
    await async_session.flush()

    master = await ensure_master(async_session, tg_user_id=42)

    record = await validate_access_code(async_session, "ABC123")
    assert record.id == invite.id

    parts = parse_name("  ")
    phone = normalize_phone("8 (999) 123-45-67")

    master.full_name = " ".join(
        filter(None, [parts.last_name, parts.first_name, parts.middle_name])
    )
    master.phone = phone
    await mark_code_used(async_session, record, master.id)
    await async_session.commit()

    refreshed = await async_session.get(m.masters, master.id)
    assert refreshed is not None
    assert refreshed.full_name == "  "
    assert refreshed.phone == "+79991234567"

    updated_invite = await async_session.get(m.master_invite_codes, invite.id)
    assert updated_invite is not None
    assert updated_invite.used_by_master_id == master.id


@pytest.mark.asyncio
async def test_commission_creation_and_overdue_block(async_session) -> None:
    owner = m.staff_users(
        tg_user_id=500,
        role=m.StaffRole.ADMIN,
        full_name='Owner',
        phone='+70000000000',
        commission_requisites={
            'methods': ['card'],
            'card_number': '4000123412341234',
            'card_holder': 'Owner',
            'card_bank': 'Test Bank',
            'sbp_phone': '',
            'sbp_bank': '',
            'sbp_qr_file_id': '',
            'other_text': '',
            'comment_template': 'Komissiya #<order_id>',
        },
    )
    async_session.add(owner)
    await async_session.flush()

    city = m.cities(name="Test City")
    async_session.add(city)
    await async_session.flush()

    master = m.masters(
        tg_user_id=1001,
        full_name="Test Master",
        phone="+70000000001",
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
        total_sum=3000,
        assigned_master_id=master.id,
    )
    async_session.add(order)
    await async_session.flush()

    commission = await CommissionService(async_session).create_for_order(order.id)
    assert commission is not None
    assert commission.status == m.CommissionStatus.WAIT_PAY
    assert commission.amount == Decimal("1500.00")
    commission_id = commission.id
    master_id = master.id

    commission.deadline_at = datetime.now(UTC) - timedelta(hours=4)
    await async_session.flush()

    events = await apply_overdue_commissions(async_session, now=datetime.now(UTC))
    await async_session.commit()

    assert [event.master_id for event in events] == [master_id]
    assert [event.commission_id for event in events] == [commission_id]

    async_session.expire_all()
    updated_commission = (
        await async_session.execute(
            sa.select(m.commissions).where(m.commissions.id == commission_id)
        )
    ).scalar_one()
    assert updated_commission.status == m.CommissionStatus.OVERDUE
    assert updated_commission.blocked_applied is True

    updated_master = (
        await async_session.execute(
            sa.select(m.masters).where(m.masters.id == master_id)
        )
    ).scalar_one()
    assert updated_master.is_blocked is True
    assert updated_master.blocked_reason == "commission_overdue"
