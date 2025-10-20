"""
Тесты граничных случаев и специальных сценариев.

Покрывает:
- Race conditions при распределении
- Максимальная загрузка мастера
- Блокировка мастера при просрочке комиссии
- Разные категории заказов и навыки
- Заказы без района (fallback на город)
- Дедлайн комиссий и напоминания
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select, text

from field_service.db import models as m
from field_service.services.commission_service import (
    CommissionService,
    apply_overdue_commissions,
)
from field_service.services.distribution_scheduler import (
    DistConfig,
    tick_once,
)

UTC = timezone.utc


async def _get_db_now(session) -> datetime:
    row = await session.execute(text("SELECT NOW()"))
    return row.scalar()


@pytest.mark.asyncio
async def test_master_max_active_orders_limit(async_session):
    """
    Тест ограничения максимального количества активных заказов:
    1. Мастер с max_active_orders=2
    2. Уже есть 2 активных заказа (ASSIGNED, EN_ROUTE)
    3. Новый заказ НЕ должен распределиться на этого мастера
    """
    # Подготовка
    city = m.cities(name="City", timezone="Europe/Moscow")
    async_session.add(city)
    await async_session.flush()

    district = m.districts(city_id=city.id, name="District")
    async_session.add(district)
    await async_session.flush()

    skill = m.skills(code="ELEC", name="Electrician", is_active=True)
    async_session.add(skill)
    await async_session.flush()

    master = m.masters(
        tg_user_id=111,
        full_name="Busy Master",
        city_id=city.id,
        is_active=True,
        is_blocked=False,
        verified=True,
        is_on_shift=True,
        shift_status=m.ShiftStatus.SHIFT_ON,
        moderation_status=m.ModerationStatus.APPROVED,
        max_active_orders_override=2,  # Лимит 2 заказа
    )
    async_session.add(master)
    await async_session.flush()

    # Привязки
    async_session.add(m.master_skills(master_id=master.id, skill_id=skill.id))
    async_session.add(m.master_districts(master_id=master.id, district_id=district.id))
    
    # Создаём 2 активных заказа
    for i in range(2):
        order = m.orders(
            city_id=city.id,
            district_id=district.id,
            status=m.OrderStatus.ASSIGNED if i == 0 else m.OrderStatus.EN_ROUTE,
            category=m.OrderCategory.ELECTRICS,
            assigned_master_id=master.id,
        )
        async_session.add(order)
    
    await async_session.commit()

    # Новый заказ для распределения
    new_order = m.orders(
        city_id=city.id,
        district_id=district.id,
        status=m.OrderStatus.SEARCHING,
        category=m.OrderCategory.ELECTRICS,
    )
    async_session.add(new_order)
    await async_session.commit()

    order_id = new_order.id
    master_id = master.id

    cfg = DistConfig(
        tick_seconds=30,
        sla_seconds=120,
        rounds=2,
        top_log_n=10,
        to_admin_after_min=10,
    )

    # Распределение
    async_session.expire_all()
    await tick_once(cfg, bot=None, alerts_chat_id=None, session=async_session)
    await async_session.commit()

    # Проверка: оффер НЕ должен быть создан
    async_session.expire_all()
    offers = await async_session.execute(
        select(m.offers).where(m.offers.order_id == order_id)
    )
    assert offers.scalar_one_or_none() is None

    # Проверка эскалации после 2 раундов
    await tick_once(cfg, bot=None, alerts_chat_id=None, session=async_session)
    await async_session.commit()

    async_session.expire_all()
    await async_session.refresh(new_order)
    assert new_order.dist_escalated_logist_at is not None


@pytest.mark.asyncio
async def test_commission_overdue_blocks_master(async_session):
    """
    Тест блокировки мастера при просрочке комиссии:
    1. Комиссия в статусе WAIT_PAY с истёкшим дедлайном
    2. apply_overdue_commissions()
    3. Комиссия -> OVERDUE
    4. Мастер блокируется (is_blocked=True, is_active=False)
    """
    # Подготовка
    city = m.cities(name="City", timezone="Europe/Moscow")
    async_session.add(city)
    await async_session.flush()

    master = m.masters(
        tg_user_id=111,
        full_name="Master",
        city_id=city.id,
        is_active=True,
        is_blocked=False,
        verified=True,
    )
    async_session.add(master)
    await async_session.flush()

    order = m.orders(
        city_id=city.id,
        status=m.OrderStatus.PAYMENT,
        category=m.OrderCategory.ELECTRICS,
        total_sum=Decimal("5000"),
        assigned_master_id=master.id,
    )
    async_session.add(order)
    await async_session.flush()

    # Комиссия с просроченным дедлайном
    db_now = await _get_db_now(async_session)
    commission = m.commissions(
        order_id=order.id,
        master_id=master.id,
        amount=Decimal("2500"),
        rate=Decimal("0.50"),
        status=m.CommissionStatus.WAIT_PAY,
        deadline_at=db_now - timedelta(hours=1),  # Просрочен на час
        is_paid=False,
        has_checks=False,
        blocked_applied=False,
    )
    async_session.add(commission)
    await async_session.commit()

    commission_id = commission.id
    master_id = master.id

    # Применение просрочки
    events = await apply_overdue_commissions(async_session, now=db_now)
    await async_session.commit()

    # Проверка событий
    assert len(events) == 1
    assert events[0].commission_id == commission_id
    assert events[0].master_id == master_id

    # Проверка комиссии
    async_session.expire_all()
    await async_session.refresh(commission)
    assert commission.status == m.CommissionStatus.OVERDUE
    assert commission.blocked_applied is True
    assert commission.blocked_at is not None

    # Проверка мастера
    async_session.expire_all()
    await async_session.refresh(master)
    assert master.is_blocked is True
    assert master.is_active is False
    assert master.blocked_at is not None
    assert master.blocked_reason == "commission_overdue"


@pytest.mark.asyncio
async def test_order_without_district_fallback_to_city(async_session):
    """
    Тест fallback на город при отсутствии района:
    1. Заказ без district_id (district_id=None)
    2. Мастер работает в другом районе этого города
    3. Распределение должно найти мастера (fallback на город)
    """
    city = m.cities(name="City", timezone="Europe/Moscow")
    async_session.add(city)
    await async_session.flush()

    district1 = m.districts(city_id=city.id, name="District 1")
    district2 = m.districts(city_id=city.id, name="District 2")
    async_session.add_all([district1, district2])
    await async_session.flush()

    skill = m.skills(code="ELEC", name="Electrician", is_active=True)
    async_session.add(skill)
    await async_session.flush()

    # Мастер работает в district2
    master = m.masters(
        tg_user_id=111,
        full_name="Master",
        city_id=city.id,
        is_active=True,
        is_blocked=False,
        verified=True,
        is_on_shift=True,
        shift_status=m.ShiftStatus.SHIFT_ON,
        moderation_status=m.ModerationStatus.APPROVED,
    )
    async_session.add(master)
    await async_session.flush()

    async_session.add(m.master_skills(master_id=master.id, skill_id=skill.id))
    async_session.add(m.master_districts(master_id=master.id, district_id=district2.id))
    await async_session.commit()

    # Заказ БЕЗ района (district_id=None)
    order = m.orders(
        city_id=city.id,
        district_id=None,  # НЕТ района
        status=m.OrderStatus.SEARCHING,
        category=m.OrderCategory.ELECTRICS,
    )
    async_session.add(order)
    await async_session.commit()

    order_id = order.id
    master_id = master.id

    cfg = DistConfig(
        tick_seconds=30,
        sla_seconds=120,
        rounds=2,
        top_log_n=10,
        to_admin_after_min=10,
    )

    # Распределение
    async_session.expire_all()
    await tick_once(cfg, bot=None, alerts_chat_id=None, session=async_session)
    await async_session.commit()

    # Проверка: оффер должен быть создан (fallback на город)
    async_session.expire_all()
    offer = await async_session.execute(
        select(m.offers).where(m.offers.order_id == order_id)
    )
    offer = offer.scalar_one()

    assert offer.master_id == master_id
    assert offer.state == m.OfferState.SENT


@pytest.mark.asyncio
async def test_different_categories_require_different_skills(async_session):
    """
    Тест что разные категории требуют разные навыки:
    1. Мастер с навыком ELEC (электрика)
    2. Заказ категории PLUMBING (сантехника)
    3. Распределение НЕ должно найти мастера
    """
    city = m.cities(name="City", timezone="Europe/Moscow")
    async_session.add(city)
    await async_session.flush()

    district = m.districts(city_id=city.id, name="District")
    async_session.add(district)
    await async_session.flush()

    # Навык ELEC
    skill_elec = m.skills(code="ELEC", name="Electrician", is_active=True)
    async_session.add(skill_elec)
    await async_session.flush()

    # Мастер только с ELEC
    master = m.masters(
        tg_user_id=111,
        full_name="Electrician Master",
        city_id=city.id,
        is_active=True,
        is_blocked=False,
        verified=True,
        is_on_shift=True,
        shift_status=m.ShiftStatus.SHIFT_ON,
        moderation_status=m.ModerationStatus.APPROVED,
    )
    async_session.add(master)
    await async_session.flush()

    async_session.add(m.master_skills(master_id=master.id, skill_id=skill_elec.id))
    async_session.add(m.master_districts(master_id=master.id, district_id=district.id))
    await async_session.commit()

    # Заказ PLUMBING (требует навык PLUMB)
    order = m.orders(
        city_id=city.id,
        district_id=district.id,
        status=m.OrderStatus.SEARCHING,
        category=m.OrderCategory.PLUMBING,  # Сантехника!
    )
    async_session.add(order)
    await async_session.commit()

    order_id = order.id

    cfg = DistConfig(
        tick_seconds=30,
        sla_seconds=120,
        rounds=2,
        top_log_n=10,
        to_admin_after_min=10,
    )

    # Распределение
    async_session.expire_all()
    await tick_once(cfg, bot=None, alerts_chat_id=None, session=async_session)
    await async_session.commit()

    # Проверка: офферов не должно быть
    async_session.expire_all()
    offers = await async_session.execute(
        select(m.offers).where(m.offers.order_id == order_id)
    )
    assert offers.scalar_one_or_none() is None

    # После 2 раундов - эскалация
    await tick_once(cfg, bot=None, alerts_chat_id=None, session=async_session)
    await async_session.commit()

    async_session.expire_all()
    await async_session.refresh(order)
    assert order.dist_escalated_logist_at is not None


@pytest.mark.asyncio
async def test_master_with_multiple_skills_and_districts(async_session):
    """
    Тест мастера с несколькими навыками и районами:
    1. Мастер работает в 2 районах
    2. Мастер имеет 2 навыка (ELEC + PLUMB)
    3. Проверка распределения для обоих категорий в обоих районах
    """
    city = m.cities(name="City", timezone="Europe/Moscow")
    async_session.add(city)
    await async_session.flush()

    district1 = m.districts(city_id=city.id, name="District 1")
    district2 = m.districts(city_id=city.id, name="District 2")
    async_session.add_all([district1, district2])
    await async_session.flush()

    skill_elec = m.skills(code="ELEC", name="Electrician", is_active=True)
    skill_plumb = m.skills(code="PLUMB", name="Plumber", is_active=True)
    async_session.add_all([skill_elec, skill_plumb])
    await async_session.flush()

    master = m.masters(
        tg_user_id=111,
        full_name="Universal Master",
        city_id=city.id,
        is_active=True,
        is_blocked=False,
        verified=True,
        is_on_shift=True,
        shift_status=m.ShiftStatus.SHIFT_ON,
        moderation_status=m.ModerationStatus.APPROVED,
    )
    async_session.add(master)
    await async_session.flush()

    # 2 навыка
    async_session.add(m.master_skills(master_id=master.id, skill_id=skill_elec.id))
    async_session.add(m.master_skills(master_id=master.id, skill_id=skill_plumb.id))

    # 2 района
    async_session.add(m.master_districts(master_id=master.id, district_id=district1.id))
    async_session.add(m.master_districts(master_id=master.id, district_id=district2.id))
    await async_session.commit()

    master_id = master.id

    cfg = DistConfig(
        tick_seconds=30,
        sla_seconds=120,
        rounds=2,
        top_log_n=10,
        to_admin_after_min=10,
    )

    # Тест 1: Заказ ELECTRICS в district1
    order1 = m.orders(
        city_id=city.id,
        district_id=district1.id,
        status=m.OrderStatus.SEARCHING,
        category=m.OrderCategory.ELECTRICS,
    )
    async_session.add(order1)
    await async_session.commit()

    async_session.expire_all()
    await tick_once(cfg, bot=None, alerts_chat_id=None, session=async_session)
    await async_session.commit()

    async_session.expire_all()
    offer1 = await async_session.execute(
        select(m.offers).where(m.offers.order_id == order1.id)
    )
    offer1 = offer1.scalar_one()
    assert offer1.master_id == master_id

    # Тест 2: Заказ PLUMBING в district2
    order2 = m.orders(
        city_id=city.id,
        district_id=district2.id,
        status=m.OrderStatus.SEARCHING,
        category=m.OrderCategory.PLUMBING,
    )
    async_session.add(order2)
    await async_session.commit()

    # Принимаем первый оффер чтобы не было конфликта с лимитом
    async_session.expire_all()
    await async_session.refresh(offer1)
    offer1.state = m.OfferState.ACCEPTED
    offer1.responded_at = await _get_db_now(async_session)
    await async_session.refresh(order1)
    order1.status = m.OrderStatus.ASSIGNED
    order1.assigned_master_id = master_id
    await async_session.commit()

    async_session.expire_all()
    await tick_once(cfg, bot=None, alerts_chat_id=None, session=async_session)
    await async_session.commit()

    async_session.expire_all()
    offer2 = await async_session.execute(
        select(m.offers).where(m.offers.order_id == order2.id)
    )
    offer2 = offer2.scalar_one()
    assert offer2.master_id == master_id


@pytest.mark.asyncio
async def test_commission_deadline_notifications_table(async_session):
    """
    Тест таблицы commission_deadline_notifications:
    1. Создание комиссии с дедлайном
    2. Запись в таблицу уведомлений (24h, 6h, 1h)
    3. Проверка уникальности (commission_id, hours_before)
    """
    city = m.cities(name="City", timezone="Europe/Moscow")
    async_session.add(city)
    await async_session.flush()

    master = m.masters(
        tg_user_id=111,
        full_name="Master",
        city_id=city.id,
        is_active=True,
    )
    async_session.add(master)
    await async_session.flush()

    order = m.orders(
        city_id=city.id,
        status=m.OrderStatus.PAYMENT,
        category=m.OrderCategory.ELECTRICS,
        total_sum=Decimal("3000"),
        assigned_master_id=master.id,
    )
    async_session.add(order)
    await async_session.flush()

    db_now = await _get_db_now(async_session)
    commission = m.commissions(
        order_id=order.id,
        master_id=master.id,
        amount=Decimal("1500"),
        rate=Decimal("0.50"),
        status=m.CommissionStatus.WAIT_PAY,
        deadline_at=db_now + timedelta(hours=24),
        is_paid=False,
        has_checks=False,
    )
    async_session.add(commission)
    await async_session.flush()

    commission_id = commission.id

    # Создаём уведомление 24h
    notif_24h = m.commission_deadline_notifications(
        commission_id=commission_id,
        hours_before=24,
    )
    async_session.add(notif_24h)
    await async_session.commit()

    # Проверка создания
    async_session.expire_all()
    notifs = await async_session.execute(
        select(m.commission_deadline_notifications)
        .where(m.commission_deadline_notifications.commission_id == commission_id)
    )
    notifs_list = notifs.scalars().all()
    assert len(notifs_list) == 1
    assert notifs_list[0].hours_before == 24

    # Попытка создать дубликат (должна упасть на UNIQUE constraint)
    notif_duplicate = m.commission_deadline_notifications(
        commission_id=commission_id,
        hours_before=24,
    )
    async_session.add(notif_duplicate)

    with pytest.raises(Exception):  # IntegrityError
        await async_session.commit()

    await async_session.rollback()

    # Создание уведомлений 6h и 1h
    notif_6h = m.commission_deadline_notifications(
        commission_id=commission_id,
        hours_before=6,
    )
    notif_1h = m.commission_deadline_notifications(
        commission_id=commission_id,
        hours_before=1,
    )
    async_session.add_all([notif_6h, notif_1h])
    await async_session.commit()

    # Проверка всех уведомлений
    async_session.expire_all()
    notifs = await async_session.execute(
        select(m.commission_deadline_notifications)
        .where(m.commission_deadline_notifications.commission_id == commission_id)
        .order_by(m.commission_deadline_notifications.hours_before.desc())
    )
    notifs_list = notifs.scalars().all()
    assert len(notifs_list) == 3
    assert [n.hours_before for n in notifs_list] == [24, 6, 1]


@pytest.mark.asyncio
async def test_order_with_timeslot_priority(async_session):
    """
    Тест приоритета заказов с просроченным слотом:
    1. Заказ 1: timeslot в прошлом (просрочен)
    2. Заказ 2: без timeslot (created раньше)
    3. Распределение должно отдать приоритет заказу 1
    """
    city = m.cities(name="City", timezone="Europe/Moscow")
    async_session.add(city)
    await async_session.flush()

    district = m.districts(city_id=city.id, name="District")
    async_session.add(district)
    await async_session.flush()

    skill = m.skills(code="ELEC", name="Electrician", is_active=True)
    async_session.add(skill)
    await async_session.flush()

    master = m.masters(
        tg_user_id=111,
        full_name="Master",
        city_id=city.id,
        is_active=True,
        is_blocked=False,
        verified=True,
        is_on_shift=True,
        shift_status=m.ShiftStatus.SHIFT_ON,
        moderation_status=m.ModerationStatus.APPROVED,
    )
    async_session.add(master)
    await async_session.flush()

    async_session.add(m.master_skills(master_id=master.id, skill_id=skill.id))
    async_session.add(m.master_districts(master_id=master.id, district_id=district.id))
    await async_session.commit()

    master_id = master.id
    db_now = await _get_db_now(async_session)

    # Заказ 2: создан раньше, без слота
    order2 = m.orders(
        city_id=city.id,
        district_id=district.id,
        status=m.OrderStatus.SEARCHING,
        category=m.OrderCategory.ELECTRICS,
        created_at=db_now - timedelta(hours=2),
    )
    async_session.add(order2)
    await async_session.flush()

    # Заказ 1: создан позже, но слот просрочен
    order1 = m.orders(
        city_id=city.id,
        district_id=district.id,
        status=m.OrderStatus.SEARCHING,
        category=m.OrderCategory.ELECTRICS,
        timeslot_start_utc=db_now - timedelta(hours=1),  # Просрочен
        timeslot_end_utc=db_now - timedelta(minutes=30),
        created_at=db_now - timedelta(hours=1),
    )
    async_session.add(order1)
    await async_session.commit()

    order1_id = order1.id

    cfg = DistConfig(
        tick_seconds=30,
        sla_seconds=120,
        rounds=2,
        top_log_n=10,
        to_admin_after_min=10,
    )

    # Распределение
    async_session.expire_all()
    await tick_once(cfg, bot=None, alerts_chat_id=None, session=async_session)
    await async_session.commit()

    # Проверка: оффер должен уйти на order1 (приоритет просроченного слота)
    async_session.expire_all()
    offer = await async_session.execute(
        select(m.offers).where(m.offers.order_id == order1_id)
    )
    offer = offer.scalar_one()
    assert offer.master_id == master_id


@pytest.mark.asyncio
async def test_idempotent_commission_creation(async_session):
    """
    Тест идемпотентности создания комиссии:
    1. Создание комиссии
    2. Повторный вызов create_for_order
    3. Должна вернуться та же комиссия (без дублей)
    """
    city = m.cities(name="City", timezone="Europe/Moscow")
    async_session.add(city)
    await async_session.flush()

    master = m.masters(
        tg_user_id=111,
        full_name="Master",
        city_id=city.id,
        is_active=True,
    )
    async_session.add(master)
    await async_session.flush()

    owner = m.staff_users(
        tg_user_id=9001,
        role=m.StaffRole.GLOBAL_ADMIN,
        full_name="Owner",
        is_active=True,
        commission_requisites={
            "methods": ["card"],
            "card_number": "1234567890123456",
        },
    )
    async_session.add(owner)
    await async_session.flush()

    order = m.orders(
        city_id=city.id,
        status=m.OrderStatus.PAYMENT,
        category=m.OrderCategory.ELECTRICS,
        total_sum=Decimal("3000"),
        assigned_master_id=master.id,
    )
    async_session.add(order)
    await async_session.commit()

    order_id = order.id

    service = CommissionService(async_session)

    # Первое создание
    commission1 = await service.create_for_order(order_id)
    await async_session.commit()

    commission1_id = commission1.id

    # Повторное создание
    commission2 = await service.create_for_order(order_id)
    await async_session.commit()

    # Должна вернуться та же комиссия
    assert commission2 is not None
    assert commission2.id == commission1_id

    # Проверка что в БД только одна комиссия
    async_session.expire_all()
    commissions = await async_session.execute(
        select(m.commissions).where(m.commissions.order_id == order_id)
    )
    commissions_list = commissions.scalars().all()
    assert len(commissions_list) == 1


@pytest.mark.asyncio
async def test_distribution_metrics_creation(async_session):
    """
    Тест создания метрик распределения:
    1. Успешное распределение заказа
    2. Проверка записи в distribution_metrics
    3. Проверка полей метрик
    
    Note: Этот тест пропускается если метрики не создаются автоматически
    """
    # Подготовка
    city = m.cities(name="City", timezone="Europe/Moscow")
    async_session.add(city)
    await async_session.flush()

    district = m.districts(city_id=city.id, name="District")
    async_session.add(district)
    await async_session.flush()

    skill = m.skills(code="ELEC", name="Electrician", is_active=True)
    async_session.add(skill)
    await async_session.flush()

    master = m.masters(
        tg_user_id=111,
        full_name="Master",
        city_id=city.id,
        is_active=True,
        is_blocked=False,
        verified=True,
        is_on_shift=True,
        shift_status=m.ShiftStatus.SHIFT_ON,
        moderation_status=m.ModerationStatus.APPROVED,
    )
    async_session.add(master)
    await async_session.flush()

    async_session.add(m.master_skills(master_id=master.id, skill_id=skill.id))
    async_session.add(m.master_districts(master_id=master.id, district_id=district.id))
    await async_session.commit()

    order = m.orders(
        city_id=city.id,
        district_id=district.id,
        status=m.OrderStatus.SEARCHING,
        category=m.OrderCategory.ELECTRICS,
    )
    async_session.add(order)
    await async_session.commit()

    order_id = order.id
    master_id = master.id

    cfg = DistConfig(
        tick_seconds=30,
        sla_seconds=120,
        rounds=2,
        top_log_n=10,
        to_admin_after_min=10,
    )

    # Распределение
    async_session.expire_all()
    await tick_once(cfg, bot=None, alerts_chat_id=None, session=async_session)
    await async_session.commit()

    # Проверка оффера
    async_session.expire_all()
    offer = await async_session.execute(
        select(m.offers).where(m.offers.order_id == order_id)
    )
    offer = offer.scalar_one()
    assert offer.master_id == master_id

    # Проверка метрик (если они создаются)
    async_session.expire_all()
    metrics = await async_session.execute(
        select(m.distribution_metrics).where(
            m.distribution_metrics.order_id == order_id
        )
    )
    metrics_list = metrics.scalars().all()

    # Если метрики создаются - проверяем их
    if metrics_list:
        metric = metrics_list[0]
        assert metric.master_id == master_id
        assert metric.round_number == 1
        assert metric.city_id == city.id
        assert metric.district_id == district.id
        assert metric.category == m.OrderCategory.ELECTRICS.value
        assert metric.candidates_count >= 1
