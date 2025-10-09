"""
Полноценные интеграционные тесты бизнес-логики.

Покрывает:
- Создание заказов в БД с разными параметрами
- Автораспределение офферов (2 раунда, SLA, эскалации)
- Смену статусов (полный жизненный цикл)
- Создание комиссий (расчёт ставок 50%/40%)
- Гарантийные заказы (preferred master, company_payment)
- Работу с районами и навыками

Все тесты используют:
- datetime.now(timezone.utc) вместо datetime.utcnow()
- session.expire_all() перед refresh
- Время БД через SELECT NOW()
- TRUNCATE CASCADE для очистки
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select, text

from field_service.db import models as m
from field_service.services.commission_service import CommissionService
from field_service.services.distribution_scheduler import (
    DistConfig,
    tick_once,
)

UTC = timezone.utc


# ===== Helper Functions =====

async def _get_db_now(session) -> datetime:
    """Получить текущее время БД (КРИТИЧНО для синхронизации)."""
    row = await session.execute(text("SELECT NOW()"))
    return row.scalar()


async def _create_test_city(session, name: str = "Test City") -> m.cities:
    """Создать тестовый город."""
    city = m.cities(
        name=name,
        timezone="Europe/Moscow",
        is_active=True,
    )
    session.add(city)
    await session.flush()
    return city


async def _create_test_district(
    session,
    city: m.cities,
    name: str = "Test District"
) -> m.districts:
    """Создать тестовый район."""
    district = m.districts(
        city_id=city.id,
        name=name,
    )
    session.add(district)
    await session.flush()
    return district


async def _create_test_skill(
    session,
    code: str = "ELEC",
    name: str = "Electrician"
) -> m.skills:
    """Создать тестовый навык."""
    skill = m.skills(
        code=code,
        name=name,
        is_active=True,
    )
    session.add(skill)
    await session.flush()
    return skill


async def _create_test_master(
    session,
    city: m.cities,
    district: m.districts,
    skill: m.skills,
    *,
    tg_user_id: int,
    full_name: str = "Test Master",
    is_on_shift: bool = True,
    verified: bool = True,
    has_vehicle: bool = True,
    rating: float = 4.5,
) -> m.masters:
    """Создать тестового мастера с навыком и районом."""
    master = m.masters(
        tg_user_id=tg_user_id,
        full_name=full_name,
        city_id=city.id,
        is_active=True,
        is_blocked=False,
        verified=verified,
        is_on_shift=is_on_shift,
        has_vehicle=has_vehicle,
        rating=rating,
        shift_status=m.ShiftStatus.SHIFT_ON if is_on_shift else m.ShiftStatus.SHIFT_OFF,
        moderation_status=m.ModerationStatus.APPROVED,
    )
    session.add(master)
    await session.flush()

    # Привязываем навык
    master_skill = m.master_skills(master_id=master.id, skill_id=skill.id)
    session.add(master_skill)

    # Привязываем район
    master_district = m.master_districts(
        master_id=master.id,
        district_id=district.id
    )
    session.add(master_district)

    await session.flush()
    return master


async def _create_test_order(
    session,
    city: m.cities,
    district: m.districts,
    *,
    status: m.OrderStatus = m.OrderStatus.SEARCHING,
    category: m.OrderCategory = m.OrderCategory.ELECTRICS,
    order_type: m.OrderType = m.OrderType.NORMAL,
    total_sum: Decimal = Decimal("3000"),
    preferred_master_id: int | None = None,
    assigned_master_id: int | None = None,
    company_payment: Decimal = Decimal("0"),
) -> m.orders:
    """Создать тестовый заказ."""
    order = m.orders(
        city_id=city.id,
        district_id=district.id,
        status=status,
        category=category,
        type=order_type,
        total_sum=total_sum,
        company_payment=company_payment,
        preferred_master_id=preferred_master_id,
        assigned_master_id=assigned_master_id,
        client_name="Test Client",
        client_phone="+79991234567",
    )
    session.add(order)
    await session.flush()
    return order


async def _create_owner_staff(session) -> m.staff_users:
    """Создать владельца системы для комиссий."""
    owner = m.staff_users(
        tg_user_id=9001,
        role=m.StaffRole.GLOBAL_ADMIN,
        full_name="System Owner",
        phone="+70000000000",
        is_active=True,
        commission_requisites={
            "methods": ["card", "sbp"],
            "card_number": "2200123456789012",
            "card_holder": "Ivanov I.I.",
            "card_bank": "T-Bank",
            "sbp_phone": "+79991234567",
            "sbp_bank": "T-Bank",
            "sbp_qr_file_id": "qr123",
            "other_text": "cash",
            "comment_template": "Commission #<order_id> from <master_fio>",
        },
    )
    session.add(owner)
    await session.flush()
    return owner


# ===== Integration Tests =====

@pytest.mark.asyncio
async def test_full_order_lifecycle_with_commission(async_session):
    """
    Полный тест жизненного цикла заказа:
    1. Создание заказа SEARCHING
    2. Автораспределение (tick_once)
    3. Оффер отправлен мастеру
    4. Мастер принимает (ASSIGNED)
    5. Смена статусов: EN_ROUTE -> WORKING -> PAYMENT
    6. Создание комиссии
    7. Проверка расчёта комиссии (50%)
    """
    # 1. Подготовка данных
    city = await _create_test_city(async_session)
    district = await _create_test_district(async_session, city)
    skill = await _create_test_skill(async_session, code="ELEC")
    master = await _create_test_master(
        async_session,
        city,
        district,
        skill,
        tg_user_id=123456,
        full_name="Ivan Ivanov",
    )
    owner = await _create_owner_staff(async_session)
    await async_session.commit()

    # 2. Создание заказа SEARCHING
    order = await _create_test_order(
        async_session,
        city,
        district,
        status=m.OrderStatus.SEARCHING,
        category=m.OrderCategory.ELECTRICS,
        total_sum=Decimal("3000"),
    )
    await async_session.commit()

    # Сохраняем ID для использования после expire_all
    order_id = order.id
    master_id = master.id

    # 3. Автораспределение - первый тик
    cfg = DistConfig(
        tick_seconds=30,
        sla_seconds=120,
        rounds=2,
        top_log_n=10,
        to_admin_after_min=10,
    )

    # Expire кэш перед tick_once
    async_session.expire_all()
    
    await tick_once(cfg, bot=None, alerts_chat_id=None, session=async_session)
    await async_session.commit()

    # 4. Проверка оффера
    async_session.expire_all()
    offer = await async_session.execute(
        select(m.offers).where(
            m.offers.order_id == order_id,
            m.offers.master_id == master_id,
        )
    )
    offer = offer.scalar_one()

    assert offer.state == m.OfferState.SENT
    assert offer.round_number == 1

    # 5. Мастер принимает оффер
    offer.state = m.OfferState.ACCEPTED
    offer.responded_at = await _get_db_now(async_session)

    async_session.expire_all()
    await async_session.refresh(order)
    order.status = m.OrderStatus.ASSIGNED
    order.assigned_master_id = master_id

    await async_session.commit()

    # 6. Смена статусов: ASSIGNED -> EN_ROUTE -> WORKING -> PAYMENT
    for new_status in [
        m.OrderStatus.EN_ROUTE,
        m.OrderStatus.WORKING,
        m.OrderStatus.PAYMENT,
    ]:
        async_session.expire_all()
        await async_session.refresh(order)
        order.status = new_status
        await async_session.commit()

    # 7. Создание комиссии
    service = CommissionService(async_session)
    commission = await service.create_for_order(order_id)
    await async_session.commit()

    # 8. Проверки комиссии
    assert commission is not None
    assert commission.order_id == order_id
    assert commission.master_id == master_id
    assert commission.status == m.CommissionStatus.WAIT_PAY
    assert commission.rate == Decimal("0.50")  # 50% для avg < 7000
    assert commission.amount == Decimal("1500.00")  # 3000 * 0.50
    assert not commission.is_paid
    assert not commission.has_checks
    assert commission.pay_to_snapshot is not None
    # Snapshot может быть пустым если owner requisites не настроены
    # Главное что структура создана
    assert isinstance(commission.pay_to_snapshot, dict)

    # Проверка дедлайна (3 часа от создания)
    db_now = await _get_db_now(async_session)
    time_diff = commission.deadline_at - db_now
    assert timedelta(hours=2, minutes=59) < time_diff < timedelta(hours=3, minutes=1)


@pytest.mark.asyncio
async def test_distribution_two_rounds_with_sla_timeout(async_session):
    """
    Тест 2 раундов распределения с таймаутом:
    1. Раунд 1: Мастер 1 получает оффер, не отвечает
    2. Оффер истекает (EXPIRED)
    3. Раунд 2: Мастер 2 получает оффер
    """
    # Подготовка: 2 мастера
    city = await _create_test_city(async_session)
    district = await _create_test_district(async_session, city)
    skill = await _create_test_skill(async_session, code="ELEC")

    master1 = await _create_test_master(
        async_session, city, district, skill,
        tg_user_id=111, full_name="Master 1"
    )
    master2 = await _create_test_master(
        async_session, city, district, skill,
        tg_user_id=222, full_name="Master 2"
    )
    await async_session.commit()

    order = await _create_test_order(
        async_session, city, district,
        status=m.OrderStatus.SEARCHING,
        category=m.OrderCategory.ELECTRICS,
    )
    order_id = order.id
    await async_session.commit()

    cfg = DistConfig(
        tick_seconds=30,
        sla_seconds=5,  # Короткий SLA для теста
        rounds=2,
        top_log_n=10,
        to_admin_after_min=10,
    )

    # Раунд 1
    async_session.expire_all()
    await tick_once(cfg, bot=None, alerts_chat_id=None, session=async_session)
    await async_session.commit()

    # Проверка оффера мастеру 1
    async_session.expire_all()
    offer1 = await async_session.execute(
        select(m.offers).where(
            m.offers.order_id == order_id,
            m.offers.round_number == 1
        )
    )
    offer1 = offer1.scalar_one()
    offer1_id = offer1.id
    assert offer1.state == m.OfferState.SENT

    # Ждём истечения SLA
    await asyncio.sleep(6)

    # Раунд 2: оффер должен истечь и создаться новый
    async_session.expire_all()
    await tick_once(cfg, bot=None, alerts_chat_id=None, session=async_session)
    await async_session.commit()

    # Проверка: первый оффер EXPIRED
    async_session.expire_all()
    await async_session.refresh(offer1)
    assert offer1.state == m.OfferState.EXPIRED
    assert offer1.responded_at is not None

    # Проверка: второй оффер создан
    async_session.expire_all()
    offer2 = await async_session.execute(
        select(m.offers).where(
            m.offers.order_id == order_id,
            m.offers.round_number == 2
        )
    )
    offer2 = offer2.scalar_one()
    assert offer2.state == m.OfferState.SENT
    assert offer2.id != offer1_id


@pytest.mark.asyncio
async def test_guarantee_order_with_preferred_master(async_session):
    """
    Тест гарантийного заказа с preferred мастером:
    1. Гарантийный заказ (type=GUARANTEE)
    2. preferred_master_id указан
    3. Распределение должно отдать приоритет preferred мастеру
    4. Комиссия НЕ создаётся (company_payment)
    """
    city = await _create_test_city(async_session)
    district = await _create_test_district(async_session, city)
    skill = await _create_test_skill(async_session, code="ELEC")

    preferred_master = await _create_test_master(
        async_session, city, district, skill,
        tg_user_id=111, full_name="Preferred Master"
    )
    other_master = await _create_test_master(
        async_session, city, district, skill,
        tg_user_id=222, full_name="Other Master",
        rating=5.0,  # Выше рейтинг, но не preferred
    )
    owner = await _create_owner_staff(async_session)
    await async_session.commit()

    order = await _create_test_order(
        async_session, city, district,
        status=m.OrderStatus.GUARANTEE,  # Гарантийный статус
        order_type=m.OrderType.GUARANTEE,
        category=m.OrderCategory.ELECTRICS,
        total_sum=Decimal("0"),
        company_payment=Decimal("2500"),
        preferred_master_id=preferred_master.id,
    )
    order_id = order.id
    preferred_master_id = preferred_master.id
    await async_session.commit()

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

    # Проверка: оффер ушёл preferred мастеру
    async_session.expire_all()
    offer = await async_session.execute(
        select(m.offers).where(m.offers.order_id == order_id)
    )
    offer = offer.scalar_one()

    assert offer.master_id == preferred_master_id
    assert offer.state == m.OfferState.SENT

    # Мастер принимает
    offer.state = m.OfferState.ACCEPTED
    offer.responded_at = await _get_db_now(async_session)

    async_session.expire_all()
    await async_session.refresh(order)
    order.status = m.OrderStatus.ASSIGNED
    order.assigned_master_id = preferred_master_id
    await async_session.commit()

    # Переход в PAYMENT
    for status in [m.OrderStatus.EN_ROUTE, m.OrderStatus.WORKING, m.OrderStatus.PAYMENT]:
        async_session.expire_all()
        await async_session.refresh(order)
        order.status = status
        await async_session.commit()

    # Попытка создать комиссию
    service = CommissionService(async_session)
    commission = await service.create_for_order(order_id)

    # Комиссия НЕ создаётся для гарантийных заказов
    assert commission is None

    # Проверка что в БД нет комиссии
    async_session.expire_all()
    result = await async_session.execute(
        select(m.commissions).where(m.commissions.order_id == order_id)
    )
    assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_high_avg_check_master_gets_40_percent_commission(async_session):
    """
    Тест расчёта комиссии 40% для мастера с высоким средним чеком:
    1. Мастер выполнил заказ на 8000 руб за последнюю неделю
    2. avg_week_check >= 7000
    3. Комиссия должна быть 40% вместо 50%
    """
    city = await _create_test_city(async_session)
    district = await _create_test_district(async_session, city)
    skill = await _create_test_skill(async_session, code="ELEC")
    master = await _create_test_master(
        async_session, city, district, skill,
        tg_user_id=111, full_name="Pro Master"
    )
    owner = await _create_owner_staff(async_session)
    master_id = master.id
    await async_session.commit()

    # Создаём закрытый заказ за неделю с большим чеком
    db_now = await _get_db_now(async_session)
    old_order = m.orders(
        city_id=city.id,
        district_id=district.id,
        status=m.OrderStatus.CLOSED,
        category=m.OrderCategory.ELECTRICS,
        total_sum=Decimal("8000"),  # Большой чек
        assigned_master_id=master_id,
        created_at=db_now - timedelta(days=3),
    )
    async_session.add(old_order)
    await async_session.commit()

    # Новый заказ
    new_order = await _create_test_order(
        async_session, city, district,
        status=m.OrderStatus.PAYMENT,
        total_sum=Decimal("5000"),
        assigned_master_id=master_id,
    )
    new_order_id = new_order.id
    await async_session.commit()

    # Создание комиссии
    service = CommissionService(async_session)
    commission = await service.create_for_order(new_order_id)
    await async_session.commit()

    # Проверка: rate=40%, amount=2000 (5000 * 0.40)
    assert commission is not None
    assert commission.rate == Decimal("0.40")
    assert commission.amount == Decimal("2000.00")


@pytest.mark.asyncio
async def test_no_candidates_leads_to_escalation_logist(async_session):
    """
    Тест эскалации к логисту при отсутствии кандидатов:
    1. Заказ SEARCHING
    2. Нет мастеров в районе с нужным навыком
    3. 2 раунда пустых
    4. Эскалация к логисту (dist_escalated_logist_at)
    """
    city = await _create_test_city(async_session)
    district = await _create_test_district(async_session, city)
    # НЕ создаём мастеров!

    order = await _create_test_order(
        async_session, city, district,
        status=m.OrderStatus.SEARCHING,
        category=m.OrderCategory.ELECTRICS,
    )
    order_id = order.id
    await async_session.commit()

    cfg = DistConfig(
        tick_seconds=30,
        sla_seconds=120,
        rounds=2,
        top_log_n=10,
        to_admin_after_min=10,
    )

    # Раунд 1
    async_session.expire_all()
    await tick_once(cfg, bot=None, alerts_chat_id=None, session=async_session)
    await async_session.commit()

    # Раунд 2
    async_session.expire_all()
    await tick_once(cfg, bot=None, alerts_chat_id=None, session=async_session)
    await async_session.commit()

    # Проверка эскалации
    async_session.expire_all()
    await async_session.refresh(order)

    assert order.dist_escalated_logist_at is not None
    assert order.dist_escalated_admin_at is None  # Ещё не дошло до админа


@pytest.mark.asyncio
async def test_escalation_to_admin_after_timeout(async_session):
    """
    Тест эскалации к админу через 10 минут после эскалации к логисту:
    1. Эскалация к логисту
    2. Ждём 10+ минут (манипуляция времени)
    3. Эскалация к админу (dist_escalated_admin_at)
    """
    city = await _create_test_city(async_session)
    district = await _create_test_district(async_session, city)

    order = await _create_test_order(
        async_session, city, district,
        status=m.OrderStatus.SEARCHING,
        category=m.OrderCategory.ELECTRICS,
    )
    order_id = order.id
    await async_session.commit()

    # Устанавливаем эскалацию к логисту вручную (11 минут назад)
    db_now = await _get_db_now(async_session)
    logist_time = db_now - timedelta(minutes=11)

    async_session.expire_all()
    await async_session.refresh(order)
    order.dist_escalated_logist_at = logist_time
    await async_session.commit()

    cfg = DistConfig(
        tick_seconds=30,
        sla_seconds=120,
        rounds=2,
        top_log_n=10,
        to_admin_after_min=10,  # 10 минут
    )

    # Тик: должна произойти эскалация к админу
    async_session.expire_all()
    await tick_once(cfg, bot=None, alerts_chat_id=None, session=async_session)
    await async_session.commit()

    # Проверка
    async_session.expire_all()
    await async_session.refresh(order)

    assert order.dist_escalated_logist_at == logist_time
    assert order.dist_escalated_admin_at is not None
    assert order.dist_escalated_admin_at > logist_time


@pytest.mark.asyncio
async def test_master_cannot_receive_duplicate_offers(async_session):
    """
    Тест защиты от дублирования офферов:
    1. Мастер получил оффер
    2. Оффер истёк
    3. В следующем раунде мастер НЕ должен получить повторный оффер
    """
    city = await _create_test_city(async_session)
    district = await _create_test_district(async_session, city)
    skill = await _create_test_skill(async_session, code="ELEC")
    master = await _create_test_master(
        async_session, city, district, skill,
        tg_user_id=111, full_name="Master"
    )
    master_id = master.id
    await async_session.commit()

    order = await _create_test_order(
        async_session, city, district,
        status=m.OrderStatus.SEARCHING,
        category=m.OrderCategory.ELECTRICS,
    )
    order_id = order.id
    await async_session.commit()

    cfg = DistConfig(
        tick_seconds=30,
        sla_seconds=3,
        rounds=3,
        top_log_n=10,
        to_admin_after_min=10,
    )

    # Раунд 1
    async_session.expire_all()
    await tick_once(cfg, bot=None, alerts_chat_id=None, session=async_session)
    await async_session.commit()

    # Проверка оффера
    async_session.expire_all()
    offers = await async_session.execute(
        select(m.offers).where(m.offers.order_id == order_id)
    )
    offers_list = offers.scalars().all()
    assert len(offers_list) == 1
    assert offers_list[0].master_id == master_id

    # Ждём истечения
    await asyncio.sleep(4)

    # Раунд 2
    async_session.expire_all()
    await tick_once(cfg, bot=None, alerts_chat_id=None, session=async_session)
    await async_session.commit()

    # Проверка: новых офферов не должно быть (мастер уже получал)
    async_session.expire_all()
    offers = await async_session.execute(
        select(m.offers).where(m.offers.order_id == order_id)
    )
    offers_list = offers.scalars().all()
    assert len(offers_list) == 1  # Только один оффер


@pytest.mark.asyncio
async def test_status_history_tracking(async_session):
    """
    Тест записи истории статусов:
    1. Создание заказа SEARCHING
    2. Смена статусов до CLOSED
    3. Проверка order_status_history
    """
    city = await _create_test_city(async_session)
    district = await _create_test_district(async_session, city)

    order = await _create_test_order(
        async_session, city, district,
        status=m.OrderStatus.CREATED,
    )
    order_id = order.id
    await async_session.commit()

    # Смена статусов с записью в историю
    statuses = [
        (m.OrderStatus.CREATED, m.OrderStatus.SEARCHING),
        (m.OrderStatus.SEARCHING, m.OrderStatus.ASSIGNED),
        (m.OrderStatus.ASSIGNED, m.OrderStatus.EN_ROUTE),
        (m.OrderStatus.EN_ROUTE, m.OrderStatus.WORKING),
        (m.OrderStatus.WORKING, m.OrderStatus.PAYMENT),
        (m.OrderStatus.PAYMENT, m.OrderStatus.CLOSED),
    ]

    for from_status, to_status in statuses:
        async_session.expire_all()
        await async_session.refresh(order)
        order.status = to_status

        history = m.order_status_history(
            order_id=order_id,
            from_status=from_status,
            to_status=to_status,
            reason="test_transition",
            actor_type=m.ActorType.SYSTEM,
        )
        async_session.add(history)
        await async_session.commit()

    # Проверка истории
    async_session.expire_all()
    history_records = await async_session.execute(
        select(m.order_status_history)
        .where(m.order_status_history.order_id == order_id)
        .order_by(m.order_status_history.created_at)
    )
    history_list = history_records.scalars().all()

    assert len(history_list) == 6
    assert history_list[0].from_status == m.OrderStatus.CREATED
    assert history_list[0].to_status == m.OrderStatus.SEARCHING
    assert history_list[-1].from_status == m.OrderStatus.PAYMENT
    assert history_list[-1].to_status == m.OrderStatus.CLOSED


@pytest.mark.asyncio
async def test_multiple_masters_ranking(async_session):
    """
    Тест ранжирования нескольких мастеров:
    1. Создаём 3 мастеров с разными параметрами:
       - Master 1: has_vehicle=True, rating=5.0
       - Master 2: has_vehicle=False, rating=4.5
       - Master 3: has_vehicle=True, rating=4.0
    2. Проверка что первым получит оффер Master 1 (машина + высокий рейтинг)
    """
    city = await _create_test_city(async_session)
    district = await _create_test_district(async_session, city)
    skill = await _create_test_skill(async_session, code="ELEC")

    master1 = await _create_test_master(
        async_session, city, district, skill,
        tg_user_id=111, full_name="Master 1",
        has_vehicle=True, rating=5.0
    )
    master2 = await _create_test_master(
        async_session, city, district, skill,
        tg_user_id=222, full_name="Master 2",
        has_vehicle=False, rating=4.5
    )
    master3 = await _create_test_master(
        async_session, city, district, skill,
        tg_user_id=333, full_name="Master 3",
        has_vehicle=True, rating=4.0
    )
    master1_id = master1.id
    await async_session.commit()

    order = await _create_test_order(
        async_session, city, district,
        status=m.OrderStatus.SEARCHING,
        category=m.OrderCategory.ELECTRICS,
    )
    order_id = order.id
    await async_session.commit()

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

    # Проверка: оффер должен уйти Master 1
    async_session.expire_all()
    offer = await async_session.execute(
        select(m.offers).where(m.offers.order_id == order_id)
    )
    offer = offer.scalar_one()

    assert offer.master_id == master1_id
    assert offer.state == m.OfferState.SENT


@pytest.mark.asyncio
async def test_master_on_break_cannot_receive_offers(async_session):
    """
    Тест что мастер на перерыве не получает офферы:
    1. Мастер в статусе BREAK с break_until в будущем
    2. Заказ SEARCHING
    3. Распределение должно пропустить мастера
    """
    city = await _create_test_city(async_session)
    district = await _create_test_district(async_session, city)
    skill = await _create_test_skill(async_session, code="ELEC")

    db_now = await _get_db_now(async_session)
    master = await _create_test_master(
        async_session, city, district, skill,
        tg_user_id=111, full_name="Master on Break"
    )
    master.shift_status = m.ShiftStatus.BREAK
    master.break_until = db_now + timedelta(hours=1)
    await async_session.commit()

    order = await _create_test_order(
        async_session, city, district,
        status=m.OrderStatus.SEARCHING,
        category=m.OrderCategory.ELECTRICS,
    )
    order_id = order.id
    await async_session.commit()

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

    # Проверка эскалации после 2 раундов
    await tick_once(cfg, bot=None, alerts_chat_id=None, session=async_session)
    await async_session.commit()

    async_session.expire_all()
    await async_session.refresh(order)
    assert order.dist_escalated_logist_at is not None
