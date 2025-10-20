# HOTFIX v2: GLOBAL_ADMIN FK-constraint fix

## Проблема
После исправления валидации `staff.id` выяснилось, что GLOBAL_ADMIN с `tg_id=332786197` **не существует в таблице `staff_users`**, что приводит к ошибке FK-constraint при попытке записи в `order_status_history`:

```
ForeignKeyViolationError: Key (changed_by_staff_id)=(0) is not present in table "staff_users"
```

## Решение
✅ Создать запись GLOBAL_ADMIN в базе данных через SQL-скрипт  
✅ Обновить middleware для загрузки superuser из БД вместо виртуального объекта

## Применение исправления

### 1. Выполнить SQL-скрипт
```bash
# Подключиться к БД (пример с psql)
psql -h 127.0.0.1 -p 5439 -U fs_user -d field_service

# Выполнить скрипт
\i C:/ProjectF/field-service/scripts/init_global_admin.sql

# Или одной командой из PowerShell
cat scripts/init_global_admin.sql | docker exec -i field-service-postgres-1 psql -U fs_user -d field_service
```

### 2. Проверить создание записи
```sql
SELECT id, tg_user_id, full_name, role, is_active 
FROM staff_users 
WHERE tg_user_id = 332786197;
```

Ожидаемый результат:
```
 id | tg_user_id  | full_name  |     role      | is_active
----+-------------+------------+---------------+-----------
  1 | 332786197   | Superuser  | GLOBAL_ADMIN  | t
```

### 3. Перезапустить админ-бот
```bash
# Остановить текущий процесс (Ctrl+C)
# Запустить заново
python -m field_service.bots.admin_bot.main
```

### 4. Протестировать
```
1. Открыть бот как GLOBAL_ADMIN (tg_id=332786197)
2. Меню → 💰 Финансы → Ожидают оплаты
3. Выбрать комиссию → ✅ Подтвердить <сумма> ₽
4. Убедиться, что операция проходит БЕЗ ошибок FK-constraint
```

## Изменённые файлы
- `field_service/bots/admin_bot/handlers_finance.py` — валидация staff.id
- `field_service/bots/admin_bot/middlewares.py` — загрузка superuser из БД
- `scripts/init_global_admin.sql` — инициализация GLOBAL_ADMIN (НОВЫЙ ФАЙЛ)

## Важные детали
1. **Виртуальный superuser больше не используется** — теперь GLOBAL_ADMIN должен существовать в БД
2. **FK-constraint работает корректно** — `changed_by_staff_id` теперь ссылается на реальную запись
3. **Безопасность** — если superuser не найден в БД, доступ блокируется с сообщением об ошибке

## Статус
🟢 **ГОТОВО К ДЕПЛОЮ**

## Дата
03.10.2025, 22:10
