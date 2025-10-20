# -*- coding: utf-8 -*-
"""Фабрики для создания тестовых объектов без дублирования и FK-ошибок."""
from __future__ import annotations

from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from field_service.db import models as m


async def ensure_city(
    session: AsyncSession, 
    *, 
    name: str = "Test City", 
    tz: str = "Europe/Moscow"
) -> m.cities:
    """Создаёт или возвращает существующий город.
    
    Args:
        session: Сессия БД
        name: Название города
        tz: Таймзона города
        
    Returns:
        Объект города
    """
    q = await session.execute(select(m.cities).where(m.cities.name == name))
    city = q.scalar_one_or_none()
    if city:
        return city
    city = m.cities(name=name, timezone=tz, is_active=True)
    session.add(city)
    await session.flush()
    return city


async def ensure_skill(
    session: AsyncSession, 
    *, 
    code: str = "ELEC", 
    name: str = "Электрика"
) -> m.skills:
    """Создаёт или возвращает существующий навык.
    
    Args:
        session: Сессия БД
        code: Код навыка
        name: Название навыка
        
    Returns:
        Объект навыка
    """
    q = await session.execute(select(m.skills).where(m.skills.code == code))
    skill = q.scalar_one_or_none()
    if skill:
        return skill
    skill = m.skills(code=code, name=name, is_active=True)
    session.add(skill)
    await session.flush()
    return skill


async def ensure_district(
    session: AsyncSession,
    *,
    city: Optional[m.cities] = None,
    name: str = "Test District",
) -> m.districts:
    """Создаёт или возвращает существующий район.
    
    Args:
        session: Сессия БД
        city: Объект города (если None, создаётся тестовый)
        name: Название района
        
    Returns:
        Объект района
    """
    if city is None:
        city = await ensure_city(session)
    
    q = await session.execute(
        select(m.districts).where(
            m.districts.city_id == city.id,
            m.districts.name == name
        )
    )
    district = q.scalar_one_or_none()
    if district:
        return district
    
    district = m.districts(city_id=city.id, name=name)
    session.add(district)
    await session.flush()
    return district


async def ensure_master(
    session: AsyncSession, 
    *, 
    city: Optional[m.cities] = None, 
    phone: str = "+70000000001",
    verified: bool = True,
    is_active: bool = True,
) -> m.masters:
    """Создаёт или возвращает существующего мастера.
    
    Args:
        session: Сессия БД
        city: Объект города (если None, создаётся тестовый)
        phone: Телефон мастера
        verified: Статус верификации
        is_active: Активность мастера
        
    Returns:
        Объект мастера
    """
    if city is None:
        city = await ensure_city(session)
    
    q = await session.execute(select(m.masters).where(m.masters.phone == phone))
    master = q.scalar_one_or_none()
    if master:
        return master
    
    master = m.masters(
        city_id=city.id, 
        phone=phone, 
        full_name="Тестовый Мастер", 
        is_active=is_active, 
        verified=verified
    )
    session.add(master)
    await session.flush()
    return master


async def create_order(
    session: AsyncSession,
    *,
    city: Optional[m.cities] = None,
    district: Optional[m.districts] = None,
    category: Optional[str] = None,
    order_type: Optional[str] = None,
    status: str = "SEARCHING",
) -> m.orders:
    """Создаёт новый заказ с валидными FK.
    
    Args:
        session: Сессия БД
        city: Объект города (если None, создаётся тестовый)
        district: Объект района (опционально)
        category: Категория заказа
        order_type: Тип заказа
        status: Статус заказа
        
    Returns:
        Созданный объект заказа
    """
    if city is None:
        city = await ensure_city(session)
    
    order = m.orders(
        city_id=city.id,
        district_id=district.id if district else None,
        status=status,
        category=category,
        type=order_type,
        description="Тестовый заказ",
    )
    session.add(order)
    await session.flush()
    return order


async def create_commission(
    session: AsyncSession,
    *,
    order: Optional[m.orders] = None,
    master: Optional[m.masters] = None,
    amount: float = 1000.0,
    status: str = "WAIT_PAY",
) -> m.commissions:
    """Создаёт новую комиссию с валидными FK.
    
    Args:
        session: Сессия БД
        order: Объект заказа (если None, создаётся тестовый)
        master: Объект мастера (если None, создаётся тестовый)
        amount: Сумма комиссии
        status: Статус комиссии
        
    Returns:
        Созданный объект комиссии
    """
    if order is None:
        order = await create_order(session)
    if master is None:
        master = await ensure_master(session)
    
    from datetime import datetime, timedelta, timezone
    
    commission = m.commissions(
        order_id=order.id,
        master_id=master.id,
        amount=amount,
        status=status,
        rate=0.5,
        deadline_at=datetime.now(timezone.utc) + timedelta(hours=3),
    )
    session.add(commission)
    await session.flush()
    return commission
