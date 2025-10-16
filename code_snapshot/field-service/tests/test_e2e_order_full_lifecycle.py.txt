"""
E2E тест: Полный цикл заказа от создания до автозакрытия в очереди

Сценарий:
1. Создание заказа → статус SEARCHING
2. Автодистрибуция → отправка оффера мастеру
3. Мастер принимает → статус ASSIGNED
4. Проверка, что активных офферов больше нет
5. Попытка ручного переназначения → должна быть запрещена (уже ASSIGNED)
6. Мастер закрывает заказ → статус CLOSED
7. Проверка автозакрытия в очереди (заказ не должен быть виден)

✅ Использует PostgreSQL (не SQLite)
✅ Минимальный набор данных из seed_ci_minimal
✅ Проверяет все ключевые переходы статусов
"""

import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from field_service.db import models as m
from field_service.services.distribution_scheduler import tick_once, DistConfig
from field_service.services.orders_service import OrdersService


UTC = timezone.utc


async def _get_db_now(session: AsyncSession) -> datetime:
    """Получает текущее время из БД."""
    row = await session.execute(text("SELECT NOW()"))
    return row.scalar()


@pytest.mark.asyncio
async def test_e2e_order_lifecycle_full_cycle(
    session: AsyncSession,
    sample_city,
    sample_district,
    sample_skill,
):
    """
    E2E: Создание → Автодистрибуция → Принятие → Защита от переназначения → Закрытие
    
    Проверяет:
    - Автодистрибуцию с успешным принятием оффера
    - Отсутствие активных офферов после принятия
    - Запрет ручного переназначения для ASSIGNED
    - Корректное закрытие и автозакрытие в очереди
    """
    
    # ============================================================================
    # Шаг 1: Создание заказа
    # ============================================================================
    db_now = await _get_db_now(session)
    
    order = m.orders(
        status=m.OrderStatus.SEARCHING,
        city_id=sample_city.id,
        district_id=sample_district.id,
        category=m.OrderCategory.ELECTRICS,
        house="42",
        timeslot_start_utc=db_now + timedelta(hours=2),
        timeslot_end_utc=db_now + timedelta(hours=4),
        created_at=db_now,
    )
    session.add(order)
    await session.commit()
    await session.refresh(order)
    
    initial_order_id = order.id
    assert order.status == m.OrderStatus.SEARCHING, "Заказ должен быть в статусе SEARCHING"
    
    # ============================================================================
    # Шаг 2: Создание мастера для автодистрибуции
    # ============================================================================
    master = m.masters(
        tg_id=777000001,
        full_name="Тестовый Мастер Евгений",
        phone="+79990001111",
        city_id=sample_city.id,
        is_verified=True,
        is_active=True,
        is_on_shift=True,
        has_car=True,
        avg_week_check=8000.0,
        rating_avg=4.8,
        created_at=db_now,
    )
    session.add(master)
    
    # Добавляем район работы
    master_district = m.master_districts(
        master_id=None,  # будет установлен после flush
        district_id=sample_district.id,
    )
    session.add(master_district)
    await session.flush()
    master_district.master_id = master.id
    
    # Добавляем навык
    master_skill = m.master_skills(
        master_id=master.id,
        skill_id=sample_skill.id,
    )
    session.add(master_skill)
    await session.commit()
    await session.refresh(master)
    
    # ============================================================================
    # Шаг 3: Запуск автодистрибуции
    # ============================================================================
    cfg = DistConfig(
        tick_seconds=30,
        sla_seconds=120,
        rounds=2,
        top_log_n=10,
        to_admin_after_min=10,
    )
    
    await tick_once(cfg, bot=None, alerts_chat_id=None, session=session)
    
    # Проверяем что оффер создан
    session.expire_all()
    await session.refresh(order)
    
    offer_stmt = select(m.offers).where(
        m.offers.order_id == initial_order_id,
        m.offers.master_id == master.id,
    )
    offer_result = await session.execute(offer_stmt)
    offer = offer_result.scalar_one_or_none()
    
    assert offer is not None, "Оффер должен быть создан для мастера"
    assert offer.state == m.OfferState.SENT, "Оффер должен быть в статусе SENT"
    
    # ============================================================================
    # Шаг 4: Мастер принимает оффер
    # ============================================================================
    orders_service = OrdersService(session)
    success, error = await orders_service.accept_offer(
        offer_id=offer.id,
        master_id=master.id,
    )
    
    assert success is True, f"Принятие оффера должно быть успешным, ошибка: {error}"
    assert error is None, "Не должно быть ошибки при принятии"
    
    await session.commit()
    session.expire_all()
    await session.refresh(order)
    await session.refresh(offer)
    
    assert order.status == m.OrderStatus.ASSIGNED, "Заказ должен быть в статусе ASSIGNED"
    assert order.assigned_master_id == master.id, "Мастер должен быть назначен"
    assert offer.state == m.OfferState.ACCEPTED, "Оффер должен быть в статусе ACCEPTED"
    
    # ============================================================================
    # Шаг 5: Проверка отсутствия активных офферов
    # ============================================================================
    active_offers_stmt = select(m.offers).where(
        m.offers.order_id == initial_order_id,
        m.offers.state.in_([m.OfferState.SENT, m.OfferState.VIEWED]),
    )
    active_offers_result = await session.execute(active_offers_stmt)
    active_offers = active_offers_result.scalars().all()
    
    assert len(active_offers) == 0, "Не должно быть активных офферов после принятия"
    
    # ============================================================================
    # Шаг 6: Попытка ручного переназначения (должна быть запрещена)
    # ============================================================================
    # Создаём второго мастера
    master2 = m.masters(
        tg_id=777000002,
        full_name="Второй Мастер Иван",
        phone="+79990002222",
        city_id=sample_city.id,
        is_verified=True,
        is_active=True,
        is_on_shift=True,
        has_car=False,
        avg_week_check=5000.0,
        rating_avg=4.5,
        created_at=db_now,
    )
    session.add(master2)
    await session.flush()
    
    # Добавляем район и навык второму мастеру
    master2_district = m.master_districts(
        master_id=master2.id,
        district_id=sample_district.id,
    )
    session.add(master2_district)
    
    master2_skill = m.master_skills(
        master_id=master2.id,
        skill_id=sample_skill.id,
    )
    session.add(master2_skill)
    await session.commit()
    
    # Проверяем что нельзя переназначить заказ в статусе ASSIGNED
    # (это должно быть запрещено на уровне логики)
    session.expire_all()
    await session.refresh(order)
    
    # Создаём оффер вручную (имитация ручного назначения)
    manual_offer = m.offers(
        order_id=initial_order_id,
        master_id=master2.id,
        state=m.OfferState.SENT,
        expires_at=db_now + timedelta(minutes=5),
    )
    session.add(manual_offer)
    
    # Пытаемся принять оффер вторым мастером
    success2, error2 = await orders_service.accept_offer(
        offer_id=manual_offer.id,
        master_id=master2.id,
    )
    
    # Принятие должно быть запрещено, т.к. заказ уже ASSIGNED
    assert success2 is False, "Принятие оффера должно быть запрещено для ASSIGNED заказа"
    assert error2 is not None, "Должна быть ошибка при попытке принять ASSIGNED заказ"
    
    await session.commit()
    session.expire_all()
    await session.refresh(order)
    
    # Заказ всё ещё должен быть назначен на первого мастера
    assert order.assigned_master_id == master.id, "Заказ должен остаться за первым мастером"
    assert order.status == m.OrderStatus.ASSIGNED, "Статус должен остаться ASSIGNED"
    
    # ============================================================================
    # Шаг 7: Закрытие заказа мастером
    # ============================================================================
    # Переводим в WORKING
    order.status = m.OrderStatus.WORKING
    order.version = (order.version or 1) + 1
    await session.commit()
    
    # Закрываем заказ
    order.status = m.OrderStatus.CLOSED
    order.closed_at = await _get_db_now(session)
    order.total_sum = 5000.0
    order.version = (order.version or 1) + 1
    await session.commit()
    
    session.expire_all()
    await session.refresh(order)
    
    assert order.status == m.OrderStatus.CLOSED, "Заказ должен быть закрыт"
    assert order.closed_at is not None, "Должна быть установлена дата закрытия"
    
    # ============================================================================
    # Шаг 8: Проверка автозакрытия в очереди
    # ============================================================================
    # Проверяем что заказ больше не попадает в очередь на распределение
    searching_orders_stmt = select(m.orders).where(
        m.orders.status.in_([
            m.OrderStatus.SEARCHING,
            m.OrderStatus.CREATED,
            m.OrderStatus.DEFERRED,
        ])
    )
    searching_result = await session.execute(searching_orders_stmt)
    searching_orders = searching_result.scalars().all()
    
    order_ids_in_queue = [o.id for o in searching_orders]
    assert initial_order_id not in order_ids_in_queue, "Закрытый заказ не должен быть в очереди"
    
    # Проверяем что закрытый заказ не получит новых офферов
    await tick_once(cfg, bot=None, alerts_chat_id=None, session=session)
    
    new_offers_stmt = select(m.offers).where(
        m.offers.order_id == initial_order_id,
        m.offers.created_at > db_now,
    )
    new_offers_result = await session.execute(new_offers_stmt)
    new_offers = new_offers_result.scalars().all()
    
    assert len(new_offers) == 0, "Закрытый заказ не должен получать новые офферы"


@pytest.mark.asyncio
async def test_e2e_order_lifecycle_no_masters_escalation(
    session: AsyncSession,
    sample_city,
    sample_district,
):
    """
    E2E: Заказ без доступных мастеров → эскалация
    
    Проверяет:
    - Эскалацию логисту при отсутствии мастеров
    - Эскалацию админу через 10 минут
    """
    
    db_now = await _get_db_now(session)
    
    # Создаём заказ без мастеров (нет подходящих кандидатов)
    order = m.orders(
        status=m.OrderStatus.SEARCHING,
        city_id=sample_city.id,
        district_id=sample_district.id,
        category=m.OrderCategory.ELECTRICS,
        house="1",
        timeslot_start_utc=db_now + timedelta(hours=2),
        timeslot_end_utc=db_now + timedelta(hours=4),
    )
    session.add(order)
    await session.commit()
    await session.refresh(order)
    
    cfg = DistConfig(
        tick_seconds=30,
        sla_seconds=120,
        rounds=2,
        top_log_n=10,
        to_admin_after_min=10,
    )
    
    # Первый тик - должна произойти эскалация логисту
    await tick_once(cfg, bot=None, alerts_chat_id=None, session=session)
    
    session.expire_all()
    await session.refresh(order)
    
    assert order.dist_escalated_logist_at is not None, "Должна быть эскалация логисту"
    assert order.escalation_logist_notified_at is not None, "Уведомление логисту должно быть отправлено"
    
    # Эмулируем 15 минут без действий логиста
    order.dist_escalated_logist_at = db_now - timedelta(minutes=15)
    order.escalation_logist_notified_at = db_now - timedelta(minutes=14)
    await session.commit()
    
    # Второй тик - должна произойти эскалация админу
    await tick_once(cfg, bot=None, alerts_chat_id=None, session=session)
    
    session.expire_all()
    await session.refresh(order)
    
    assert order.dist_escalated_admin_at is not None, "Должна быть эскалация админу"
    assert order.escalation_admin_notified_at is not None, "Уведомление админу должно быть отправлено"


@pytest.mark.asyncio
async def test_e2e_order_lifecycle_decline_and_reassign(
    session: AsyncSession,
    sample_city,
    sample_district,
    sample_skill,
):
    """
    E2E: Мастер отклоняет оффер → повторная дистрибуция → принятие другим мастером
    
    Проверяет:
    - Отклонение оффера первым мастером
    - Повторную дистрибуцию другому мастеру
    - Успешное принятие вторым мастером
    """
    
    db_now = await _get_db_now(session)
    
    # Создаём заказ
    order = m.orders(
        status=m.OrderStatus.SEARCHING,
        city_id=sample_city.id,
        district_id=sample_district.id,
        category=m.OrderCategory.ELECTRICS,
        house="100",
        timeslot_start_utc=db_now + timedelta(hours=2),
        timeslot_end_utc=db_now + timedelta(hours=4),
    )
    session.add(order)
    await session.commit()
    await session.refresh(order)
    
    # Создаём двух мастеров
    master1 = m.masters(
        tg_id=777000003,
        full_name="Мастер Первый",
        phone="+79990003333",
        city_id=sample_city.id,
        is_verified=True,
        is_active=True,
        is_on_shift=True,
        has_car=True,
        avg_week_check=9000.0,  # Выше - будет первым
        rating_avg=4.9,
    )
    session.add(master1)
    await session.flush()
    
    master2 = m.masters(
        tg_id=777000004,
        full_name="Мастер Второй",
        phone="+79990004444",
        city_id=sample_city.id,
        is_verified=True,
        is_active=True,
        is_on_shift=True,
        has_car=True,
        avg_week_check=7000.0,  # Ниже - будет вторым
        rating_avg=4.7,
    )
    session.add(master2)
    await session.flush()
    
    # Добавляем районы и навыки обоим мастерам
    for master in [master1, master2]:
        md = m.master_districts(master_id=master.id, district_id=sample_district.id)
        session.add(md)
        ms = m.master_skills(master_id=master.id, skill_id=sample_skill.id)
        session.add(ms)
    
    await session.commit()
    
    # Первая дистрибуция - оффер должен пойти первому мастеру (выше avg_week_check)
    cfg = DistConfig(
        tick_seconds=30,
        sla_seconds=120,
        rounds=2,
        top_log_n=10,
        to_admin_after_min=10,
    )
    
    await tick_once(cfg, bot=None, alerts_chat_id=None, session=session)
    
    offer1_stmt = select(m.offers).where(
        m.offers.order_id == order.id,
        m.offers.master_id == master1.id,
    )
    offer1_result = await session.execute(offer1_stmt)
    offer1 = offer1_result.scalar_one_or_none()
    
    assert offer1 is not None, "Оффер должен быть создан для первого мастера"
    
    # Первый мастер отклоняет
    orders_service = OrdersService(session)
    success1, _ = await orders_service.decline_offer(
        offer_id=offer1.id,
        master_id=master1.id,
    )
    
    assert success1 is True, "Отклонение должно быть успешным"
    await session.commit()
    
    session.expire_all()
    await session.refresh(offer1)
    assert offer1.state == m.OfferState.DECLINED, "Оффер должен быть отклонён"
    
    # Вторая дистрибуция - оффер должен пойти второму мастеру
    await tick_once(cfg, bot=None, alerts_chat_id=None, session=session)
    
    offer2_stmt = select(m.offers).where(
        m.offers.order_id == order.id,
        m.offers.master_id == master2.id,
    )
    offer2_result = await session.execute(offer2_stmt)
    offer2 = offer2_result.scalar_one_or_none()
    
    assert offer2 is not None, "Оффер должен быть создан для второго мастера"
    
    # Второй мастер принимает
    success2, error2 = await orders_service.accept_offer(
        offer_id=offer2.id,
        master_id=master2.id,
    )
    
    assert success2 is True, f"Принятие должно быть успешным, ошибка: {error2}"
    await session.commit()
    
    session.expire_all()
    await session.refresh(order)
    
    assert order.status == m.OrderStatus.ASSIGNED, "Заказ должен быть назначен"
    assert order.assigned_master_id == master2.id, "Заказ должен быть назначен второму мастеру"
