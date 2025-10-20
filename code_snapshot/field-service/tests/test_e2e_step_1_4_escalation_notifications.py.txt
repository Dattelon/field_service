# -*- coding: utf-8 -*-
"""
E2E tests for Step 1.4: Escalation notifications should be sent only once
"""
import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from field_service.db import models as m
from field_service.services.distribution_scheduler import tick_once, _load_config

UTC = timezone.utc


@pytest_asyncio.fixture
async def test_city(async_session: AsyncSession):
    """Create test city"""
    city = m.cities(name="Test City Escalations", timezone="Europe/Moscow")
    async_session.add(city)
    await async_session.flush()
    return city


@pytest_asyncio.fixture
async def test_district(async_session: AsyncSession, test_city):
    """Create test district"""
    district = m.districts(city_id=test_city.id, name="Test District")
    async_session.add(district)
    await async_session.flush()
    return district


@pytest_asyncio.fixture
async def test_master(async_session: AsyncSession, test_city, test_district):
    """Create verified master on shift"""
    master = m.masters(
        tg_user_id=999001,
        full_name="Test Master Esc",
        city_id=test_city.id,
        verified=True,
        is_active=True,
        is_blocked=False,
        is_on_shift=True,
        shift_status=m.ShiftStatus.SHIFT_ON,
        moderation_status=m.ModerationStatus.APPROVED,
    )
    async_session.add(master)
    await async_session.flush()
    
    # Add district
    async_session.add(m.master_districts(master_id=master.id, district_id=test_district.id))
    
    # Add skill
    skill_row = await async_session.execute(select(m.skills).where(m.skills.code == "ELEC"))
    skill = skill_row.scalar_one_or_none()
    if not skill:
        skill = m.skills(code="ELEC", name="Electrician", is_active=True)
        async_session.add(skill)
        await async_session.flush()
    
    async_session.add(m.master_skills(master_id=master.id, skill_id=skill.id))
    await async_session.flush()
    return master


@pytest.mark.asyncio
async def test_logist_escalation_notification_sent_once(async_session: AsyncSession, test_city, test_district):
    """
    Test: Logist escalation notification should be sent only once
    Scenario: Order without district escalates to logist
    Expected: Notification sent once, repeated ticks don't send again
    """
    # Create order without district (will trigger immediate escalation)
    order = m.orders(
        city_id=test_city.id,
        district_id=None,  # No district triggers escalation
        no_district=True,
        category=m.OrderCategory.ELECTRICS,
        status=m.OrderStatus.SEARCHING,
        created_at=datetime.now(UTC) - timedelta(minutes=5),
    )
    async_session.add(order)
    await async_session.commit()
    
    # Load config
    cfg = await _load_config()
    
    # First tick - should escalate and send notification
    await tick_once(cfg, bot=None, alerts_chat_id=None)
    await async_session.refresh(order)
    
    assert order.dist_escalated_logist_at is not None, "Order should be escalated to logist"
    first_notified_at = order.escalation_logist_notified_at
    assert first_notified_at is not None, "Notification should be marked as sent"
    
    print(f"[TEST] First escalation: notified_at={first_notified_at.isoformat()}")
    
    # Second tick - should NOT send notification again
    await asyncio.sleep(0.5)
    await tick_once(cfg, bot=None, alerts_chat_id=None)
    await async_session.refresh(order)
    
    assert order.escalation_logist_notified_at == first_notified_at, \
        "Notification timestamp should not change on repeated ticks"
    
    print(f"[TEST] Second tick: notification NOT resent (timestamp unchanged)")
    
    # Third tick - still should not change
    await asyncio.sleep(0.5)
    await tick_once(cfg, bot=None, alerts_chat_id=None)
    await async_session.refresh(order)
    
    assert order.escalation_logist_notified_at == first_notified_at, \
        "Notification timestamp should remain unchanged after multiple ticks"
    
    print(f"[TEST] PASSED: Logist escalation notification sent only once")


@pytest.mark.asyncio
async def test_admin_escalation_notification_sent_once(async_session: AsyncSession, test_city, test_district):
    """
    Test: Admin escalation notification should be sent only once
    Scenario: Order escalated to logist, then after timeout escalates to admin
    Expected: Admin notification sent once, repeated ticks don't send again
    """
    # Create order that will escalate
    now = datetime.now(UTC)
    order = m.orders(
        city_id=test_city.id,
        district_id=test_district.id,
        category=m.OrderCategory.ELECTRICS,
        status=m.OrderStatus.SEARCHING,
        created_at=now - timedelta(minutes=20),
        # Pre-escalate to logist
        dist_escalated_logist_at=now - timedelta(minutes=15),
        escalation_logist_notified_at=now - timedelta(minutes=15),
    )
    async_session.add(order)
    await async_session.commit()
    
    # Load config
    cfg = await _load_config()
    
    # First tick - should escalate to admin and send notification
    await tick_once(cfg, bot=None, alerts_chat_id=None)
    await async_session.refresh(order)
    
    assert order.dist_escalated_admin_at is not None, "Order should be escalated to admin"
    first_admin_notified_at = order.escalation_admin_notified_at
    assert first_admin_notified_at is not None, "Admin notification should be marked as sent"
    
    print(f"[TEST] First admin escalation: notified_at={first_admin_notified_at.isoformat()}")
    
    # Second tick - should NOT send notification again
    await asyncio.sleep(0.5)
    await tick_once(cfg, bot=None, alerts_chat_id=None)
    await async_session.refresh(order)
    
    assert order.escalation_admin_notified_at == first_admin_notified_at, \
        "Admin notification timestamp should not change on repeated ticks"
    
    print(f"[TEST] Second tick: admin notification NOT resent (timestamp unchanged)")
    
    # Third tick - still should not change
    await asyncio.sleep(0.5)
    await tick_once(cfg, bot=None, alerts_chat_id=None)
    await async_session.refresh(order)
    
    assert order.escalation_admin_notified_at == first_admin_notified_at, \
        "Admin notification timestamp should remain unchanged after multiple ticks"
    
    print(f"[TEST] PASSED: Admin escalation notification sent only once")


@pytest.mark.asyncio
async def test_escalation_notifications_reset_on_offer(
    async_session: AsyncSession, test_city, test_district, test_master
):
    """
    Test: Escalation notification flags should reset when offer is sent
    Scenario: Order escalated, then offer sent, then escalated again
    Expected: New notification should be sent after reset
    """
    # Create order that will escalate
    now = datetime.now(UTC)
    order = m.orders(
        city_id=test_city.id,
        district_id=None,  # Will escalate immediately
        no_district=True,
        category=m.OrderCategory.ELECTRICS,
        status=m.OrderStatus.SEARCHING,
        created_at=now - timedelta(minutes=5),
    )
    async_session.add(order)
    await async_session.commit()
    
    # Load config
    cfg = await _load_config()
    
    # First tick - escalate
    await tick_once(cfg, bot=None, alerts_chat_id=None)
    await async_session.refresh(order)
    
    assert order.escalation_logist_notified_at is not None, "First notification should be sent"
    first_notified_at = order.escalation_logist_notified_at
    
    print(f"[TEST] First escalation: notified_at={first_notified_at.isoformat()}")
    
    # Simulate resolution: add district and create offer
    order.district_id = test_district.id
    order.no_district = False
    async_session.add(order)
    
    offer = m.offers(
        order_id=order.id,
        master_id=test_master.id,
        round_number=1,
        state=m.OfferState.SENT,
        sent_at=now,
        expires_at=now + timedelta(seconds=120),
    )
    async_session.add(offer)
    await async_session.commit()
    
    # Tick with active offer - should reset escalation flags
    await tick_once(cfg, bot=None, alerts_chat_id=None)
    await async_session.refresh(order)
    
    assert order.dist_escalated_logist_at is None, "Escalation should be reset"
    assert order.escalation_logist_notified_at is None, "Notification flag should be reset"
    
    print(f"[TEST] After offer sent: escalation flags reset")
    
    # Expire offer
    offer.state = m.OfferState.EXPIRED
    offer.responded_at = now
    async_session.add(offer)
    
    # Remove district again to trigger new escalation
    order.district_id = None
    order.no_district = True
    async_session.add(order)
    await async_session.commit()
    
    # New tick - should escalate again and send NEW notification
    await tick_once(cfg, bot=None, alerts_chat_id=None)
    await async_session.refresh(order)
    
    assert order.dist_escalated_logist_at is not None, "Should escalate again"
    second_notified_at = order.escalation_logist_notified_at
    assert second_notified_at is not None, "New notification should be sent"
    assert second_notified_at > first_notified_at, "New notification should have newer timestamp"
    
    print(f"[TEST] Second escalation: new notified_at={second_notified_at.isoformat()}")
    print(f"[TEST] PASSED: Notifications reset correctly on offer")


@pytest.mark.asyncio
async def test_no_candidates_escalation_notification(
    async_session: AsyncSession, test_city, test_district
):
    """
    Test: Escalation notification when no candidates available
    Scenario: Order with valid district but no available masters
    Expected: Notification sent once after rounds exhausted
    """
    # Create order with valid district but no masters
    now = datetime.now(UTC)
    order = m.orders(
        city_id=test_city.id,
        district_id=test_district.id,
        category=m.OrderCategory.ELECTRICS,
        status=m.OrderStatus.SEARCHING,
        created_at=now - timedelta(minutes=5),
    )
    async_session.add(order)
    await async_session.commit()
    
    # Load config
    cfg = await _load_config()
    
    # First tick - round 1, no candidates
    await tick_once(cfg, bot=None, alerts_chat_id=None)
    await async_session.refresh(order)
    
    # Check round 1 happened (no escalation yet)
    offers_count = await async_session.scalar(
        select(m.func.count()).select_from(m.offers).where(m.offers.order_id == order.id)
    )
    assert offers_count == 0, "No offers should be created (no candidates)"
    
    # Second tick - round 2, should exhaust rounds and escalate
    await tick_once(cfg, bot=None, alerts_chat_id=None)
    await async_session.refresh(order)
    
    assert order.dist_escalated_logist_at is not None, "Should escalate after rounds exhausted"
    first_notified_at = order.escalation_logist_notified_at
    assert first_notified_at is not None, "Notification should be sent"
    
    print(f"[TEST] Escalated after no candidates: notified_at={first_notified_at.isoformat()}")
    
    # Third tick - should NOT send notification again
    await asyncio.sleep(0.5)
    await tick_once(cfg, bot=None, alerts_chat_id=None)
    await async_session.refresh(order)
    
    assert order.escalation_logist_notified_at == first_notified_at, \
        "Notification should not be resent"
    
    print(f"[TEST] PASSED: No candidates escalation notification sent once")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
