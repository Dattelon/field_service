from datetime import datetime, time, timezone, timedelta
from zoneinfo import ZoneInfo
from unittest.mock import AsyncMock

import pytest
import sqlalchemy as sa

from field_service.db import models as m
from field_service.services.distribution import wakeup
from field_service.services import distribution_worker


@pytest.mark.asyncio
async def test_wakeup_promotes_at_start(async_session, monkeypatch):
    await async_session.execute(
        m.cities.__table__.insert().values(id=1, name="Test City", is_active=True)
    )
    await async_session.execute(
        m.orders.__table__.insert().values(
            id=100,
            city_id=1,
            status=m.OrderStatus.DEFERRED,
            timeslot_start_utc=datetime(2025, 9, 15, 10, 0, tzinfo=timezone.utc),
            timeslot_end_utc=datetime(2025, 9, 15, 12, 0, tzinfo=timezone.utc),
        )
    )
    await async_session.commit()

    monkeypatch.setattr(
        wakeup.settings_service,
        "get_working_window",
        AsyncMock(return_value=(time(10, 0), time(20, 0))),
    )
    monkeypatch.setattr(
        wakeup, "_resolve_city_timezone",
        AsyncMock(return_value=ZoneInfo("UTC")),
    )

    now_utc = datetime(2025, 9, 15, 10, 0, tzinfo=timezone.utc)
    awakened, notices = await wakeup.run(async_session, now_utc=now_utc)

    assert notices == []
    assert len(awakened) == 1
    assert awakened[0].order_id == 100
    assert awakened[0].city_name == "Test City"
    assert awakened[0].target_local.tzinfo == ZoneInfo("UTC")

    order = await async_session.get(m.orders, 100)
    assert order.status == m.OrderStatus.SEARCHING

    history_rows = await async_session.execute(
        m.order_status_history.__table__.select().where(
            m.order_status_history.order_id == 100
        )
    )
    history = history_rows.mappings().all()
    assert history and history[-1]["to_status"] == m.OrderStatus.SEARCHING


@pytest.mark.asyncio
async def test_wakeup_notices_only_once(async_session, monkeypatch):
    await async_session.execute(
        m.cities.__table__.insert().values(id=2, name="Another City", is_active=True)
    )
    await async_session.execute(
        m.orders.__table__.insert().values(
            id=200,
            city_id=2,
            status=m.OrderStatus.DEFERRED,
            timeslot_start_utc=datetime(2025, 9, 15, 10, 0, tzinfo=timezone.utc),
            timeslot_end_utc=datetime(2025, 9, 15, 12, 0, tzinfo=timezone.utc),
        )
    )
    await async_session.commit()

    monkeypatch.setattr(
        wakeup.settings_service,
        "get_working_window",
        AsyncMock(return_value=(time(10, 0), time(20, 0))),
    )
    monkeypatch.setattr(
        wakeup, "_resolve_city_timezone",
        AsyncMock(return_value=ZoneInfo("UTC")),
    )

    before_start = datetime(2025, 9, 15, 8, 0, tzinfo=timezone.utc)
    awakened, notices = await wakeup.run(async_session, now_utc=before_start)
    assert awakened == []
    assert len(notices) == 1
    assert notices[0].order_id == 200

    # Second invocation before start should not duplicate notice
    awakened2, notices2 = await wakeup.run(async_session, now_utc=before_start)
    assert awakened2 == []
    assert notices2 == []

    at_start = datetime(2025, 9, 15, 10, 0, tzinfo=timezone.utc)
    awakened3, notices3 = await wakeup.run(async_session, now_utc=at_start)
    assert notices3 == []
    assert any(order.order_id == 200 for order in awakened3)
    assert wakeup._DEFERRED_LOGGED == set()


@pytest.mark.asyncio
async def test_distribution_no_candidates_escalates_and_admin(async_session, monkeypatch):
    async def fake_has_active_sent_offer(session, order_id):
        now = datetime.now(timezone.utc)
        result = await session.execute(
            sa.select(m.offers.id)
            .where(m.offers.order_id == order_id)
            .where(m.offers.state == m.OfferState.SENT)
            .where(
                sa.or_(
                    m.offers.expires_at.is_(None),
                    m.offers.expires_at > now,
                )
            )
        )
        return result.scalar_one_or_none() is not None

    async def fake_send_offer(session, order_id, master_id, round_number, sla_seconds):
        existing = await session.execute(
            sa.select(m.offers.id)
            .where(m.offers.order_id == order_id)
            .where(m.offers.master_id == master_id)
        )
        if existing.scalar_one_or_none():
            return False
        offer = m.offers(
            order_id=order_id,
            master_id=master_id,
            round_number=round_number,
            state=m.OfferState.SENT,
            sent_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=sla_seconds),
        )
        session.add(offer)
        await session.flush()
        return True

    async def fake_candidate_rows(session, order_id, city_id, district_id, preferred_master_id, skill_code, limit, force_preferred_first=False):
        query = (
            sa.select(
                m.masters.id,
                m.masters.has_vehicle,
                m.masters.rating,
            )
            .join(m.master_districts, m.master_districts.master_id == m.masters.id)
            .join(m.master_skills, m.master_skills.master_id == m.masters.id)
            .join(m.skills, m.skills.id == m.master_skills.skill_id)
            .where(m.masters.city_id == city_id)
            .where(m.master_districts.district_id == district_id)
            .where(m.skills.code == skill_code)
            .where(m.masters.is_active.is_(True))
            .where(m.masters.is_blocked.is_(False))
            .where(m.masters.verified.is_(True))
            .where(m.masters.is_on_shift.is_(True))
        )
        try:
            result = await session.execute(query)
        except sa.exc.OperationalError:
            return []
        rows = [
            {
                "mid": int(row.id),
                "car": bool(row.has_vehicle),
                "avg_week": 0.0,
                "rating": float(row.rating or 0),
                "shift": True,
                "rnd": 0.0,
            }
            for row in result
        ]
        rows.sort(key=lambda item: (item["car"], item["rating"]), reverse=True)
        if force_preferred_first and preferred_master_id:
            rows.sort(key=lambda item: 1 if item["mid"] == preferred_master_id else 0, reverse=True)
        return rows[:limit]

    monkeypatch.setattr(distribution_worker, "has_active_sent_offer", fake_has_active_sent_offer)
    monkeypatch.setattr(distribution_worker, "send_offer", fake_send_offer)
    monkeypatch.setattr(distribution_worker, "candidate_rows", fake_candidate_rows)

    city = m.cities(name="Escalate City", is_active=True)
    district = m.districts(city=city, name="North")
    async_session.add_all([city, district])
    await async_session.flush()

    order = m.orders(
        city_id=city.id,
        district_id=district.id,
        status=m.OrderStatus.SEARCHING,
        category="ELECTRICS",
        type=m.OrderType.NORMAL,
        no_district=False,
    )
    async_session.add(order)
    await async_session.commit()

    cfg = distribution_worker.DistConfig(
        sla_seconds=120, rounds=2, escalate_to_admin_after_min=10
    )

    order_entity = await async_session.get(m.orders, order.id)
    await distribution_worker.process_one_order(async_session, cfg, order_entity)
    await async_session.commit()

    refreshed = await async_session.get(m.orders, order.id)
    assert refreshed.dist_escalated_logist_at is not None
    assert refreshed.dist_escalated_admin_at is None

    old_stamp = refreshed.dist_escalated_logist_at - timedelta(minutes=11)
    await async_session.execute(
        sa.update(m.orders)
        .where(m.orders.id == order.id)
        .values(dist_escalated_logist_at=old_stamp, dist_escalated_admin_at=None)
    )
    await async_session.commit()

    updated_entity = await async_session.get(m.orders, order.id)
    await distribution_worker._maybe_escalate_admin(async_session, cfg, updated_entity)
    await async_session.commit()

    final = await async_session.get(m.orders, order.id)
    assert final.dist_escalated_admin_at is not None


@pytest.mark.asyncio
async def test_guarantee_decline_blocks_master_and_advances_round(async_session, monkeypatch):
    engine = async_session.bind
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync_conn: m.skills.__table__.create(sync_conn, checkfirst=True))
        await conn.run_sync(lambda sync_conn: m.master_skills.__table__.create(sync_conn, checkfirst=True))
        await conn.run_sync(lambda sync_conn: m.master_districts.__table__.create(sync_conn, checkfirst=True))

    async def fake_has_active_sent_offer(session, order_id):
        now = datetime.now(timezone.utc)
        result = await session.execute(
            sa.select(m.offers.id)
            .where(m.offers.order_id == order_id)
            .where(m.offers.state == m.OfferState.SENT)
            .where(
                sa.or_(
                    m.offers.expires_at.is_(None),
                    m.offers.expires_at > now,
                )
            )
        )
        return result.scalar_one_or_none() is not None

    async def fake_send_offer(session, order_id, master_id, round_number, sla_seconds):
        existing = await session.execute(
            sa.select(m.offers.id)
            .where(m.offers.order_id == order_id)
            .where(m.offers.master_id == master_id)
        )
        if existing.scalar_one_or_none():
            return False
        offer = m.offers(
            order_id=order_id,
            master_id=master_id,
            round_number=round_number,
            state=m.OfferState.SENT,
            sent_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=sla_seconds),
        )
        session.add(offer)
        await session.flush()
        return True

    async def fake_autoblock_guarantee_declines(session):
        rows = await session.execute(
            sa.select(m.offers.master_id)
            .join(m.orders, m.orders.id == m.offers.order_id)
            .where(m.offers.state == m.OfferState.DECLINED)
            .where(m.orders.status == m.OrderStatus.GUARANTEE)
            .where(m.orders.preferred_master_id == m.offers.master_id)
        )
        master_ids = {int(row[0]) for row in rows}
        updated = 0
        for master_id in master_ids:
            result = await session.execute(
                sa.update(m.masters)
                .where(m.masters.id == master_id)
                .where(m.masters.is_blocked.is_(False))
                .values(
                    is_blocked=True,
                    is_active=False,
                    blocked_reason='guarantee_refusal',
                    blocked_at=datetime.now(timezone.utc),
                )
            )
            updated += result.rowcount or 0
        return updated

    async def fake_candidate_rows(session, order_id, city_id, district_id, preferred_master_id, skill_code, limit, force_preferred_first=False):
        query = (
            sa.select(
                m.masters.id,
                m.masters.has_vehicle,
                m.masters.rating,
            )
            .join(m.master_districts, m.master_districts.master_id == m.masters.id)
            .join(m.master_skills, m.master_skills.master_id == m.masters.id)
            .join(m.skills, m.skills.id == m.master_skills.skill_id)
            .where(m.masters.city_id == city_id)
            .where(m.master_districts.district_id == district_id)
            .where(m.skills.code == skill_code)
            .where(m.masters.is_active.is_(True))
            .where(m.masters.is_blocked.is_(False))
            .where(m.masters.verified.is_(True))
            .where(m.masters.is_on_shift.is_(True))
        )
        result = await session.execute(query)
        rows = [
            {
                "mid": int(row.id),
                "car": bool(row.has_vehicle),
                "avg_week": 0.0,
                "rating": float(row.rating or 0),
                "shift": True,
                "rnd": 0.0,
            }
            for row in result
        ]
        rows.sort(key=lambda item: (item["car"], item["rating"]), reverse=True)
        if force_preferred_first and preferred_master_id:
            rows.sort(key=lambda item: 1 if item["mid"] == preferred_master_id else 0, reverse=True)
        return rows[:limit]

    monkeypatch.setattr(distribution_worker, "has_active_sent_offer", fake_has_active_sent_offer)
    monkeypatch.setattr(distribution_worker, "send_offer", fake_send_offer)
    monkeypatch.setattr(distribution_worker, "autoblock_guarantee_declines", fake_autoblock_guarantee_declines)
    monkeypatch.setattr(distribution_worker, "candidate_rows", fake_candidate_rows)

    city = m.cities(name="Guarantee Town", is_active=True)
    district = m.districts(city=city, name="Central")
    skill = m.skills(code="ELEC", name="Electrics", is_active=True)
    async_session.add_all([city, district, skill])
    await async_session.flush()

    master_one = m.masters(
        full_name="Master One",
        phone="+70000000001",
        city_id=city.id,
        has_vehicle=True,
        rating=4.8,
        is_active=True,
        is_blocked=False,
        is_on_shift=True,
        verified=True,
    )
    master_two = m.masters(
        full_name="Master Two",
        phone="+70000000002",
        city_id=city.id,
        has_vehicle=False,
        rating=4.5,
        is_active=True,
        is_blocked=False,
        is_on_shift=True,
        verified=True,
    )
    async_session.add_all([master_one, master_two])
    await async_session.flush()

    async_session.add_all(
        [
            m.master_districts(master_id=master_one.id, district_id=district.id),
            m.master_districts(master_id=master_two.id, district_id=district.id),
            m.master_skills(master_id=master_one.id, skill_id=skill.id),
            m.master_skills(master_id=master_two.id, skill_id=skill.id),
        ]
    )

    order = m.orders(
        city_id=city.id,
        district_id=district.id,
        status=m.OrderStatus.GUARANTEE,
        category="ELECTRICS",
        type=m.OrderType.GUARANTEE,
        preferred_master_id=master_one.id,
    )
    async_session.add(order)
    await async_session.commit()

    cfg = distribution_worker.DistConfig(
        sla_seconds=120, rounds=2, escalate_to_admin_after_min=10
    )

    order_entity = await async_session.get(m.orders, order.id)
    await distribution_worker.process_one_order(async_session, cfg, order_entity)
    await async_session.commit()

    offer_rows = await async_session.execute(
        sa.select(m.offers).where(m.offers.order_id == order.id)
    )
    offers = offer_rows.scalars().all()
    assert len(offers) == 1
    first_offer = offers[0]
    assert first_offer.master_id == master_one.id
    assert first_offer.round_number == 1

    await async_session.execute(
        sa.update(m.offers)
        .where(m.offers.id == first_offer.id)
        .values(
            state=m.OfferState.DECLINED,
            responded_at=datetime.now(timezone.utc),
        )
    )
    await async_session.commit()

    blocked = await distribution_worker.autoblock_guarantee_declines(async_session)
    await async_session.commit()
    assert blocked == 1

    master_one_state = await async_session.get(m.masters, master_one.id)
    assert master_one_state.is_blocked is True
    assert master_one_state.is_active is False

    order_entity = await async_session.get(m.orders, order.id)
    await distribution_worker.process_one_order(async_session, cfg, order_entity)
    await async_session.commit()

    offer_rows = await async_session.execute(
        sa.select(m.offers)
        .where(m.offers.order_id == order.id)
        .order_by(m.offers.round_number)
    )
    offers = offer_rows.scalars().all()
    assert len(offers) == 2
    assert offers[1].master_id == master_two.id
    assert offers[1].round_number == 2

@pytest.mark.asyncio
async def test_wakeup_uses_city_timezone(async_session, monkeypatch) -> None:
    await async_session.execute(
        m.cities.__table__.insert().values(
            id=3,
            name="Zone City",
            is_active=True,
            timezone="Asia/Yekaterinburg",
        )
    )
    await async_session.execute(
        m.orders.__table__.insert().values(
            id=300,
            city_id=3,
            status=m.OrderStatus.DEFERRED,
            timeslot_start_utc=None,
            timeslot_end_utc=None,
        )
    )
    await async_session.commit()

    monkeypatch.setattr(
        wakeup.settings_service,
        "get_working_window",
        AsyncMock(return_value=(time(10, 0), time(20, 0))),
    )
    wakeup._DEFERRED_LOGGED.clear()

    now_utc = datetime(2025, 9, 15, 5, 0, tzinfo=timezone.utc)
    awake, notices = await wakeup.run(async_session, now_utc=now_utc)

    assert not notices
    assert len(awake) == 1
    assert awake[0].order_id == 300
    assert awake[0].target_local.tzinfo == ZoneInfo("Asia/Yekaterinburg")
