"""
P1-10: Тест push-уведомлений о новых офферах

Проверяет что при создании оффера мастер получает уведомление.
"""
import pytest
from datetime import datetime, timezone, timedelta
from sqlalchemy import text, select

from field_service.db import models as m
from field_service.services.distribution_scheduler import tick_once, _load_config
from field_service.services.push_notifications import NotificationEvent


@pytest.mark.asyncio
async def test_offer_push_notification(async_session):
    """Проверить что при создании оффера мастер получает push-уведомление."""
    
    # 1. Создать город
    city = m.cities(name="Москва", timezone="Europe/Moscow")
    async_session.add(city)
    await async_session.flush()
    
    # 2. Создать район
    district = m.districts(city_id=city.id, name="Центральный")
    async_session.add(district)
    await async_session.flush()
    
    # 3. Создать навык
    skill = m.skills(name="Электрика", code="ELEC", is_active=True)
    async_session.add(skill)
    await async_session.flush()
    
    # 4. Создать мастера
    master = m.masters(
        telegram_user_id=12345,
        full_name="Иван Иванов",
        phone="+79001234567",
        city_id=city.id,
        is_active=True,
        verified=True,
        is_on_shift=True,
        max_active_orders_override=5,
    )
    async_session.add(master)
    await async_session.flush()
    
    # 5. Связать мастера с районом
    master_district = m.master_districts(master_id=master.id, district_id=district.id)
    async_session.add(master_district)
    await async_session.flush()
    
    # 6. Связать мастера с навыком
    master_skill = m.master_skills(master_id=master.id, skill_id=skill.id)
    async_session.add(master_skill)
    await async_session.flush()
    
    # 7. Создать заказ
    now = datetime.now(timezone.utc)
    order = m.orders(
        city_id=city.id,
        district_id=district.id,
        status=m.OrderStatus.SEARCHING,
        category=m.OrderCategory.ELECTRICS,
        type=m.OrderType.NORMAL,
        created_at=now,
        timeslot_start_utc=now + timedelta(hours=2),
        timeslot_end_utc=now + timedelta(hours=4),
        client_name="Клиент",
        client_phone="+79009999999",
        address_street="Улица",
        address_house="1",
    )
    async_session.add(order)
    await async_session.flush()
    await async_session.commit()
    
    # 8. Запустить тик распределения
    cfg = await _load_config()
    await tick_once(cfg, bot=None, alerts_chat_id=None, session=async_session)
    
    # 9. Проверить что оффер создан
    async_session.expire_all()
    result = await async_session.execute(
        select(m.offers)
        .where(m.offers.order_id == order.id)
        .where(m.offers.master_id == master.id)
    )
    offer = result.scalar_one_or_none()
    assert offer is not None, "Оффер должен быть создан"
    assert offer.state == m.OfferState.SENT, "Оффер должен быть в статусе SENT"
    
    # 10. Проверить что уведомление добавлено в outbox
    result = await async_session.execute(
        select(m.notifications_outbox)
        .where(m.notifications_outbox.master_id == master.id)
        .where(m.notifications_outbox.event == NotificationEvent.NEW_OFFER.value)
    )
    notification = result.scalar_one_or_none()
    assert notification is not None, "Уведомление должно быть в outbox"
    
    # 11. Проверить содержимое уведомления
    payload = notification.payload
    assert payload is not None
    assert "message" in payload
    assert str(order.id) in payload["message"], "В сообщении должен быть ID заказа"
    assert "Москва" in payload["message"], "В сообщении должен быть город"
    assert "Центральный" in payload["message"], "В сообщении должен быть район"
    assert "Электрика" in payload["message"], "В сообщении должна быть категория"
    
    print(f"✅ Уведомление создано: {payload['message']}")


@pytest.mark.asyncio
async def test_notification_format(async_session):
    """Проверить формат уведомления."""
    from field_service.services.distribution_scheduler import _get_order_notification_data
    
    # 1. Создать тестовые данные
    city = m.cities(name="Санкт-Петербург", timezone="Europe/Moscow")
    async_session.add(city)
    await async_session.flush()
    
    district = m.districts(city_id=city.id, name="Невский")
    async_session.add(district)
    await async_session.flush()
    
    now = datetime.now(timezone.utc)
    order = m.orders(
        city_id=city.id,
        district_id=district.id,
        status=m.OrderStatus.SEARCHING,
        category=m.OrderCategory.PLUMBING,
        type=m.OrderType.NORMAL,
        created_at=now,
        timeslot_start_utc=now + timedelta(hours=1),
        timeslot_end_utc=now + timedelta(hours=3),
        client_name="Тест",
        client_phone="+79001111111",
        address_street="Улица",
        address_house="1",
    )
    async_session.add(order)
    await async_session.flush()
    await async_session.commit()
    
    # 2. Получить данные для уведомления
    data = await _get_order_notification_data(async_session, order.id)
    
    # 3. Проверить формат данных
    assert data["order_id"] == order.id
    assert data["city"] == "Санкт-Петербург"
    assert data["district"] == "Невский"
    assert data["category"] == "🚰 Сантехника"
    assert ":" in data["timeslot"], "Timeslot должен содержать время"
    
    print(f"✅ Данные уведомления: {data}")


@pytest.mark.asyncio
async def test_notification_without_district(async_session):
    """Проверить уведомление для заказа без района."""
    from field_service.services.distribution_scheduler import _get_order_notification_data
    
    # 1. Создать город
    city = m.cities(name="Казань", timezone="Europe/Moscow")
    async_session.add(city)
    await async_session.flush()
    
    now = datetime.now(timezone.utc)
    order = m.orders(
        city_id=city.id,
        district_id=None,  # Без района
        status=m.OrderStatus.SEARCHING,
        category=m.OrderCategory.HANDYMAN,
        type=m.OrderType.NORMAL,
        created_at=now,
        client_name="Тест",
        client_phone="+79001111111",
        address_street="Улица",
        address_house="1",
    )
    async_session.add(order)
    await async_session.flush()
    await async_session.commit()
    
    data = await _get_order_notification_data(async_session, order.id)
    
    assert data["district"] == "не указан", "Для заказа без района должно быть 'не указан'"
    print(f"✅ Уведомление без района: {data}")
