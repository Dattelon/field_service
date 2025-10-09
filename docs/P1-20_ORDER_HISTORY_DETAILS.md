# P1-20: Детальная история действий по заказу

**Дата:** 2025-10-09  
**Статус:** ✅ Реализовано  
**Приоритет:** P1 (Высокий)

---

## 📋 Описание проблемы

**Было:**
```
CREATED → SEARCHING (system)
SEARCHING → ASSIGNED (auto)
```

**Стало:**
```
🤖 CREATED → SEARCHING — 09.10.2025 14:23
    Кто: Система
    Причина: created_by_staff
    
⚙️ SEARCHING → ASSIGNED — 09.10.2025 14:25
    Кто: Автораспределение
    Причина: accepted_by_master
    Раунд 1, кандидатов: 3
    
👤 ASSIGNED → CANCELED — 09.10.2025 15:00
    Кто: Админ: Иванов Иван
    Причина: client_refused
    Метод: Ручное назначение
```

---

## 🎯 Что реализовано

### 1️⃣ Расширена модель `order_status_history`

**Новые поля:**
- `actor_type` (ENUM): `SYSTEM`, `ADMIN`, `MASTER`, `AUTO_DISTRIBUTION`
- `context` (JSONB): дополнительные детали действия

**Файл:** `field_service/db/models.py`

```python
class ActorType(str, enum.Enum):
    """Type of actor that changed order status."""
    SYSTEM = "SYSTEM"
    ADMIN = "ADMIN"
    MASTER = "MASTER"
    AUTO_DISTRIBUTION = "AUTO_DISTRIBUTION"

class order_status_history(Base):
    # ... существующие поля ...
    actor_type: Mapped[ActorType] = mapped_column(
        Enum(ActorType, name="actor_type"), nullable=False, index=True
    )
    context: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
```

---

### 2️⃣ Создана миграция БД

**Файл:** `alembic/versions/2025_10_09_0001_order_history_details.py`

**Что делает:**
- Создаёт ENUM `actor_type`
- Добавляет поля `actor_type` и `context` в `order_status_history`
- Заполняет `actor_type` для существующих записей на основе `changed_by_*` полей
- Создаёт индекс на `actor_type` для быстрого поиска

---

### 3️⃣ Обновлен DTO

**Файл:** `field_service/bots/admin_bot/core/dto.py`

```python
@dataclass(frozen=True)
class OrderStatusHistoryItem:
    # ... существующие поля ...
    actor_type: str
    actor_name: Optional[str] = None  # "Админ: Иванов И.", "Мастер: Петров П."
    context: Mapping[str, any] = None  # {"round": 1, "candidates_count": 3}
```

---

### 4️⃣ Обновлены все места записи истории

#### **Admin cancel order**
**Файл:** `field_service/bots/admin_bot/services/orders.py`

```python
session.add(
    m.order_status_history(
        # ...
        actor_type=m.ActorType.ADMIN,
        context={
            "staff_id": staff.id,
            "staff_name": staff.full_name,
            "cancel_reason": reason,
            "action": "manual_cancel"
        }
    )
)
```

#### **Admin assign master**
```python
session.add(
    m.order_status_history(
        # ...
        actor_type=m.ActorType.ADMIN,
        context={
            "staff_id": staff.id,
            "staff_name": staff.full_name,
            "master_id": master.id,
            "master_name": master_name,
            "action": "manual_assignment",
            "method": "admin_override"
        }
    )
)
```

#### **Master accept offer**
**Файл:** `field_service/bots/master_bot/handlers/orders.py`

```python
await session.execute(
    insert(m.order_status_history).values(
        # ...
        actor_type=m.ActorType.MASTER,
        context={
            "master_id": master.id,
            "master_name": f"{master.last_name} {master.first_name}".strip(),
            "action": "offer_accepted",
            "method": "manual_accept"
        }
    )
)
```

#### **Order creation**
**Файл:** `field_service/bots/admin_bot/services/orders.py`

```python
session.add(
    m.order_status_history(
        # ...
        actor_type=m.ActorType.ADMIN,
        context={
            "staff_id": data.created_by_staff_id,
            "staff_name": staff_info.full_name,
            "action": "order_creation",
            "initial_status": initial_status.value,
            "deferred_reason": "outside_working_hours" if deferred else None,
            "has_preferred_master": data.preferred_master_id is not None,
            "is_guarantee": data.order_type == OrderType.GUARANTEE
        }
    )
)
```

#### **Auto-wakeup from DEFERRED**
**Файл:** `field_service/services/distribution/wakeup.py`

```python
await session.execute(
    insert(m.order_status_history).values(
        # ...
        actor_type=m.ActorType.AUTO_DISTRIBUTION,
        context={
            "action": "auto_wakeup",
            "reason": "working_hours_started",
            "target_time_local": target_local,
            "system": "distribution_scheduler"
        }
    )
)
```

#### **Guarantee order creation**
**Файл:** `field_service/services/guarantee_service.py`

```python
await session.execute(
    insert(m.order_status_history).values(
        # ...
        actor_type=m.ActorType.ADMIN if created_by_staff_id else m.ActorType.SYSTEM,
        context={
            "action": "guarantee_order_creation",
            "source_order_id": source_order_id,
            "created_by_staff_id": created_by_staff_id,
            "order_type": "GUARANTEE"
        }
    )
)
```

---

### 5️⃣ Обновлены методы загрузки истории

**Файлы:**
- `field_service/bots/admin_bot/services/orders.py`:
  - `_load_status_history()` - с JOIN на staff_users и masters для получения имён
  - `list_status_history()` - аналогично

**Что загружается:**
- `actor_type`, `context`
- Имена админов/мастеров через JOIN
- Автоматическое определение `actor_name` на основе типа

---

### 6️⃣ Обновлён UI отображения истории

**Файл:** `field_service/bots/admin_bot/ui/texts/orders.py`

**Новый формат:**
```python
# Иконка актора
actor_icon = {
    "SYSTEM": "🤖",
    "ADMIN": "👤",
    "MASTER": "🔧",
    "AUTO_DISTRIBUTION": "⚙️"
}.get(item.actor_type, "")

# Основная строка с актором
if actor_name:
    lines.append(f"  {actor_icon} {change_text} — {item.changed_at_local}")
    lines.append(f"    <i>Кто: {actor_name}</i>")

# Причина
if item.reason:
    lines.append(f"    <i>Причина: {item.reason}</i>")

# Дополнительный контекст
if item.context:
    ctx = item.context
    if "candidates_count" in ctx and "round_number" in ctx:
        lines.append(f"    <i>Раунд {ctx['round_number']}, кандидатов: {ctx['candidates_count']}</i>")
    elif "method" in ctx:
        method_text = {"auto_distribution": "Автораспределение", ...}.get(ctx["method"], ctx["method"])
        lines.append(f"    <i>Метод: {method_text}</i>")
```

---

## 📊 Примеры контекста для разных сценариев

### Создание заказа админом
```json
{
    "staff_id": 1,
    "staff_name": "Иванов Иван",
    "action": "order_creation",
    "initial_status": "SEARCHING",
    "has_preferred_master": true,
    "is_guarantee": false
}
```

### Ручное назначение мастера
```json
{
    "staff_id": 1,
    "staff_name": "Иванов Иван",
    "master_id": 42,
    "master_name": "Петров Петр",
    "action": "manual_assignment",
    "method": "admin_override"
}
```

### Принятие оффера мастером
```json
{
    "master_id": 42,
    "master_name": "Петров Петр",
    "action": "offer_accepted",
    "method": "manual_accept"
}
```

### Авто-пробуждение из DEFERRED
```json
{
    "action": "auto_wakeup",
    "reason": "working_hours_started",
    "target_time_local": "10:00",
    "system": "distribution_scheduler"
}
```

### Отмена заказа админом
```json
{
    "staff_id": 1,
    "staff_name": "Иванов Иван",
    "cancel_reason": "client_refused",
    "action": "manual_cancel"
}
```

---

## 🧪 Тестирование

### Шаги для проверки:

1. **Применить миграцию:**
   ```bash
   cd field-service
   alembic upgrade head
   ```

2. **Создать новый заказ через админ-бота** → проверить что в истории появилась запись с `actor_type=ADMIN` и заполненным `context`

3. **Мастер принимает оффер** → проверить что в истории `actor_type=MASTER`

4. **Админ отменяет заказ** → проверить детали в истории

5. **Открыть карточку заказа** → убедиться что история отображается с иконками, именами и контекстом

### SQL для проверки данных:
```sql
SELECT 
    id, 
    order_id, 
    from_status, 
    to_status, 
    actor_type, 
    context,
    changed_by_staff_id,
    changed_by_master_id,
    created_at
FROM order_status_history
ORDER BY created_at DESC
LIMIT 10;
```

---

## ✅ Результат

### До:
- История показывала только переходы статусов
- Непонятно кто и почему изменил статус
- Нет деталей авторассылки

### После:
- ✅ Видно **кто** изменил (система/админ/мастер/авторассылка)
- ✅ Видно **имя** админа или мастера
- ✅ Видно **причину** изменения
- ✅ Для авторассылки: раунд, количество кандидатов
- ✅ Для ручных операций: метод, детали
- ✅ Иконки для визуального разделения типов

---

## 🚀 Дальнейшие улучшения

### Возможные расширения (опционально):

1. **Аналитика по истории:**
   - Средний time-to-assign по акторам
   - % ручных vs автоназначений
   - Частые причины отмен

2. **Фильтры в админ-боте:**
   - Показать только действия админов
   - Показать только системные изменения

3. **Экспорт истории:**
   - В CSV/XLSX для анализа
   - В timeline для визуализации

4. **Уведомления:**
   - Алерты при частых ручных переназначениях
   - Мониторинг системных ошибок

---

## 📝 Обратная совместимость

- ✅ Миграция заполняет `actor_type` для существующих записей
- ✅ Старый код продолжит работать (добавлены дефолты)
- ✅ UI показывает старые записи без контекста корректно

---

**Автор:** Claude Sonnet 4.5  
**Ревью:** Требуется  
**Тестирование:** Требуется
