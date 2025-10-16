"""
Сервис для ручного назначения мастера на заказ администратором.

Проверяет пригодность мастера через фильтры candidates.py,
отменяет активные офферы и записывает действие в историю.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import and_, func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from field_service.db import models as m
from field_service.services.candidates import select_candidates

_log = logging.getLogger(__name__)


async def assign_manually(
    session: AsyncSession,
    order_id: int,
    master_id: int,
    staff_id: int,
) -> tuple[bool, Optional[str]]:
    """
    Ручное назначение мастера на заказ администратором.
    
    Args:
        session: AsyncSession для работы с БД
        order_id: ID заказа
        master_id: ID мастера для назначения
        staff_id: ID администратора, выполняющего назначение
    
    Returns:
        tuple[bool, Optional[str]]: (success, error_message)
        - (True, None) - успешное назначение
        - (False, "error") - ошибка с текстом
    """
    _log.info(
        "manual_assign START: order=%s master=%s staff=%s",
        order_id, master_id, staff_id
    )

    # Шаг 1: Получаем информацию о заказе
    order_stmt = (
        select(
            m.orders.id,
            m.orders.status,
            m.orders.assigned_master_id,
            m.orders.city_id,
            m.orders.district_id,
            m.orders.category,
            m.orders.type,
            m.orders.version,
        )
        .where(m.orders.id == order_id)
        .with_for_update()
        .limit(1)
    )
    
    order_result = await session.execute(order_stmt)
    order_row = order_result.first()
    
    if order_row is None:
        _log.warning("manual_assign: order=%s not found", order_id)
        return False, "Заказ не найден"
    
    current_status = order_row.status
    assigned_master_id = order_row.assigned_master_id
    current_version = order_row.version or 1
    
    _log.info(
        "manual_assign: order=%s status=%s assigned_master=%s",
        order_id, current_status, assigned_master_id
    )

    # Шаг 2: Проверяем что заказ можно назначить
    if assigned_master_id is not None:
        _log.info(
            "manual_assign: order=%s already assigned to master=%s",
            order_id, assigned_master_id
        )
        return False, "Заказ уже назначен другому мастеру"
    
    assignable_statuses = {
        m.OrderStatus.SEARCHING,
        m.OrderStatus.GUARANTEE,
        m.OrderStatus.CREATED,
        m.OrderStatus.DEFERRED,
    }
    
    if current_status not in assignable_statuses:
        _log.info(
            "manual_assign: order=%s in wrong status=%s",
            order_id, current_status
        )
        return False, f"Заказ в неподходящем статусе: {current_status.value}"

    # Шаг 3: Проверяем пригодность мастера через фильтры
    order_dict = {
        "id": order_row.id,
        "city_id": order_row.city_id,
        "district_id": order_row.district_id,
        "category": order_row.category,
    }
    
    candidates = await select_candidates(
        order=order_dict,
        mode="manual_assign",
        session=session,
        limit=None,  # Получаем всех кандидатов
    )
    
    # Проверяем, что мастер входит в список кандидатов
    master_eligible = any(c.master_id == master_id for c in candidates)
    
    if not master_eligible:
        _log.warning(
            "manual_assign: master=%s not eligible for order=%s",
            master_id, order_id
        )
        return False, "Мастер не подходит для этого заказа (проверьте город, район, навыки и статус смены)"

    # Шаг 4: Атомарное назначение заказа
    update_result = await session.execute(
        update(m.orders)
        .where(
            and_(
                m.orders.id == order_id,
                m.orders.assigned_master_id.is_(None),
                m.orders.status == current_status,
                m.orders.version == current_version,
            )
        )
        .values(
            assigned_master_id=master_id,
            status=m.OrderStatus.ASSIGNED,
            updated_at=func.now(),
            version=current_version + 1,
        )
        .returning(m.orders.id)
    )
    
    if not update_result.first():
        _log.warning(
            "manual_assign: order=%s UPDATE returned 0 rows (race condition)",
            order_id
        )
        return False, "Заказ уже назначен другим администратором"

    _log.info(
        "manual_assign: order=%s successfully assigned to master=%s by staff=%s",
        order_id, master_id, staff_id
    )

    # Шаг 5: Отменяем все активные офферы для этого заказа
    await session.execute(
        update(m.offers)
        .where(
            and_(
                m.offers.order_id == order_id,
                m.offers.state.in_((m.OfferState.SENT, m.OfferState.VIEWED)),
            )
        )
        .values(
            state=m.OfferState.CANCELED,
            responded_at=func.now()
        )
    )
    
    _log.info(
        "manual_assign: canceled active offers for order=%s",
        order_id
    )

    # Шаг 6: Записываем историю статуса
    await session.execute(
        insert(m.order_status_history).values(
            order_id=order_id,
            from_status=current_status,
            to_status=m.OrderStatus.ASSIGNED,
            changed_by_staff_id=staff_id,
            reason="manual_assign",
            actor_type=m.ActorType.ADMIN,
            context={
                "master_id": master_id,
                "staff_id": staff_id,
                "action": "manual_assignment",
                "from_status": current_status.value if hasattr(current_status, 'value') else str(current_status),
            }
        )
    )

    # Шаг 7: Коммитим транзакцию
    await session.commit()
    
    _log.info(
        "manual_assign SUCCESS: order=%s assigned to master=%s by staff=%s",
        order_id, master_id, staff_id
    )
    return True, None
