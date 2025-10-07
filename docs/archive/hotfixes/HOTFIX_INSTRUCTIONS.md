# Быстрая инструкция: Исправление FK Violation

## Что сделано

Исправлена критическая ошибка при одобрении комиссий:
- ❌ Было: superuser с фейковым `id=0` → FK violation
- ✅ Стало: только реальные staff_users из БД

## Изменённые файлы

```
field_service/bots/admin_bot/
├── middlewares.py           (убран фейковый StaffUser с id=0)
└── handlers_finance.py      (добавлена валидация staff.id)
```

## Срочно после деплоя

**1. Проверить наличие superuser'ов в БД:**

```sql
SELECT id, tg_user_id, full_name, role, is_active 
FROM staff_users 
WHERE role = 'ADMIN' AND is_active = true;
```

**2. Если superuser'ы отсутствуют - добавить:**

```sql
-- Замените на реальные Telegram ID
INSERT INTO staff_users (tg_user_id, role, is_active, full_name, phone)
VALUES 
    (123456789, 'ADMIN', true, 'Superuser 1', '+71234567890'),
    (987654321, 'ADMIN', true, 'Superuser 2', '+79876543210');
```

**3. Или использовать код:**

```python
from field_service.bots.admin_bot.services_db import DBStaffService

staff_service = DBStaffService()
await staff_service.seed_global_admins([
    123456789,  # TG ID superuser 1
    987654321,  # TG ID superuser 2
])
```

## Проверка работы

### ✅ Тест 1: Вход superuser'а
1. Запустить бот
2. Войти как superuser (настроенный в .env ADMIN_TG_IDS)
3. **Ожидаемо:** Доступ разрешён, видно меню

### ✅ Тест 2: Одобрение комиссии
1. Финансы → Ожидают оплаты
2. Выбрать комиссию
3. Нажать "Подтвердить"
4. **Ожидаемо:** ✅ Комиссия одобрена

### ❌ Тест 3: Незарегистрированный superuser
1. Удалить запись из staff_users для тестового TG ID
2. Попробовать войти
3. **Ожидаемо:** ⛔ Суперпользователь не зарегистрирован в системе

## Откат (если что-то пошло не так)

```bash
git revert HEAD
# или
git checkout HEAD~1 field_service/bots/admin_bot/middlewares.py
git checkout HEAD~1 field_service/bots/admin_bot/handlers_finance.py
```

**Внимание:** После отката superuser'ы с фейковым id=0 снова смогут войти, но проблема с FK violation вернётся!

## Мониторинг

После деплоя следить за логами:
```bash
# Ошибки FK violation больше не должны появляться
grep "ForeignKeyViolationError" logs/app.log

# Проверить логи входа superuser'ов
grep "superuser" logs/app.log
```

## Вопросы?

См. полную документацию: `BUGFIX_2025-10-03_FK_VIOLATION.md`
