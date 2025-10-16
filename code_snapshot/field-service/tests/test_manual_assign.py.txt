"""
Тесты для сервиса ручного назначения мастера на заказ.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from field_service.db import models as m
from field_service.services.manual_assign import assign_manually


@pytest.mark.asyncio
async def test_manual_assign_eligible_master_success(
    async_session,
    sample_city,
    sample_district,
    sample_skill,
    sample_master,
) -> None:
    """Тест успешного назначения подходящего мастера."""
    # Создаём администратора
    staff = m.staff_users(
        id=1,
        tg_user_id=999000,
        full_name="Admin Test",
        role=m.StaffRole.GLOBAL_ADMIN,
        is_active=True,
    )
    async_session.add(staff)
    await async_session.flush()

    # Создаём заказ в статусе SEARCHING
    order = m.orders(
        city_id=sample_city.id,
        district_id=sample_district.id,
        status=m.OrderStatus.SEARCHING,
        category=m.OrderCategory.ELECTRICS,
        description="Test order",
        client_name="Client Test",
        client_phone="+79991234567",
    )
    async_session.add(order)
    await async_session.commit()

    # Вызываем сервис ручного назначения
    success, error = await assign_manually(
        session=async_session,
        order_id=order.id,
        master_id=sample_master.id,
        staff_id=staff.id,
    )

    # Проверяем результат
    assert success is True
    assert error is None

    # Проверяем что заказ назначен
    await async_session.refresh(order)
    assert order.assigned_master_id == sample_master.id
    assert order.status == m.OrderStatus.ASSIGNED

    # Проверяем запись в истории
    history_rows = await async_session.execute(
        select(m.order_status_history)
        .where(m.order_status_history.order_id == order.id)
        .order_by(m.order_status_history.id.desc())
    )
    history = history_rows.scalar_one()
    assert history.from_status == m.OrderStatus.SEARCHING
    assert history.to_status == m.OrderStatus.ASSIGNED
    assert history.changed_by_staff_id == staff.id
    assert history.reason == "manual_assign"
    assert history.actor_type == m.ActorType.ADMIN
    assert history.context["master_id"] == sample_master.id
    assert history.context["staff_id"] == staff.id


@pytest.mark.asyncio
async def test_manual_assign_ineligible_master_fails(
    async_session,
    sample_city,
    sample_district,
    sample_skill,
) -> None:
    """Тест отказа при назначении неподходящего мастера."""
    # Создаём администратора
    staff = m.staff_users(
        id=1,
        tg_user_id=999000,
        full_name="Admin Test",
        role=m.StaffRole.GLOBAL_ADMIN,
        is_active=True,
    )
    async_session.add(staff)
    await async_session.flush()

    # Создаём мастера БЕЗ подходящего навыка
    master = m.masters(
        tg_user_id=888999,
        full_name="Ineligible Master",
        city_id=sample_city.id,
        is_active=True,
        is_blocked=False,
        verified=True,
        is_on_shift=True,
        has_vehicle=True,
        rating=4.5,
    )
    async_session.add(master)
    await async_session.flush()

    # Привязываем район (но не навык!)
    master_district = m.master_districts(
        master_id=master.id,
        district_id=sample_district.id
    )
    async_session.add(master_district)

    # Создаём заказ
    order = m.orders(
        city_id=sample_city.id,
        district_id=sample_district.id,
        status=m.OrderStatus.SEARCHING,
        category=m.OrderCategory.ELECTRICS,
        description="Test order",
        client_name="Client Test",
        client_phone="+79991234567",
    )
    async_session.add(order)
    await async_session.commit()

    # Вызываем сервис ручного назначения
    success, error = await assign_manually(
        session=async_session,
        order_id=order.id,
        master_id=master.id,
        staff_id=staff.id,
    )

    # Проверяем результат - должен быть отказ
    assert success is False
    assert error is not None
    assert "не подходит" in error.lower()

    # Проверяем что заказ НЕ назначен
    await async_session.refresh(order)
    assert order.assigned_master_id is None
    assert order.status == m.OrderStatus.SEARCHING


@pytest.mark.asyncio
async def test_manual_assign_cancels_active_offers(
    async_session,
    sample_city,
    sample_district,
    sample_skill,
    sample_master,
) -> None:
    """Тест отмены активных офферов при ручном назначении."""
    # Создаём администратора
    staff = m.staff_users(
        id=1,
        tg_user_id=999000,
        full_name="Admin Test",
        role=m.StaffRole.GLOBAL_ADMIN,
        is_active=True,
    )
    async_session.add(staff)
    await async_session.flush()

    # Создаём второго мастера
    master2 = m.masters(
        tg_user_id=777888,
        full_name="Second Master",
        city_id=sample_city.id,
        is_active=True,
        is_blocked=False,
        verified=True,
        is_on_shift=True,
        has_vehicle=False,
        rating=4.0,
    )
    async_session.add(master2)
    await async_session.flush()

    # Привязываем навык и район ко второму мастеру
    master2_skill = m.master_skills(
        master_id=master2.id,
        skill_id=sample_skill.id
    )
    master2_district = m.master_districts(
        master_id=master2.id,
        district_id=sample_district.id
    )
    async_session.add_all([master2_skill, master2_district])

    # Создаём заказ
    order = m.orders(
        city_id=sample_city.id,
        district_id=sample_district.id,
        status=m.OrderStatus.SEARCHING,
        category=m.OrderCategory.ELECTRICS,
        description="Test order",
        client_name="Client Test",
        client_phone="+79991234567",
    )
    async_session.add(order)
    await async_session.flush()

    # Создаём активные офферы для обоих мастеров
    offer1 = m.offers(
        order_id=order.id,
        master_id=sample_master.id,
        round_number=1,
        state=m.OfferState.SENT,
        sent_at=datetime.now(timezone.utc),
    )
    offer2 = m.offers(
        order_id=order.id,
        master_id=master2.id,
        round_number=1,
        state=m.OfferState.VIEWED,
        sent_at=datetime.now(timezone.utc),
    )
    async_session.add_all([offer1, offer2])
    await async_session.commit()

    # Вызываем ручное назначение на первого мастера
    success, error = await assign_manually(
        session=async_session,
        order_id=order.id,
        master_id=sample_master.id,
        staff_id=staff.id,
    )

    # Проверяем успех
    assert success is True
    assert error is None

    # Проверяем что все офферы отменены
    offers_result = await async_session.execute(
        select(m.offers).where(m.offers.order_id == order.id)
    )
    offers = offers_result.scalars().all()
    assert len(offers) == 2
    for offer in offers:
        assert offer.state == m.OfferState.CANCELED
        assert offer.responded_at is not None


@pytest.mark.asyncio
async def test_manual_assign_already_assigned_order_fails(
    async_session,
    sample_city,
    sample_district,
    sample_skill,
    sample_master,
) -> None:
    """Тест отказа при попытке назначить уже назначенный заказ."""
    # Создаём администратора
    staff = m.staff_users(
        id=1,
        tg_user_id=999000,
        full_name="Admin Test",
        role=m.StaffRole.GLOBAL_ADMIN,
        is_active=True,
    )
    async_session.add(staff)
    await async_session.flush()

    # Создаём второго мастера
    master2 = m.masters(
        tg_user_id=777888,
        full_name="Second Master",
        city_id=sample_city.id,
        is_active=True,
        is_blocked=False,
        verified=True,
        is_on_shift=True,
        has_vehicle=False,
        rating=4.0,
    )
    async_session.add(master2)
    await async_session.flush()

    # Привязываем навык и район ко второму мастеру
    master2_skill = m.master_skills(
        master_id=master2.id,
        skill_id=sample_skill.id
    )
    master2_district = m.master_districts(
        master_id=master2.id,
        district_id=sample_district.id
    )
    async_session.add_all([master2_skill, master2_district])

    # Создаём заказ УЖЕ НАЗНАЧЕННЫЙ первому мастеру
    order = m.orders(
        city_id=sample_city.id,
        district_id=sample_district.id,
        status=m.OrderStatus.ASSIGNED,
        category=m.OrderCategory.ELECTRICS,
        description="Test order",
        client_name="Client Test",
        client_phone="+79991234567",
        assigned_master_id=sample_master.id,
    )
    async_session.add(order)
    await async_session.commit()

    # Пытаемся назначить второму мастеру
    success, error = await assign_manually(
        session=async_session,
        order_id=order.id,
        master_id=master2.id,
        staff_id=staff.id,
    )

    # Проверяем отказ
    assert success is False
    assert error is not None
    assert "уже назначен" in error.lower()

    # Проверяем что заказ остался у первого мастера
    await async_session.refresh(order)
    assert order.assigned_master_id == sample_master.id


@pytest.mark.asyncio
async def test_manual_assign_wrong_status_fails(
    async_session,
    sample_city,
    sample_district,
    sample_skill,
    sample_master,
) -> None:
    """Тест отказа при попытке назначить заказ в неподходящем статусе."""
    # Создаём администратора
    staff = m.staff_users(
        id=1,
        tg_user_id=999000,
        full_name="Admin Test",
        role=m.StaffRole.GLOBAL_ADMIN,
        is_active=True,
    )
    async_session.add(staff)
    await async_session.flush()

    # Создаём заказ в статусе CLOSED (завершён)
    order = m.orders(
        city_id=sample_city.id,
        district_id=sample_district.id,
        status=m.OrderStatus.CLOSED,
        category=m.OrderCategory.ELECTRICS,
        description="Test order",
        client_name="Client Test",
        client_phone="+79991234567",
    )
    async_session.add(order)
    await async_session.commit()

    # Пытаемся назначить мастера
    success, error = await assign_manually(
        session=async_session,
        order_id=order.id,
        master_id=sample_master.id,
        staff_id=staff.id,
    )

    # Проверяем отказ
    assert success is False
    assert error is not None
    assert "статусе" in error.lower()

    # Проверяем что заказ не изменился
    await async_session.refresh(order)
    assert order.assigned_master_id is None
    assert order.status == m.OrderStatus.CLOSED


@pytest.mark.asyncio
async def test_manual_assign_nonexistent_order_fails(
    async_session,
    sample_master,
) -> None:
    """Тест отказа при попытке назначить несуществующий заказ."""
    # Создаём администратора
    staff = m.staff_users(
        id=1,
        tg_user_id=999000,
        full_name="Admin Test",
        role=m.StaffRole.GLOBAL_ADMIN,
        is_active=True,
    )
    async_session.add(staff)
    await async_session.commit()

    # Пытаемся назначить несуществующий заказ
    success, error = await assign_manually(
        session=async_session,
        order_id=99999,  # несуществующий ID
        master_id=sample_master.id,
        staff_id=staff.id,
    )

    # Проверяем отказ
    assert success is False
    assert error is not None
    assert "не найден" in error.lower()
