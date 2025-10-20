"""
Unit-тесты для модуля eligibility.

Проверяет что eligible_masters_for_order корректно фильтрует мастеров
по тем же критериям что и автораспределение.
"""

import pytest
from datetime import datetime, timedelta, timezone

from field_service.db import models as m
from field_service.services.eligibility import eligible_masters_for_order


@pytest.mark.asyncio
async def test_eligible_masters_basic(session):
    """Тест: базовая проверка - находим подходящего мастера."""
    # Создаём город
    city = m.cities(name="Москва", timezone="Europe/Moscow")
    session.add(city)
    await session.flush()
    
    # Создаём район
    district = m.districts(name="ЮЗАО", city_id=city.id)
    session.add(district)
    await session.flush()
    
    # Создаём навык
    skill = m.skills(code="ELEC", name="Электрика", is_active=True)
    session.add(skill)
    await session.flush()
    
    # Создаём подходящего мастера
    master = m.masters(
        tg_user_id=12345,
        first_name="Иван",
        last_name="Иванов",
        patronymic="Иванович",
        phone="+79991234567",
        city_id=city.id,
        verified=True,
        is_active=True,
        is_blocked=False,
        is_on_shift=True,
        has_vehicle=True,
        rating=4.5,
    )
    session.add(master)
    await session.flush()
    
    # Привязываем навык
    master_skill = m.master_skills(master_id=master.id, skill_id=skill.id)
    session.add(master_skill)
    
    # Привязываем район
    master_district = m.master_districts(master_id=master.id, district_id=district.id)
    session.add(master_district)
    await session.flush()
    
    # Создаём заказ
    order = m.orders(
        city_id=city.id,
        district_id=district.id,
        category="ELECTRICS",
        status=m.OrderStatus.SEARCHING,
        no_district=False,
    )
    session.add(order)
    await session.flush()
    
    # Проверяем
    masters = await eligible_masters_for_order(session, order.id)
    
    assert len(masters) == 1
    assert masters[0]["master_id"] == master.id
    assert masters[0]["master_name"] == "Иванов Иван Иванович"
    assert masters[0]["has_vehicle"] is True
    assert masters[0]["is_on_shift"] is True
    assert masters[0]["rating"] == 4.5
    assert masters[0]["active_orders"] == 0


@pytest.mark.asyncio
async def test_eligible_masters_no_skill(session):
    """Тест: мастер без нужного навыка не попадает в список."""
    # Создаём город
    city = m.cities(name="Москва", timezone="Europe/Moscow")
    session.add(city)
    await session.flush()
    
    # Создаём район
    district = m.districts(name="ЮЗАО", city_id=city.id)
    session.add(district)
    await session.flush()
    
    # Создаём навык PLUMB (сантехника)
    skill_plumb = m.skills(code="PLUMB", name="Сантехника", is_active=True)
    session.add(skill_plumb)
    await session.flush()
    
    # Создаём мастера с навыком PLUMB
    master = m.masters(
        tg_user_id=12345,
        first_name="Пётр",
        last_name="Петров",
        phone="+79991234567",
        city_id=city.id,
        verified=True,
        is_active=True,
        is_blocked=False,
        is_on_shift=True,
    )
    session.add(master)
    await session.flush()
    
    # Привязываем навык сантехника
    master_skill = m.master_skills(master_id=master.id, skill_id=skill_plumb.id)
    session.add(master_skill)
    
    # Привязываем район
    master_district = m.master_districts(master_id=master.id, district_id=district.id)
    session.add(master_district)
    await session.flush()
    
    # Создаём заказ с категорией ELECTRICS (требуется навык ELEC)
    order = m.orders(
        city_id=city.id,
        district_id=district.id,
        category="ELECTRICS",  # Нужен ELEC, а у мастера только PLUMB
        status=m.OrderStatus.SEARCHING,
        no_district=False,
    )
    session.add(order)
    await session.flush()
    
    # Проверяем - мастер не подходит
    masters = await eligible_masters_for_order(session, order.id)
    assert len(masters) == 0


@pytest.mark.asyncio
async def test_eligible_masters_not_on_shift(session):
    """Тест: мастер вне смены не попадает в список."""
    # Создаём город
    city = m.cities(name="Москва", timezone="Europe/Moscow")
    session.add(city)
    await session.flush()
    
    # Создаём район
    district = m.districts(name="ЮЗАО", city_id=city.id)
    session.add(district)
    await session.flush()
    
    # Создаём навык
    skill = m.skills(code="ELEC", name="Электрика", is_active=True)
    session.add(skill)
    await session.flush()
    
    # Создаём мастера вне смены
    master = m.masters(
        tg_user_id=12345,
        first_name="Сергей",
        last_name="Сергеев",
        phone="+79991234567",
        city_id=city.id,
        verified=True,
        is_active=True,
        is_blocked=False,
        is_on_shift=False,  # НЕ на смене
    )
    session.add(master)
    await session.flush()
    
    # Привязываем навык
    master_skill = m.master_skills(master_id=master.id, skill_id=skill.id)
    session.add(master_skill)
    
    # Привязываем район
    master_district = m.master_districts(master_id=master.id, district_id=district.id)
    session.add(master_district)
    await session.flush()
    
    # Создаём заказ
    order = m.orders(
        city_id=city.id,
        district_id=district.id,
        category="ELECTRICS",
        status=m.OrderStatus.SEARCHING,
        no_district=False,
    )
    session.add(order)
    await session.flush()
    
    # Проверяем - мастер не подходит
    masters = await eligible_masters_for_order(session, order.id)
    assert len(masters) == 0


@pytest.mark.asyncio
async def test_eligible_masters_blocked(session):
    """Тест: заблокированный мастер не попадает в список."""
    # Создаём город
    city = m.cities(name="Москва", timezone="Europe/Moscow")
    session.add(city)
    await session.flush()
    
    # Создаём район
    district = m.districts(name="ЮЗАО", city_id=city.id)
    session.add(district)
    await session.flush()
    
    # Создаём навык
    skill = m.skills(code="ELEC", name="Электрика", is_active=True)
    session.add(skill)
    await session.flush()
    
    # Создаём заблокированного мастера
    master = m.masters(
        tg_user_id=12345,
        first_name="Алексей",
        last_name="Алексеев",
        phone="+79991234567",
        city_id=city.id,
        verified=True,
        is_active=True,
        is_blocked=True,  # Заблокирован
        is_on_shift=True,
    )
    session.add(master)
    await session.flush()
    
    # Привязываем навык
    master_skill = m.master_skills(master_id=master.id, skill_id=skill.id)
    session.add(master_skill)
    
    # Привязываем район
    master_district = m.master_districts(master_id=master.id, district_id=district.id)
    session.add(master_district)
    await session.flush()
    
    # Создаём заказ
    order = m.orders(
        city_id=city.id,
        district_id=district.id,
        category="ELECTRICS",
        status=m.OrderStatus.SEARCHING,
        no_district=False,
    )
    session.add(order)
    await session.flush()
    
    # Проверяем - мастер не подходит
    masters = await eligible_masters_for_order(session, order.id)
    assert len(masters) == 0


@pytest.mark.asyncio
async def test_eligible_masters_on_break(session):
    """Тест: мастер на перерыве не попадает в список."""
    # Создаём город
    city = m.cities(name="Москва", timezone="Europe/Moscow")
    session.add(city)
    await session.flush()
    
    # Создаём район
    district = m.districts(name="ЮЗАО", city_id=city.id)
    session.add(district)
    await session.flush()
    
    # Создаём навык
    skill = m.skills(code="ELEC", name="Электрика", is_active=True)
    session.add(skill)
    await session.flush()
    
    # Создаём мастера на перерыве
    future_time = datetime.now(timezone.utc) + timedelta(hours=1)
    master = m.masters(
        tg_user_id=12345,
        first_name="Дмитрий",
        last_name="Дмитриев",
        phone="+79991234567",
        city_id=city.id,
        verified=True,
        is_active=True,
        is_blocked=False,
        is_on_shift=True,
        break_until=future_time,  # На перерыве
    )
    session.add(master)
    await session.flush()
    
    # Привязываем навык
    master_skill = m.master_skills(master_id=master.id, skill_id=skill.id)
    session.add(master_skill)
    
    # Привязываем район
    master_district = m.master_districts(master_id=master.id, district_id=district.id)
    session.add(master_district)
    await session.flush()
    
    # Создаём заказ
    order = m.orders(
        city_id=city.id,
        district_id=district.id,
        category="ELECTRICS",
        status=m.OrderStatus.SEARCHING,
        no_district=False,
    )
    session.add(order)
    await session.flush()
    
    # Проверяем - мастер не подходит
    masters = await eligible_masters_for_order(session, order.id)
    assert len(masters) == 0


@pytest.mark.asyncio
async def test_eligible_masters_active_limit_exceeded(session):
    """Тест: мастер с превышенным лимитом активных заказов не попадает в список."""
    # Создаём город
    city = m.cities(name="Москва", timezone="Europe/Moscow")
    session.add(city)
    await session.flush()
    
    # Создаём район
    district = m.districts(name="ЮЗАО", city_id=city.id)
    session.add(district)
    await session.flush()
    
    # Создаём навык
    skill = m.skills(code="ELEC", name="Электрика", is_active=True)
    session.add(skill)
    await session.flush()
    
    # Создаём мастера
    master = m.masters(
        tg_user_id=12345,
        first_name="Владимир",
        last_name="Владимиров",
        phone="+79991234567",
        city_id=city.id,
        verified=True,
        is_active=True,
        is_blocked=False,
        is_on_shift=True,
        max_active_orders_override=2,  # Лимит 2 заказа
    )
    session.add(master)
    await session.flush()
    
    # Привязываем навык
    master_skill = m.master_skills(master_id=master.id, skill_id=skill.id)
    session.add(master_skill)
    
    # Привязываем район
    master_district = m.master_districts(master_id=master.id, district_id=district.id)
    session.add(master_district)
    await session.flush()
    
    # Создаём 2 активных заказа (лимит достигнут)
    for i in range(2):
        active_order = m.orders(
            city_id=city.id,
            district_id=district.id,
            category="ELECTRICS",
            status=m.OrderStatus.ASSIGNED,
            assigned_master_id=master.id,
        )
        session.add(active_order)
    await session.flush()
    
    # Создаём новый заказ
    order = m.orders(
        city_id=city.id,
        district_id=district.id,
        category="ELECTRICS",
        status=m.OrderStatus.SEARCHING,
        no_district=False,
    )
    session.add(order)
    await session.flush()
    
    # Проверяем - мастер не подходит (лимит превышен)
    masters = await eligible_masters_for_order(session, order.id)
    assert len(masters) == 0


@pytest.mark.asyncio
async def test_eligible_masters_no_district_flag(session):
    """Тест: заказ с флагом no_district=True возвращает пустой список."""
    # Создаём город
    city = m.cities(name="Москва", timezone="Europe/Moscow")
    session.add(city)
    await session.flush()
    
    # Создаём заказ с флагом no_district
    order = m.orders(
        city_id=city.id,
        district_id=None,
        category="ELECTRICS",
        status=m.OrderStatus.SEARCHING,
        no_district=True,  # Явный флаг - идти на ручное распределение
    )
    session.add(order)
    await session.flush()
    
    # Проверяем - список пуст
    masters = await eligible_masters_for_order(session, order.id)
    assert len(masters) == 0


@pytest.mark.asyncio
async def test_eligible_masters_order_not_found(session):
    """Тест: несуществующий заказ вызывает ValueError."""
    with pytest.raises(ValueError, match="Order 99999 not found"):
        await eligible_masters_for_order(session, 99999)


@pytest.mark.asyncio
async def test_eligible_masters_citywide_search(session):
    """Тест: поиск по всему городу если у заказа нет района."""
    # Создаём город
    city = m.cities(name="Санкт-Петербург", timezone="Europe/Moscow")
    session.add(city)
    await session.flush()
    
    # Создаём район (но заказ будет без района)
    district = m.districts(name="Центральный", city_id=city.id)
    session.add(district)
    await session.flush()
    
    # Создаём навык
    skill = m.skills(code="HANDY", name="Универсал", is_active=True)
    session.add(skill)
    await session.flush()
    
    # Создаём мастера привязанного к району
    master = m.masters(
        tg_user_id=54321,
        first_name="Михаил",
        last_name="Михайлов",
        phone="+79991234567",
        city_id=city.id,
        verified=True,
        is_active=True,
        is_blocked=False,
        is_on_shift=True,
    )
    session.add(master)
    await session.flush()
    
    # Привязываем навык
    master_skill = m.master_skills(master_id=master.id, skill_id=skill.id)
    session.add(master_skill)
    
    # Привязываем район
    master_district = m.master_districts(master_id=master.id, district_id=district.id)
    session.add(master_district)
    await session.flush()
    
    # Создаём заказ БЕЗ района (поиск по городу)
    order = m.orders(
        city_id=city.id,
        district_id=None,  # Нет района
        category="HANDYMAN",
        status=m.OrderStatus.SEARCHING,
        no_district=False,  # НО флаг no_district=False
    )
    session.add(order)
    await session.flush()
    
    # Проверяем - мастер должен найтись (citywide search)
    masters = await eligible_masters_for_order(session, order.id)
    assert len(masters) == 1
    assert masters[0]["master_id"] == master.id


@pytest.mark.asyncio
async def test_eligible_masters_multiple_candidates(session):
    """Тест: несколько подходящих мастеров."""
    # Создаём город
    city = m.cities(name="Москва", timezone="Europe/Moscow")
    session.add(city)
    await session.flush()
    
    # Создаём район
    district = m.districts(name="ЦАО", city_id=city.id)
    session.add(district)
    await session.flush()
    
    # Создаём навык
    skill = m.skills(code="PLUMB", name="Сантехника", is_active=True)
    session.add(skill)
    await session.flush()
    
    # Создаём 3 подходящих мастера
    masters_created = []
    for i in range(3):
        master = m.masters(
            tg_user_id=10000 + i,
            first_name=f"Мастер{i}",
            last_name=f"Фамилия{i}",
            phone=f"+7999123456{i}",
            city_id=city.id,
            verified=True,
            is_active=True,
            is_blocked=False,
            is_on_shift=True,
            rating=4.0 + i * 0.1,
        )
        session.add(master)
        await session.flush()
        
        # Привязываем навык
        master_skill = m.master_skills(master_id=master.id, skill_id=skill.id)
        session.add(master_skill)
        
        # Привязываем район
        master_district = m.master_districts(master_id=master.id, district_id=district.id)
        session.add(master_district)
        
        masters_created.append(master)
    
    await session.flush()
    
    # Создаём заказ
    order = m.orders(
        city_id=city.id,
        district_id=district.id,
        category="PLUMBING",
        status=m.OrderStatus.SEARCHING,
        no_district=False,
    )
    session.add(order)
    await session.flush()
    
    # Проверяем - все 3 мастера подходят
    masters = await eligible_masters_for_order(session, order.id)
    assert len(masters) == 3
    
    master_ids = {m["master_id"] for m in masters}
    expected_ids = {m.id for m in masters_created}
    assert master_ids == expected_ids
