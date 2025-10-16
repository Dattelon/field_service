"""
Тесты для watchdog_expired_offers - автоматическое истечение офферов.
"""
import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy import select

from field_service.db import models as m
from field_service.services.watchdogs import watchdog_expired_offers
from tests.factories import ensure_city, ensure_district, ensure_master, ensure_skill


UTC = timezone.utc


async def create_test_order(async_session):
    """Вспомогательная функция для создания тестового заказа."""
    city = await ensure_city(async_session, name="Test City Offers", tz="Europe/Moscow")
    district = await ensure_district(async_session, city=city, name="Test District Offers")
    
    order = m.orders(
        city_id=city.id,
        district_id=district.id,
        status=m.OrderStatus.SEARCHING,
        category=m.OrderCategory.ELECTRICS,
        address="Test Address",
        client_phone="+79001234567",
        visit_date=datetime.now(UTC).date(),
        slot_start="10:00",
        slot_end="12:00",
    )
    async_session.add(order)
    await async_session.flush()
    return order


async def create_test_master(async_session, phone="+79009998877"):
    """Вспомогательная функция для создания тестового мастера."""
    city = await ensure_city(async_session, name="Test City Offers", tz="Europe/Moscow")
    district = await ensure_district(async_session, city=city, name="Test District Offers")
    skill = await ensure_skill(async_session, code="ELEC", name="Electrician")
    
    master = m.masters(
        tg_user_id=999888777 + hash(phone) % 1000,  # уникальный ID на базе телефона
        full_name="Тестовый Мастер Watchdog",
        phone=phone,
        city_id=city.id,
        is_active=True,
        is_on_shift=True,
        is_blocked=False,
        verified=True,
        has_vehicle=True,
    )
    async_session.add(master)
    await async_session.flush()
    
    # Добавляем навык
    master_skill = m.master_skills(master_id=master.id, skill_id=skill.id)
    async_session.add(master_skill)
    
    # Добавляем район
    master_district = m.master_districts(master_id=master.id, district_id=district.id)
    async_session.add(master_district)
    
    await async_session.flush()
    return master


@pytest.mark.asyncio
async def test_watchdog_expires_old_offers(async_session):
    """Watchdog должен помечать истёкшие офферы как EXPIRED."""
    # Создаём тестовые данные
    sample_order = await create_test_order(async_session)
    sample_master = await create_test_master(async_session, phone="+79009998801")
    
    # Создаём истёкший оффер (expires_at в прошлом)
    expired_offer = m.offers(
        order_id=sample_order.id,
        master_id=sample_master.id,
        state=m.OfferState.SENT,
        sent_at=datetime.now(UTC) - timedelta(minutes=5),
        expires_at=datetime.now(UTC) - timedelta(minutes=2),  # Истёк 2 минуты назад
        round_number=1,
    )
    async_session.add(expired_offer)
    await async_session.flush()
    
    offer_id = expired_offer.id
    
    # Запускаем watchdog (1 итерация) с передачей сессии
    await watchdog_expired_offers(interval_seconds=1, iterations=1, session=async_session)
    
    # Проверяем что оффер помечен как EXPIRED
    async_session.expire_all()
    result = await async_session.execute(
        select(m.offers).where(m.offers.id == offer_id)
    )
    updated_offer = result.scalar_one()
    
    assert updated_offer.state == m.OfferState.EXPIRED
    assert updated_offer.responded_at is not None


@pytest.mark.asyncio
async def test_watchdog_keeps_active_offers(async_session):
    """Watchdog НЕ должен трогать активные офферы."""
    # Создаём тестовые данные
    sample_order = await create_test_order(async_session)
    sample_master = await create_test_master(async_session, phone="+79009998802")
    
    # Создаём активный оффер (expires_at в будущем)
    active_offer = m.offers(
        order_id=sample_order.id,
        master_id=sample_master.id,
        state=m.OfferState.SENT,
        sent_at=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(minutes=2),  # Ещё не истёк
        round_number=1,
    )
    async_session.add(active_offer)
    await async_session.flush()
    
    offer_id = active_offer.id
    
    # Запускаем watchdog (1 итерация) с передачей сессии
    await watchdog_expired_offers(interval_seconds=1, iterations=1, session=async_session)
    
    # Проверяем что оффер остался SENT
    async_session.expire_all()
    result = await async_session.execute(
        select(m.offers).where(m.offers.id == offer_id)
    )
    updated_offer = result.scalar_one()
    
    assert updated_offer.state == m.OfferState.SENT
    assert updated_offer.responded_at is None


@pytest.mark.asyncio
async def test_watchdog_multiple_expired_offers(async_session):
    """Watchdog должен обработать несколько истёкших офферов за раз."""
    # Создаём тестовые данные
    sample_order = await create_test_order(async_session)
    sample_master = await create_test_master(async_session, phone="+79009998803")
    
    # Создаём второй заказ и мастера
    city = await ensure_city(async_session, name="Test City Offers 2", tz="Europe/Moscow")
    
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
    async_session.add(order2)
    await async_session.flush()
    
    master2 = await create_test_master(async_session, phone="+79009998804")
    
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
        async_session.add(offer)
    await async_session.flush()
    
    offer_ids = [o.id for o in offers]
    
    # Запускаем watchdog (1 итерация) с передачей сессии
    await watchdog_expired_offers(interval_seconds=1, iterations=1, session=async_session)
    
    # Проверяем что все офферы помечены как EXPIRED
    async_session.expire_all()
    result = await async_session.execute(
        select(m.offers).where(m.offers.id.in_(offer_ids))
    )
    updated_offers = result.scalars().all()
    
    assert len(updated_offers) == 3
    for offer in updated_offers:
        assert offer.state == m.OfferState.EXPIRED
        assert offer.responded_at is not None


@pytest.mark.asyncio
async def test_watchdog_ignores_already_expired(async_session):
    """Watchdog не должен повторно обрабатывать уже EXPIRED офферы."""
    # Создаём тестовые данные
    sample_order = await create_test_order(async_session)
    sample_master = await create_test_master(async_session, phone="+79009998805")
    
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
    async_session.add(already_expired)
    await async_session.flush()
    
    offer_id = already_expired.id
    original_responded_at = already_expired.responded_at
    
    # Запускаем watchdog (1 итерация) с передачей сессии
    await watchdog_expired_offers(interval_seconds=1, iterations=1, session=async_session)
    
    # Проверяем что responded_at не изменился
    async_session.expire_all()
    result = await async_session.execute(
        select(m.offers).where(m.offers.id == offer_id)
    )
    updated_offer = result.scalar_one()
    
    assert updated_offer.state == m.OfferState.EXPIRED
    assert updated_offer.responded_at == original_responded_at


@pytest.mark.asyncio
async def test_watchdog_ignores_declined_offers(async_session):
    """Watchdog не должен трогать DECLINED офферы."""
    # Создаём тестовые данные
    sample_order = await create_test_order(async_session)
    sample_master = await create_test_master(async_session, phone="+79009998806")
    
    declined_offer = m.offers(
        order_id=sample_order.id,
        master_id=sample_master.id,
        state=m.OfferState.DECLINED,
        sent_at=datetime.now(UTC) - timedelta(minutes=10),
        expires_at=datetime.now(UTC) - timedelta(minutes=5),
        responded_at=datetime.now(UTC) - timedelta(minutes=7),
        round_number=1,
    )
    async_session.add(declined_offer)
    await async_session.flush()
    
    offer_id = declined_offer.id
    
    # Запускаем watchdog (1 итерация) с передачей сессии
    await watchdog_expired_offers(interval_seconds=1, iterations=1, session=async_session)
    
    # Проверяем что оффер остался DECLINED
    async_session.expire_all()
    result = await async_session.execute(
        select(m.offers).where(m.offers.id == offer_id)
    )
    updated_offer = result.scalar_one()
    
    assert updated_offer.state == m.OfferState.DECLINED
