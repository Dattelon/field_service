"""
Тесты для watchdog_expired_offers - автоматическое истечение офферов.
"""
import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, text

from field_service.db import models as m
from field_service.services.watchdogs import watchdog_expired_offers


UTC = timezone.utc


@pytest.fixture
async def sample_order(session):
    """Создать тестовый заказ."""
    city_row = await session.execute(select(m.cities).limit(1))
    city = city_row.scalar_one()
    
    district_row = await session.execute(
        select(m.districts).where(m.districts.city_id == city.id).limit(1)
    )
    district = district_row.scalar_one_or_none()
    
    order = m.orders(
        city_id=city.id,
        district_id=district.id if district else None,
        status=m.OrderStatus.SEARCHING,
        category=m.OrderCategory.ELECTRICS,
        address="Test Address",
        client_phone="+79001234567",
        visit_date=datetime.now(UTC).date(),
        slot_start="10:00",
        slot_end="12:00",
    )
    session.add(order)
    await session.flush()
    return order


@pytest.fixture
async def sample_master(session):
    """Создать тестового мастера."""
    city_row = await session.execute(select(m.cities).limit(1))
    city = city_row.scalar_one()
    
    district_row = await session.execute(
        select(m.districts).where(m.districts.city_id == city.id).limit(1)
    )
    district = district_row.scalar_one_or_none()
    
    skill_row = await session.execute(
        select(m.skills).where(m.skills.code == "ELEC").limit(1)
    )
    skill = skill_row.scalar_one()
    
    master = m.masters(
        tg_user_id=999888777,
        full_name="Тестовый Мастер Watchdog",
        phone="+79009998877",
        city_id=city.id,
        is_active=True,
        is_on_shift=True,
        is_blocked=False,
        verified=True,
        has_vehicle=True,
    )
    session.add(master)
    await session.flush()
    
    # Добавляем навык
    master_skill = m.master_skills(master_id=master.id, skill_id=skill.id)
    session.add(master_skill)
    
    # Добавляем район
    if district:
        master_district = m.master_districts(master_id=master.id, district_id=district.id)
        session.add(master_district)
    
    await session.flush()
    return master


async def test_watchdog_expires_old_offers(session, sample_order, sample_master):
    """Watchdog должен помечать истёкшие офферы как EXPIRED."""
    # Создаём истёкший оффер (expires_at в прошлом)
    expired_offer = m.offers(
        order_id=sample_order.id,
        master_id=sample_master.id,
        state=m.OfferState.SENT,
        sent_at=datetime.now(UTC) - timedelta(minutes=5),
        expires_at=datetime.now(UTC) - timedelta(minutes=2),  # Истёк 2 минуты назад
        round_number=1,
    )
    session.add(expired_offer)
    await session.commit()
    
    # Запускаем watchdog (1 итерация)
    await watchdog_expired_offers(interval_seconds=1, iterations=1)
    
    # Проверяем что оффер помечен как EXPIRED
    session.expire_all()
    await session.refresh(expired_offer)
    
    assert expired_offer.state == m.OfferState.EXPIRED
    assert expired_offer.responded_at is not None


async def test_watchdog_keeps_active_offers(session, sample_order, sample_master):
    """Watchdog НЕ должен трогать активные офферы."""
    # Создаём активный оффер (expires_at в будущем)
    active_offer = m.offers(
        order_id=sample_order.id,
        master_id=sample_master.id,
        state=m.OfferState.SENT,
        sent_at=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(minutes=2),  # Ещё не истёк
        round_number=1,
    )
    session.add(active_offer)
    await session.commit()
    
    # Запускаем watchdog (1 итерация)
    await watchdog_expired_offers(interval_seconds=1, iterations=1)
    
    # Проверяем что оффер остался SENT
    session.expire_all()
    await session.refresh(active_offer)
    
    assert active_offer.state == m.OfferState.SENT
    assert active_offer.responded_at is None


async def test_watchdog_multiple_expired_offers(session, sample_order, sample_master):
    """Watchdog должен обработать несколько истёкших офферов за раз."""
    # Создаём второй заказ и мастера
    city_row = await session.execute(select(m.cities).limit(1))
    city = city_row.scalar_one()
    
    order2 = m.orders(
        city_id=city.id,
        status=m.OrderStatus.SEARCHING,
        category=m.OrderCategory.PLUMBING,
        address="Test Address 2",
        client_phone="+79001234568",
        visit_date=datetime.now(UTC).date(),
        slot_start="14:00",
        slot_end="16:00",
    )
    session.add(order2)
    await session.flush()
    
    master2 = m.masters(
        tg_user_id=999888778,
        full_name="Тестовый Мастер 2",
        phone="+79009998878",
        city_id=city.id,
        is_active=True,
        is_on_shift=True,
        is_blocked=False,
        verified=True,
    )
    session.add(master2)
    await session.flush()
    
    # Создаём 3 истёкших оффера
    offers = [
        m.offers(
            order_id=sample_order.id,
            master_id=sample_master.id,
            state=m.OfferState.SENT,
            sent_at=datetime.now(UTC) - timedelta(minutes=10),
            expires_at=datetime.now(UTC) - timedelta(minutes=5),
            round_number=1,
        ),
        m.offers(
            order_id=order2.id,
            master_id=master2.id,
            state=m.OfferState.SENT,
            sent_at=datetime.now(UTC) - timedelta(minutes=8),
            expires_at=datetime.now(UTC) - timedelta(minutes=3),
            round_number=1,
        ),
        m.offers(
            order_id=sample_order.id,
            master_id=master2.id,
            state=m.OfferState.SENT,
            sent_at=datetime.now(UTC) - timedelta(minutes=6),
            expires_at=datetime.now(UTC) - timedelta(minutes=1),
            round_number=2,
        ),
    ]
    
    for offer in offers:
        session.add(offer)
    await session.commit()
    
    offer_ids = [o.id for o in offers]
    
    # Запускаем watchdog (1 итерация)
    await watchdog_expired_offers(interval_seconds=1, iterations=1)
    
    # Проверяем что все офферы помечены как EXPIRED
    result = await session.execute(
        select(m.offers).where(m.offers.id.in_(offer_ids))
    )
    updated_offers = result.scalars().all()
    
    assert len(updated_offers) == 3
    for offer in updated_offers:
        assert offer.state == m.OfferState.EXPIRED
        assert offer.responded_at is not None


async def test_watchdog_ignores_already_expired(session, sample_order, sample_master):
    """Watchdog не должен повторно обрабатывать уже EXPIRED офферы."""
    # Создаём оффер который уже EXPIRED
    already_expired = m.offers(
        order_id=sample_order.id,
        master_id=sample_master.id,
        state=m.OfferState.EXPIRED,
        sent_at=datetime.now(UTC) - timedelta(minutes=10),
        expires_at=datetime.now(UTC) - timedelta(minutes=5),
        responded_at=datetime.now(UTC) - timedelta(minutes=5),
        round_number=1,
    )
    session.add(already_expired)
    await session.commit()
    
    original_responded_at = already_expired.responded_at
    
    # Запускаем watchdog (1 итерация)
    await watchdog_expired_offers(interval_seconds=1, iterations=1)
    
    # Проверяем что responded_at не изменился
    session.expire_all()
    await session.refresh(already_expired)
    
    assert already_expired.state == m.OfferState.EXPIRED
    assert already_expired.responded_at == original_responded_at


async def test_watchdog_ignores_declined_offers(session, sample_order, sample_master):
    """Watchdog не должен трогать DECLINED офферы."""
    declined_offer = m.offers(
        order_id=sample_order.id,
        master_id=sample_master.id,
        state=m.OfferState.DECLINED,
        sent_at=datetime.now(UTC) - timedelta(minutes=10),
        expires_at=datetime.now(UTC) - timedelta(minutes=5),
        responded_at=datetime.now(UTC) - timedelta(minutes=7),
        round_number=1,
    )
    session.add(declined_offer)
    await session.commit()
    
    # Запускаем watchdog (1 итерация)
    await watchdog_expired_offers(interval_seconds=1, iterations=1)
    
    # Проверяем что оффер остался DECLINED
    session.expire_all()
    await session.refresh(declined_offer)
    
    assert declined_offer.state == m.OfferState.DECLINED
