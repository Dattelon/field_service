"""
Модуль проверки подходящих мастеров для заказа.

Использует те же критерии что и автораспределение:
- Верификация (verified=True)
- Активность (is_active=True, is_blocked=False)
- Смена (is_on_shift=True)
- Перерыв (break_until IS NULL OR <= NOW())
- Совпадение города
- Совпадение района (если указан)
- Наличие навыка категории
- Лимит активных заказов
- Отсутствие дублирующих офферов
"""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from field_service.services.skills_map import get_skill_code

logger = logging.getLogger(__name__)

DEFAULT_MAX_ACTIVE_LIMIT = 5


async def eligible_masters_for_order(
    session: AsyncSession,
    order_id: int,
    limit: int = 100,
) -> list[dict]:
    """
    Получить список подходящих мастеров для заказа.
    
    Использует те же фильтры что и автораспределение:
    - Верификация, активность, блокировка
    - Смена и перерыв
    - Совпадение города
    - Совпадение района (если у заказа указан район)
    - Наличие навыка категории
    - Лимит активных заказов не превышен
    - Нет дублирующих офферов для этого заказа
    
    Args:
        session: Асинхронная сессия БД
        order_id: ID заказа
        limit: Максимальное количество мастеров в результате
        
    Returns:
        Список словарей с данными мастеров:
        - master_id: ID мастера
        - master_name: ФИО мастера
        - has_vehicle: Есть ли авто
        - is_on_shift: На смене ли
        - rating: Средний рейтинг
        - active_orders: Количество активных заказов
        - max_limit: Лимит активных заказов для мастера
        
    Raises:
        ValueError: Если заказ не найден или у него отсутствуют критичные данные
    """
    # Получаем данные заказа
    order_result = await session.execute(
        text("""
            SELECT 
                o.id,
                o.city_id,
                o.district_id,
                o.category,
                o.no_district
            FROM orders o
            WHERE o.id = :order_id
        """).bindparams(order_id=order_id)
    )
    
    order_row = order_result.mappings().first()
    if not order_row:
        raise ValueError(f"Order {order_id} not found")
    
    city_id = order_row["city_id"]
    district_id = order_row["district_id"]
    category = order_row["category"]
    no_district = order_row["no_district"]
    
    # Проверка критичных данных
    if not city_id:
        raise ValueError(f"Order {order_id} has no city_id")
    
    # Если у заказа явно указано no_district, возвращаем пустой список
    # (такие заказы должны идти на ручное распределение)
    if no_district:
        logger.info(f"[eligibility] order={order_id} has no_district=true, skipping auto-distribution")
        return []
    
    # Получаем код навыка для категории
    skill_code = get_skill_code(category)
    if not skill_code:
        logger.warning(f"[eligibility] order={order_id} has invalid/missing category={category}")
        return []
    
    # SQL-запрос идентичен тому что в _candidates() из distribution_scheduler.py
    # но без ORDER BY (так как это функция проверки, а не выбора)
    # и с добавлением полей для отображения
    
    if district_id is None:
        # Поиск по всему городу (без привязки к району)
        sql = text("""
            WITH lim AS (
              SELECT m.id AS master_id,
                     COALESCE(
                         m.max_active_orders_override,
                         (SELECT CAST(value AS INT) FROM settings WHERE key='max_active_orders' LIMIT 1),
                         :fallback
                     ) AS max_limit,
                     (SELECT COUNT(*) FROM orders o2
                       WHERE o2.assigned_master_id = m.id
                         AND o2.status IN ('ASSIGNED','EN_ROUTE','WORKING','PAYMENT')
                     ) AS active_cnt
              FROM masters m
            )
            SELECT m.id AS master_id,
                   CONCAT(m.last_name, ' ', m.first_name, COALESCE(' ' || m.patronymic, '')) AS master_name,
                   m.has_vehicle,
                   m.is_on_shift,
                   COALESCE(m.rating, 0)::numeric(3,1) AS rating,
                   lim.active_cnt AS active_orders,
                   lim.max_limit
              FROM masters m
              LEFT JOIN master_districts md ON md.master_id = m.id
              JOIN master_skills ms ON ms.master_id = m.id
              JOIN skills s ON s.id = ms.skill_id AND s.code = :skill_code AND s.is_active = TRUE
              JOIN lim ON lim.master_id = m.id
             WHERE m.city_id = :cid
               AND m.is_active = TRUE
               AND m.is_blocked = FALSE
               AND m.verified = TRUE
               AND m.is_on_shift = TRUE
               AND (m.break_until IS NULL OR m.break_until <= NOW())
               AND lim.active_cnt < lim.max_limit
               AND NOT EXISTS (SELECT 1 FROM offers o WHERE o.order_id = :oid AND o.master_id = m.id)
             LIMIT :limit
        """)
        
        result = await session.execute(
            sql.bindparams(
                oid=order_id,
                cid=city_id,
                skill_code=skill_code,
                fallback=DEFAULT_MAX_ACTIVE_LIMIT,
                limit=limit,
            )
        )
    else:
        # Поиск по конкретному району
        sql = text("""
            WITH lim AS (
              SELECT m.id AS master_id,
                     COALESCE(
                         m.max_active_orders_override,
                         (SELECT CAST(value AS INT) FROM settings WHERE key='max_active_orders' LIMIT 1),
                         :fallback
                     ) AS max_limit,
                     (SELECT COUNT(*) FROM orders o2
                       WHERE o2.assigned_master_id = m.id
                         AND o2.status IN ('ASSIGNED','EN_ROUTE','WORKING','PAYMENT')
                     ) AS active_cnt
              FROM masters m
            )
            SELECT m.id AS master_id,
                   CONCAT(m.last_name, ' ', m.first_name, COALESCE(' ' || m.patronymic, '')) AS master_name,
                   m.has_vehicle,
                   m.is_on_shift,
                   COALESCE(m.rating, 0)::numeric(3,1) AS rating,
                   lim.active_cnt AS active_orders,
                   lim.max_limit
              FROM masters m
              JOIN master_districts md ON md.master_id = m.id AND md.district_id = :did
              JOIN master_skills ms ON ms.master_id = m.id
              JOIN skills s ON s.id = ms.skill_id AND s.code = :skill_code AND s.is_active = TRUE
              JOIN lim ON lim.master_id = m.id
             WHERE m.city_id = :cid
               AND m.is_active = TRUE
               AND m.is_blocked = FALSE
               AND m.verified = TRUE
               AND m.is_on_shift = TRUE
               AND (m.break_until IS NULL OR m.break_until <= NOW())
               AND lim.active_cnt < lim.max_limit
               AND NOT EXISTS (SELECT 1 FROM offers o WHERE o.order_id = :oid AND o.master_id = m.id)
             LIMIT :limit
        """)
        
        result = await session.execute(
            sql.bindparams(
                oid=order_id,
                cid=city_id,
                did=district_id,
                skill_code=skill_code,
                fallback=DEFAULT_MAX_ACTIVE_LIMIT,
                limit=limit,
            )
        )
    
    masters = []
    for row in result.mappings().all():
        masters.append({
            "master_id": int(row["master_id"]),
            "master_name": str(row["master_name"]).strip(),
            "has_vehicle": bool(row["has_vehicle"]),
            "is_on_shift": bool(row["is_on_shift"]),
            "rating": float(row["rating"]),
            "active_orders": int(row["active_orders"]),
            "max_limit": int(row["max_limit"]),
        })
    
    logger.info(
        f"[eligibility] order={order_id} city={city_id} district={district_id} "
        f"category={category} found {len(masters)} eligible masters"
    )
    
    return masters
