# P1-21: Quick Start Guide

## 🚀 Быстрый запуск

### 1. Применить миграцию (если ещё не применена)
```powershell
Get-Content C:\ProjectF\field-service\migrations\2025-10-09_create_commission_deadline_notifications.sql | docker exec -i field-service-postgres-1 psql -U fs_user -d field_service
```

### 2. Перезапустить admin-bot
```powershell
docker-compose -f C:\ProjectF\field-service\docker-compose.yml restart admin-bot
```

### 3. Проверить что watchdog запустился
```powershell
docker logs field-service-admin-bot-1 --tail 50 | Select-String "commission_deadline"
```

---

## 🧪 Тестирование

### Создать тестовую комиссию с дедлайном через 1 час
```sql
-- Подключиться к БД
docker exec -it field-service-postgres-1 psql -U fs_user -d field_service

-- Найти мастера для теста
SELECT id, tg_user_id, full_name FROM masters LIMIT 5;

-- Найти заказ
SELECT id, master_id, status FROM orders WHERE status = 'CLOSED' LIMIT 5;

-- Создать тестовую комиссию с дедлайном через 1 час
INSERT INTO commissions (
    order_id, 
    master_id, 
    amount, 
    status, 
    deadline_at
) VALUES (
    <order_id>,     -- ID заказа
    <master_id>,    -- ID мастера
    1000.00,        -- Сумма
    'WAIT_PAY',     -- Статус
    NOW() + INTERVAL '1 hour 5 minutes'  -- Дедлайн через 1 час 5 минут
) RETURNING id;

-- Подождать 30 минут (следующий запуск watchdog)
-- Или перезапустить бота сразу для теста
```

### Проверить отправку уведомления
```sql
-- Проверить что уведомление записано
SELECT * FROM commission_deadline_notifications 
WHERE commission_id = <commission_id>;

-- Должно быть:
-- commission_id | hours_before | sent_at
-- 123          | 1            | 2025-10-09 12:30:00+00
```

### Проверить логи бота
```powershell
# Фильтр по уведомлениям
docker logs field-service-admin-bot-1 -f | Select-String "deadline_reminder"

# Ожидаемый вывод:
# INFO [watchdogs] commission_deadline_reminder sent: commission=123 master=45 hours=1
# INFO [watchdogs] commission_deadline_reminders sent=1 notifications
```

---

## 📊 Мониторинг

### Статистика за сегодня
```sql
SELECT 
    hours_before,
    COUNT(*) as sent_today
FROM commission_deadline_notifications
WHERE DATE(sent_at) = CURRENT_DATE
GROUP BY hours_before
ORDER BY hours_before DESC;
```

### Последние отправленные уведомления
```sql
SELECT 
    cdn.id,
    cdn.commission_id,
    cdn.hours_before,
    cdn.sent_at,
    c.master_id,
    c.amount,
    c.deadline_at,
    m.full_name
FROM commission_deadline_notifications cdn
JOIN commissions c ON c.id = cdn.commission_id
JOIN masters m ON m.id = c.master_id
ORDER BY cdn.sent_at DESC
LIMIT 10;
```

---

## ❌ Troubleshooting

### Проблема: Уведомления не отправляются

**Проверки**:
1. Watchdog запущен?
   ```powershell
   docker logs field-service-admin-bot-1 --tail 100 | Select-String "commission_deadline"
   ```

2. Есть ли комиссии в статусе WAIT_PAY?
   ```sql
   SELECT COUNT(*) FROM commissions WHERE status = 'WAIT_PAY';
   ```

3. Не отправлены ли уже уведомления?
   ```sql
   SELECT * FROM commission_deadline_notifications 
   WHERE commission_id IN (
       SELECT id FROM commissions WHERE status = 'WAIT_PAY'
   );
   ```

4. Правильный ли дедлайн?
   ```sql
   SELECT 
       id, 
       master_id, 
       deadline_at,
       EXTRACT(EPOCH FROM (deadline_at - NOW())) / 3600 as hours_until
   FROM commissions 
   WHERE status = 'WAIT_PAY'
   ORDER BY deadline_at;
   ```

### Проблема: Дублирующие уведомления

**Причина**: Нарушено unique constraint
**Решение**: Проверить логи на ошибки INSERT

```powershell
docker logs field-service-admin-bot-1 | Select-String "duplicate key"
```

### Проблема: Мастер не получил уведомление

**Проверки**:
1. Есть ли у мастера tg_user_id?
   ```sql
   SELECT id, tg_user_id FROM masters WHERE id = <master_id>;
   ```

2. Записано ли уведомление в БД?
   ```sql
   SELECT * FROM commission_deadline_notifications 
   WHERE commission_id IN (
       SELECT id FROM commissions WHERE master_id = <master_id>
   );
   ```

3. Есть ли ошибки в логах бота?
   ```powershell
   docker logs field-service-admin-bot-1 --tail 200 | Select-String "Failed to send deadline reminder"
   ```

---

## ✅ Успешное тестирование

Признаки успешной работы:
1. ✅ Мастер получил Telegram уведомление
2. ✅ Запись появилась в `commission_deadline_notifications`
3. ✅ В логах: `commission_deadline_reminder sent`
4. ✅ Повторных уведомлений нет (unique constraint работает)

---

## 🔄 Откат изменений (если нужно)

```sql
-- Удалить таблицу уведомлений
DROP TABLE IF EXISTS commission_deadline_notifications;

-- Удалить модель из models.py
-- Удалить функцию из watchdogs.py
-- Убрать импорт и task из admin_bot/main.py
-- Перезапустить боты
```

---

**Готово!** Система уведомлений о дедлайне комиссии работает. 🎉
