# BUGFIX: Foreign Key Violation при одобрении комиссий

**Дата:** 2025-10-03  
**Приоритет:** КРИТИЧЕСКИЙ  
**Статус:** ИСПРАВЛЕНО

## Проблема

При нажатии кнопки "Подтвердить" на этапе подтверждения оплаты комиссии возникала ошибка:

```
asyncpg.exceptions.ForeignKeyViolationError: insert or update on table "order_status_history" 
violates foreign key constraint "fk_order_status_history__changed_by_staff_id__staff_users"
DETAIL: Key (changed_by_staff_id)=(0) is not present in table "staff_users".
```

## Причина

В middleware для superuser'ов создавался фейковый объект `StaffUser` с `id=0`, который не существовал в базе данных:

```python
staff = resolved or StaffUser(
    id=0,  # <-- ПРОБЛЕМА: не существует в БД
    tg_id=tg_id,
    role=StaffRole.GLOBAL_ADMIN,
    ...
)
```

Этот `staff.id=0` затем передавался в метод `finance_service.approve()` и попадал в `INSERT INTO order_status_history`, что вызывало нарушение внешнего ключа.

## Решение

### 1. Исправление middleware (`middlewares.py`)

**ДО:**
```python
if tg_id in self._superusers:
    # Try to resolve real staff from DB to keep FK references valid
    if not isinstance(staff, StaffUser):
        try:
            resolved = await self._staff_service.get_by_tg_id(tg_id)
        except Exception:
            resolved = None
        staff = resolved or StaffUser(
            id=0,  # ❌ Фейковый ID
            tg_id=tg_id,
            role=StaffRole.GLOBAL_ADMIN,
            is_active=True,
            city_ids=frozenset(),
            full_name="Superuser",
            phone="",
        )
    data["staff"] = staff
    return await handler(event, data)
```

**ПОСЛЕ:**
```python
if tg_id in self._superusers:
    # CR-2025-10-03-FIX: Always load from DB to get valid staff.id for FK references
    if not isinstance(staff, StaffUser):
        try:
            resolved = await self._staff_service.get_by_tg_id(tg_id)
        except Exception:
            resolved = None
        
        # If superuser not in DB, deny access - they must be properly registered
        if not resolved:
            await _notify_access_required(
                event, 
                "⛔ Суперпользователь не зарегистрирован в системе. Обратитесь к администратору."
            )
            return None
        
        staff = resolved  # ✅ Только реальные ID из БД
    data["staff"] = staff
    return await handler(event, data)
```

### 2. Защитная валидация в обработчиках (`handlers_finance.py`)

Добавлена проверка `staff.id` в трёх критических обработчиках:

1. **`cb_finance_approve_instant`** (быстрое одобрение)
2. **`finance_approve_amount`** (одобрение с кастомной суммой)
3. **`finance_reject_reason`** (отклонение комиссии)

```python
# CR-2025-10-03-FIX: Validate staff.id before database operations
if not staff or not staff.id or staff.id <= 0:
    await _safe_answer(cq, "❌ Ошибка: некорректный ID персонала", show_alert=True)
    return
```

## Изменённые файлы

1. `field_service/bots/admin_bot/middlewares.py` - исправление логики superuser
2. `field_service/bots/admin_bot/handlers_finance.py` - добавлена валидация (3 места)

## Как работает исправление

1. **При входе superuser'а:**
   - Middleware загружает запись из БД (`get_by_tg_id`)
   - Если записи нет → отказ в доступе с сообщением
   - Если есть → использует реальный `staff.id` из БД

2. **При одобрении комиссии:**
   - Проверка `staff.id > 0` перед вызовом БД
   - Если проверка не прошла → ошибка с понятным сообщением
   - Если прошла → вызов `approve()` с валидным ID

## Требования для superuser'ов

Теперь все superuser'ы ДОЛЖНЫ:
1. Быть зарегистрированы в таблице `staff_users`
2. Иметь валидный `tg_user_id` = их Telegram ID

Для регистрации используйте:
```sql
INSERT INTO staff_users (tg_user_id, role, is_active, full_name, phone)
VALUES (123456789, 'ADMIN', true, 'Admin Name', '+71234567890');
```

Или через `DBStaffService.seed_global_admins()`.

## Тестирование

### Сценарий 1: Superuser зарегистрирован
- ✅ Вход разрешён
- ✅ Одобрение комиссий работает
- ✅ История в БД сохраняется с правильным `changed_by_staff_id`

### Сценарий 2: Superuser НЕ зарегистрирован
- ✅ Вход заблокирован
- ✅ Сообщение: "Суперпользователь не зарегистрирован в системе"

### Сценарий 3: Попытка обойти валидацию
- ✅ Защита в обработчиках срабатывает
- ✅ Операция не выполняется

## Backward Compatibility

⚠️ **BREAKING CHANGE**: Superuser'ы без записи в БД больше не могут войти

**Миграция:**
```python
# Автоматически создать записи для superuser'ов
await staff_service.seed_global_admins([
    123456789,  # TG ID superuser 1
    987654321,  # TG ID superuser 2
])
```

## Change Request Tag

`[CR-2025-10-03-FIX]` - используется во всех изменениях для трассировки

## Автор

Исправление создано автоматически на основе анализа трейса ошибки
