# Инструкция по подготовке БД к E2E тестированию

## Дата: 2025-10-09

## Цель
Подготовить чистую БД и настроить права доступа для тестирования жизненного цикла заказов через Telethon.

## Шаги выполнения

### 1. Назначение тестового пользователя глобальным админом

```powershell
# Из корня проекта
docker exec -i projectf-db-1 psql -U postgres -d field_service < field-service\migrations\2025-10-09_setup_test_admin.sql
```

**Что делает:**
- Меняет роль пользователя regizdrou (tg_user_id: 6022057382) с LOGIST на GLOBAL_ADMIN
- Активирует пользователя
- Выводит список всех админов для проверки

**Ожидаемый результат:**
```
UPDATE 1
 id | tg_user_id |  username  | full_name | role         | is_active
----+------------+------------+-----------+--------------+-----------
  8 | 6022057382 | regizdrou  | regizdrou | GLOBAL_ADMIN | t
```

---

### 2. Полная очистка тестовых данных

```powershell
# Из корня проекта
docker exec -i projectf-db-1 psql -U postgres -d field_service < field-service\migrations\2025-10-09_clean_test_data.sql
```

**Что делает:**
- Удаляет ВСЕ заказы, офферы, комиссии, мастеров
- Удаляет историю, уведомления, логи
- Сбрасывает автоинкременты на 1
- **СОХРАНЯЕТ:** города, районы, навыки, настройки, админов

**Ожидаемый результат:**
```
BEGIN
...множество DELETE...
ALTER SEQUENCE
...
COMMIT
       status       |          timestamp
--------------------+----------------------------
 CLEANUP COMPLETE   | 2025-10-09 XX:XX:XX.XXXXXX

      table_name         | count
-------------------------+-------
 cities                  |   79
 commissions             |    0
 districts               |  XXX
 master_districts        |    0
 masters                 |    0
 offers                  |    0
 order_status_history    |    0
 orders                  |    0
 staff_users             |    9
```

---

## После выполнения скриптов

1. **Проверка доступа к админ-боту:**
   - Откройте Telegram
   - Найдите бота (username из конфига)
   - Отправьте /start
   - Должны увидеть полное меню глобального админа

2. **Авторизация Telethon сессии:**
   ```powershell
   cd C:\ProjectF
   python tests\telegram_ui\setup_client.py
   ```
   - Введите номер телефона тестового аккаунта
   - Введите код из SMS/Telegram
   - Создастся файл test_session.session

3. **Проверка Telethon подключения:**
   ```powershell
   cd C:\ProjectF
   $env:PYTHONIOENCODING='utf-8'
   python tests\telegram_ui\check_session_simple.py
   ```
   - Должен вывести: "Authorization status: AUTHORIZED"
   - И данные пользователя

---

## Что дальше

После успешного выполнения всех шагов можно приступать к:
- Разработке плана E2E тестов
- Написанию тестов жизненного цикла заказа
- Запуску автоматизированного тестирования

---

## Безопасность

✅ **Что сохраняется:**
- Все города (79 штук)
- Все районы
- Все навыки
- Все настройки (settings)
- Все администраторы (staff_users)

❌ **Что удаляется:**
- ВСЕ заказы и история
- ВСЕ мастера и их данные
- ВСЕ офферы и комиссии
- ВСЕ уведомления и метрики

---

## Откат изменений

Если нужно вернуть роль LOGIST:
```sql
UPDATE staff_users 
SET role = 'LOGIST' 
WHERE tg_user_id = '6022057382';
```

Если нужно восстановить данные - используйте бэкап из ops/backup_db.ps1
