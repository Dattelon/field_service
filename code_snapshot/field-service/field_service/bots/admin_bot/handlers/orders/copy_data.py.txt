"""
Handler для быстрого копирования данных заказа (P1-19).

Обрабатывает callback'и вида: adm:copy:type:order_id
- type: cph (client_phone), mph (master_phone), addr (address)
- order_id: ID заказа

Данные загружаются из БД и отправляются через alert для быстрого копирования.
"""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from field_service.bots.common import safe_answer_callback
from field_service.bots.common.copy_utils import format_copy_message
from field_service.db import models as m
from field_service.db.models import StaffRole

from ...core.dto import StaffUser
from ...core.filters import StaffRoleFilter

copy_router = Router(name="admin_copy_data")
_log = logging.getLogger("admin_bot.copy_data")

# Роли с доступом к копированию данных
_ALLOWED_ROLES = {StaffRole.GLOBAL_ADMIN, StaffRole.CITY_ADMIN, StaffRole.LOGIST}


@copy_router.callback_query(
    StaffRoleFilter(_ALLOWED_ROLES),
    F.data.regexp(r"^adm:copy:(cph|mph|addr):(\d+)$")
)
async def copy_data_handler(
    callback: CallbackQuery,
    session: AsyncSession,
    staff: StaffUser,
) -> None:
    """
    Обрабатывает копирование данных заказа (телефоны, адрес).
    
    Callback format: adm:copy:type:order_id
    - type: cph (client_phone), mph (master_phone), addr (address)
    - order_id: ID заказа
    """
    parts = callback.data.split(":")
    if len(parts) != 4:
        await safe_answer_callback(callback, "❌ Ошибка формата", show_alert=True)
        return
    
    data_type = parts[2]
    try:
        order_id = int(parts[3])
    except ValueError:
        await safe_answer_callback(callback, "❌ Неверный ID заказа", show_alert=True)
        return
    
    # Загружаем заказ с данными мастера
    stmt = (
        select(
            m.orders.id,
            m.orders.client_phone,
            m.orders.house,
            m.cities.name.label("city"),
            m.districts.name.label("district"),
            m.streets.name.label("street"),
            m.masters.phone.label("master_phone"),
        )
        .join(m.cities, m.cities.id == m.orders.city_id)
        .outerjoin(m.districts, m.districts.id == m.orders.district_id)
        .outerjoin(m.streets, m.streets.id == m.orders.street_id)
        .outerjoin(m.masters, m.masters.id == m.orders.assigned_master_id)
        .where(m.orders.id == order_id)
    )
    
    row = (await session.execute(stmt)).first()
    
    if not row:
        await safe_answer_callback(callback, "❌ Заказ не найден", show_alert=True)
        return
    
    # Формируем данные для копирования
    if data_type == "cph":
        # Телефон клиента
        if not row.client_phone:
            await safe_answer_callback(callback, "❌ Телефон клиента не указан", show_alert=True)
            return
        data = row.client_phone
        
    elif data_type == "mph":
        # Телефон мастера
        if not row.master_phone:
            await safe_answer_callback(callback, "❌ Мастер не назначен или телефон не указан", show_alert=True)
            return
        data = row.master_phone
        
    elif data_type == "addr":
        # Адрес
        address_parts = [row.city]
        if row.district:
            address_parts.append(row.district)
        if row.street:
            address_parts.append(row.street)
        if row.house:
            address_parts.append(str(row.house))
        data = ", ".join(address_parts)
        
    else:
        await safe_answer_callback(callback, "❌ Неизвестный тип данных", show_alert=True)
        return
    
    # Отправляем данные через alert для быстрого копирования
    # Telegram позволяет копировать текст из alert
    await safe_answer_callback(callback, data, show_alert=True)
    
    _log.info(
        "copy_data: staff_id=%s order_id=%s type=%s",
        staff.staff_id,
        order_id,
        data_type,
    )
