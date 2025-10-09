"""
P1-10: Push-уведомления о новых офферах
Патч для distribution_scheduler.py
"""

# ============================================================================
# ИЗМЕНЕНИЕ 1: Добавить импорт notify_master
# ============================================================================
# Найти строку:
from field_service.services.push_notifications import notify_admin, NotificationEvent

# Заменить на:
from field_service.services.push_notifications import notify_admin, notify_master, NotificationEvent


# ============================================================================
# ИЗМЕНЕНИЕ 2: Добавить функцию получения данных заказа
# ============================================================================
# Вставить после функции _db_now (примерно строка 150):

async def _get_order_notification_data(
    session: AsyncSession, order_id: int
) -> dict[str, Any]:
    """Получить данные заказа для push-уведомления мастера."""
    from typing import Any
    
    result = await session.execute(
        text("""
            SELECT 
                o.id,
                c.name AS city_name,
                d.name AS district_name,
                o.timeslot_start_utc,
                o.timeslot_end_utc,
                o.category
            FROM orders o
            JOIN cities c ON c.id = o.city_id
            LEFT JOIN districts d ON d.id = o.district_id
            WHERE o.id = :order_id
        """).bindparams(order_id=order_id)
    )
    row = result.mappings().first()
    if not row:
        return {}
    
    # Форматируем timeslot
    timeslot = "не указано"
    if row["timeslot_start_utc"] and row["timeslot_end_utc"]:
        start = row["timeslot_start_utc"]
        end = row["timeslot_end_utc"]
        # Преобразуем в локальное время
        tz = time_service.resolve_timezone("Europe/Moscow")  # TODO: использовать timezone города
        start_local = start.astimezone(tz)
        end_local = end.astimezone(tz)
        timeslot = f"{start_local.strftime('%H:%M')}-{end_local.strftime('%H:%M')}"
    
    # Форматируем категорию
    category_labels = {
        "ELECTRICS": "⚡ Электрика",
        "PLUMBING": "🚰 Сантехника",
        "APPLIANCES": "🔌 Бытовая техника",
        "WINDOWS": "🪟 Окна",
        "HANDYMAN": "🔧 Мелкий ремонт",
        "ROADSIDE": "🚗 Помощь на дороге",
    }
    category = category_labels.get(row["category"], row["category"] or "не указано")
    
    return {
        "order_id": order_id,
        "city": row["city_name"] or "не указан",
        "district": row["district_name"] or "не указан",
        "timeslot": timeslot,
        "category": category,
    }


# ============================================================================
# ИЗМЕНЕНИЕ 3: Добавить вызов notify_master после создания оффера
# ============================================================================
# Найти блок (примерно строка 1095-1120):

        if ok:
            until_row = await session.execute(
                text("SELECT NOW() + make_interval(secs => :sla)").bindparams(
                    sla=cfg.sla_seconds
                )
            )
            until = until_row.scalar()
            message = f"[dist] order={order.id} decision=offer mid={first_mid} until={until.isoformat()}"
            logger.info(message)
            _dist_log(message)
            
            # ✅ STEP 4.2: Structured logging - offer sent
            log_distribution_event(
                DistributionEvent.OFFER_SENT,
                order_id=order.id,
                master_id=first_mid,
                round_number=next_round,
                sla_seconds=cfg.sla_seconds,
                expires_at=until,
            )

# Добавить ПОСЛЕ log_distribution_event:

            # ✅ P1-10: Отправить push-уведомление мастеру о новом оффере
            try:
                order_data = await _get_order_notification_data(session, order.id)
                if order_data:
                    await notify_master(
                        session,
                        master_id=first_mid,
                        event=NotificationEvent.NEW_OFFER,
                        **order_data,
                    )
                    logger.info(f"[dist] Push notification queued for master#{first_mid} about order#{order.id}")
            except Exception as e:
                logger.error(f"[dist] Failed to queue notification for master#{first_mid}: {e}")


# ============================================================================
# ИТОГО ИЗМЕНЕНИЙ
# ============================================================================
# 1. Добавлен импорт notify_master (1 строка)
# 2. Добавлена функция _get_order_notification_data (50 строк)
# 3. Добавлен вызов notify_master после создания оффера (13 строк)
#
# Всего: ~65 строк нового кода
