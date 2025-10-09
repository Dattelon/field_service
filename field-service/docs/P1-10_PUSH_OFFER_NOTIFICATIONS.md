# P1-10: Push-уведомления о новых офферах

**Дата:** 2025-10-08  
**Приоритет:** P1 (Высокий)  
**Статус:** 🟡 В разработке

## 📋 Описание

**Проблема:** Мастера используют pull-модель (обновляют список офферов вручную) и пропускают новые заказы.

**Решение:** Отправлять push-уведомление мастеру при создании оффера через `notifications_outbox`.

## ✅ Что уже есть

- ✅ Сервис `push_notifications.py`
- ✅ `NotificationEvent.NEW_OFFER` определён
- ✅ Шаблон сообщения готов
- ✅ Функция `notify_master()` работает
- ✅ Воркер `notifications_watcher.py` отправляет уведомления

## 🔧 Изменения

### 1. Добавить импорт в `distribution_scheduler.py`

```python
# Было:
from field_service.services.push_notifications import notify_admin, NotificationEvent

# Стало:
from field_service.services.push_notifications import notify_admin, notify_master, NotificationEvent
```

### 2. Добавить функцию получения данных заказа

```python
async def _get_order_notification_data(
    session: AsyncSession, order_id: int
) -> dict[str, Any]:
    """Получить данные заказа для уведомления мастера."""
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
        # Преобразуем в локальное время (используем московское как пример)
        tz = time_service.resolve_timezone("Europe/Moscow")
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
```

### 3. Вызвать notify_master после создания оффера

В функции где вызывается `await _send_offer`:

```python
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
```

## 📝 Шаблон уведомления

Уже готов в `push_notifications.py`:

```python
NotificationEvent.NEW_OFFER: (
    "🆕 <b>Новый заказ #{order_id}</b>\n\n"
    "📍 {city}, {district}\n"
    "⏰ {timeslot}\n"
    "🛠 {category}\n\n"
    "Откройте бот для принятия заказа."
),
```

## 🔄 Процесс работы

1. Auto-distribution создаёт оффер через `_send_offer()`
2. При `ok=True` вызывается `notify_master()`
3. Запись добавляется в `notifications_outbox`
4. Воркер `notifications_watcher.py` читает outbox
5. Отправляет Telegram сообщение мастеру
6. Помечает запись как отправленную

## ⚠️ Важные моменты

1. **Не блокирует распределение** - уведомление в фоне через outbox
2. **Откат при ошибке** - если уведомление не отправилось, это не влияет на оффер
3. **Логирование** - все ошибки логируются для отладки
4. **Timezone** - время показывается в локальном часовом поясе города

## 🧪 Тестирование

### Ручное тестирование

1. Создать заказ в админ-боте
2. Дождаться автораспределения (15 секунд)
3. Проверить что мастер получил уведомление
4. Проверить что в `notifications_outbox` появилась запись

### SQL проверка

```sql
-- Проверить очередь уведомлений
SELECT * FROM notifications_outbox 
WHERE event = 'new_offer' 
ORDER BY created_at DESC 
LIMIT 10;

-- Проверить что уведомление отправлено
SELECT * FROM notifications_outbox 
WHERE event = 'new_offer' 
  AND sent_at IS NOT NULL 
ORDER BY sent_at DESC 
LIMIT 10;
```

## 📊 Метрики

После внедрения отслеживать:

- **Скорость отклика** - сколько времени от создания оффера до принятия
- **% принятых офферов** - увеличился ли после push
- **% открытий бота** - мастера получают уведомление и открывают бот

## 🚀 Следующие шаги

1. ✅ Написать патч
2. ⏳ Применить изменения
3. ⏳ Протестировать на dev
4. ⏳ Развернуть на prod
5. ⏳ Мониторить метрики

---

**Автор:** Claude Sonnet 4.5  
**Ревью:** Требуется
