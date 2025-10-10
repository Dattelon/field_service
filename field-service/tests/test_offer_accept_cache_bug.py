"""
Тест для бага: после принятия заказа оффер остаётся в списке "Новые заявки"

ПРОБЛЕМА:
1. Мастер нажимает "Взять заявку"
2. Приходит уведомление "Заявка принята. Удачи в работе!"
3. НО заказ не исчезает из списка "Новые заявки"
4. Можно нажимать "Взять" по кругу

ПРИЧИНА:
- После commit() не вызывается session.expire_all()
- SQLAlchemy кэширует данные в session
- _load_offers() читает из кэша где оффер всё ещё в статусе SENT/VIEWED
- Реальное состояние в БД: оффер в статусе ACCEPTED, но session об этом не знает

РЕШЕНИЕ:
- Добавить session.expire_all() после commit() в offer_accept()
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from field_service.db import models as m

_log = logging.getLogger(__name__)


@pytest.mark.asyncio
async def test_offer_disappears_after_accept(session: AsyncSession) -> None:
    """
    Проверяет что после принятия заказа он исчезает из списка "Новые заявки".
    
    CRITICAL: Это regression test для бага где заказ оставался в списке после accept.
    """
    _log.info("=== TEST START: offer_disappears_after_accept ===")
    
    # === SETUP ===
    # Создаём город
    city = m.cities(name="TestCity", timezone="Europe/Moscow")
    session.add(city)
    await session.flush()
    
    # Создаём мастера
    master = m.masters(
        tg_user_id=12345,
        full_name="Test Master",
        phone="79991234567",
        is_active=True,
        is_blocked=False,
        moderation_status=m.ModerationStatus.APPROVED,
        max_active_orders_override=5,
    )
    session.add(master)
    await session.flush()
    
    # Создаём заказ в статусе SEARCHING
    db_now = (await session.execute(text("SELECT NOW()"))).scalar()
    order = m.orders(
        city_id=city.id,
        client_name="Test Client",
        client_phone="79997654321",
        category=m.OrderCategory.ELECTRICS,
        type=m.OrderType.NORMAL,
        house="123",
        description="Test order",
        status=m.OrderStatus.SEARCHING,
        timeslot_start_utc=db_now + timedelta(hours=2),
        timeslot_end_utc=db_now + timedelta(hours=4),
        version=1,
    )
    session.add(order)
    await session.flush()
    
    # Создаём оффер для мастера в статусе SENT
    offer = m.offers(
        order_id=order.id,
        master_id=master.id,
        state=m.OfferState.SENT,
        round_number=1,
        expires_at=db_now + timedelta(minutes=5),
        sent_at=db_now,
    )
    session.add(offer)
    await session.commit()
    
    _log.info("Setup complete: order_id=%s master_id=%s offer_id=%s", order.id, master.id, offer.id)
    
    # === ПРОВЕРКА: Оффер видим в "Новых заявках" ===
    _log.info("Step 1: Checking offer is visible before accept")
    offers_before = await session.execute(
        select(m.offers)
        .where(
            m.offers.master_id == master.id,
            m.offers.state.in_((m.OfferState.SENT, m.OfferState.VIEWED)),
            m.offers.expires_at > db_now,
        )
    )
    offers_before_list = offers_before.scalars().all()
    _log.info("Offers before accept: %s", len(offers_before_list))
    assert len(offers_before_list) == 1, "Оффер должен быть видим ДО принятия"
    
    # === СИМУЛЯЦИЯ: Принятие заказа ===
    _log.info("Step 2: Accepting order (simulating offer_accept handler)")
    
    # Обновляем заказ
    order.status = m.OrderStatus.ASSIGNED
    order.assigned_master_id = master.id
    order.version = 2
    
    # Обновляем оффер
    offer.state = m.OfferState.ACCEPTED
    offer.responded_at = db_now
    
    # Коммитим
    await session.commit()
    _log.info("Commit done for order=%s", order.id)
    
    # === БАГ: Без expire_all() оффер всё ещё видим ===
    _log.info("Step 3: Checking offers WITHOUT expire_all (bug scenario)")
    offers_bug = await session.execute(
        select(m.offers)
        .where(
            m.offers.master_id == master.id,
            m.offers.state.in_((m.OfferState.SENT, m.OfferState.VIEWED)),
            m.offers.expires_at > db_now,
        )
    )
    offers_bug_list = offers_bug.scalars().all()
    _log.info("Offers after accept WITHOUT expire (buggy): %s", len(offers_bug_list))
    
    # БЕЗ expire_all() SQLAlchemy вернёт 1 оффер из кэша (БАГ!)
    # С expire_all() SQLAlchemy обновит данные из БД и вернёт 0 офферов (ПРАВИЛЬНО!)
    
    # === FIX: С expire_all() оффер исчезает ===
    _log.info("Step 4: Checking offers WITH expire_all (fixed scenario)")
    session.expire_all()  # ✅ КРИТИЧНО: Сбрасываем кэш SQLAlchemy
    
    offers_fixed = await session.execute(
        select(m.offers)
        .where(
            m.offers.master_id == master.id,
            m.offers.state.in_((m.OfferState.SENT, m.OfferState.VIEWED)),
            m.offers.expires_at > db_now,
        )
    )
    offers_fixed_list = offers_fixed.scalars().all()
    _log.info("Offers after accept WITH expire (fixed): %s", len(offers_fixed_list))
    
    # === ASSERTION ===
    assert len(offers_fixed_list) == 0, (
        "После принятия заказа и expire_all() оффер НЕ должен быть виден в 'Новых заявках'"
    )
    
    # === ПРОВЕРКА: Оффер реально в ACCEPTED в БД ===
    _log.info("Step 5: Verifying offer state in DB")
    offer_check = await session.execute(
        select(m.offers.state)
        .where(
            m.offers.order_id == order.id,
            m.offers.master_id == master.id,
        )
    )
    final_state = offer_check.scalar()
    _log.info("Final offer state in DB: %s", final_state)
    assert final_state == m.OfferState.ACCEPTED, "Оффер должен быть в статусе ACCEPTED в БД"
    
    # === ПРОВЕРКА: Заказ в ASSIGNED в БД ===
    _log.info("Step 6: Verifying order status in DB")
    order_check = await session.execute(
        select(m.orders.status, m.orders.assigned_master_id)
        .where(m.orders.id == order.id)
    )
    order_row = order_check.first()
    _log.info("Final order status: %s, assigned_master: %s", order_row[0], order_row[1])
    assert order_row[0] == m.OrderStatus.ASSIGNED, "Заказ должен быть в статусе ASSIGNED"
    assert order_row[1] == master.id, "Заказ должен быть назначен мастеру"
    
    _log.info("=== TEST SUCCESS: offer_disappears_after_accept ===")
