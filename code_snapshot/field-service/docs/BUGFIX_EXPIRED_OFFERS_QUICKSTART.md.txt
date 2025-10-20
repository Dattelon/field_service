# 🚀 QUICKSTART: Проверка watchdog истёкших офферов

**Время выполнения:** 5 минут  
**Приоритет:** P0

---

## 📋 Чеклист перед запуском

- [ ] Все процессы Python остановлены
- [ ] PostgreSQL запущен (`docker ps`)
- [ ] Виртуальное окружение активировано

---

## 1️⃣ Подготовка (1 мин)

### Остановить все процессы:
```powershell
Get-Process python | Where-Object { 
    $_.MainWindowTitle -like '*bot*' 
} | Stop-Process -Force
```

### Проверить что PostgreSQL запущен:
```powershell
docker ps | Select-String postgres
```

Должно вывести: `field-service-postgres-1`

---

## 2️⃣ Очистка зависших офферов (30 сек)

### Проверить наличие зависших офферов:
```powershell
docker exec field-service-postgres-1 psql -U fs_user -d field_service -c "
SELECT 
    id, 
    order_id, 
    master_id, 
    state, 
    expires_at,
    NOW() - expires_at AS overdue
FROM offers 
WHERE state = 'SENT' 
  AND expires_at < NOW()
ORDER BY expires_at;
"
```

### Принудительно пометить как EXPIRED:
```powershell
docker exec field-service-postgres-1 psql -U fs_user -d field_service -c "
UPDATE offers 
SET state = 'EXPIRED' 
WHERE state = 'SENT' 
  AND expires_at < NOW();
"
```

---

## 3️⃣ Запуск ботов (30 сек)

### Открыть 2 терминала PowerShell

**Терминал 1 - Admin Bot:**
```powershell
cd C:\ProjectF\field-service
.venv\Scripts\Activate.ps1
python -m field_service.bots.admin_bot.main
```

**Ожидаемый лог:**
```
INFO [aiogram.dispatcher] Start polling
INFO [autoclose] Autoclose scheduler started, interval=3600s
INFO [aiogram.dispatcher] Run polling for bot @sportsforecastbot_bot
```

**Терминал 2 - Master Bot:**
```powershell
cd C:\ProjectF\field-service
.venv\Scripts\Activate.ps1
python -m field_service.bots.master_bot.main
```

---

## 4️⃣ Проверка watchdog (2 мин)

### Создать тестовый истёкший оффер:

```powershell
docker exec field-service-postgres-1 psql -U fs_user -d field_service -c "
-- Получить ID активного заказа и мастера
WITH test_data AS (
    SELECT 
        o.id AS order_id,
        m.id AS master_id
    FROM orders o
    CROSS JOIN masters m
    WHERE o.status = 'SEARCHING'
      AND m.is_active = TRUE
      AND m.is_on_shift = TRUE
    LIMIT 1
)
INSERT INTO offers (order_id, master_id, state, sent_at, expires_at, round_number)
SELECT 
    order_id,
    master_id,
    'SENT',
    NOW() - INTERVAL '5 minutes',
    NOW() - INTERVAL '2 minutes',
    1
FROM test_data
RETURNING id, order_id, master_id, expires_at;
"
```

### Подождать 60 секунд

Watchdog работает с интервалом 60 секунд.

### Проверить что оффер помечен как EXPIRED:

```powershell
docker exec field-service-postgres-1 psql -U fs_user -d field_service -c "
SELECT 
    id,
    order_id,
    master_id,
    state,
    expires_at,
    responded_at
FROM offers 
WHERE expires_at < NOW() - INTERVAL '1 minute'
ORDER BY id DESC 
LIMIT 5;
"
```

**Ожидаемый результат:**
- `state` = `EXPIRED`
- `responded_at` заполнено

### Проверить логи admin_bot:

В терминале 1 должно появиться:
```
INFO [watchdogs] offer_expired id=XX order=YY master=ZZ
```

---

## 5️⃣ Функциональный тест (1 мин)

### Открыть админ-бот в Telegram:

1. Перейти в "Заказы → Очередь"
2. Выбрать любой заказ в статусе SEARCHING
3. Нажать "Назначить" → "Вручную"
4. **Проверить что все подходящие мастера отображаются**

### Проверить что зависших офферов нет:

```powershell
docker exec field-service-postgres-1 psql -U fs_user -d field_service -c "
SELECT COUNT(*) AS stuck_offers
FROM offers 
WHERE state = 'SENT' 
  AND expires_at < NOW();
"
```

**Ожидаемый результат:** `stuck_offers = 0`

---

## 6️⃣ Запуск тестов (опционально, 30 сек)

```powershell
cd C:\ProjectF\field-service
.venv\Scripts\Activate.ps1
$env:PYTHONIOENCODING='utf-8'
pytest tests/test_watchdog_expired_offers.py -v
```

**Ожидаемый результат:**
```
test_watchdog_expires_old_offers PASSED
test_watchdog_keeps_active_offers PASSED
test_watchdog_multiple_expired_offers PASSED
test_watchdog_ignores_already_expired PASSED
test_watchdog_ignores_declined_offers PASSED

====== 5 passed in X.XXs ======
```

---

## ✅ Критерии успешной проверки

- [x] Оба бота запущены без ошибок
- [x] Watchdog логирует истёкшие офферы каждую минуту
- [x] Зависших офферов в БД нет
- [x] Мастера отображаются в ручном назначении
- [x] Тесты проходят (опционально)

---

## 🐛 Troubleshooting

### Проблема: "NameError: select_candidates not defined"
**Решение:** Проверить импорт в `masters.py`:
```python
from field_service.services.candidates import select_candidates
```

### Проблема: Watchdog не запускается
**Проверить:**
1. Импорт в `main.py`:
```python
from field_service.services.watchdogs import watchdog_expired_offers
```

2. Создание задачи:
```python
expired_offers_task = asyncio.create_task(
    watchdog_expired_offers(interval_seconds=60),
    name="expired_offers_watchdog",
)
```

### Проблема: Офферы не помечаются как EXPIRED
**Проверить:**
1. Логи watchdog в консоли admin_bot
2. Время БД совпадает с реальным:
```sql
SELECT NOW(), NOW() - INTERVAL '1 minute';
```

### Проблема: Дублирующиеся процессы
**Решение:**
```powershell
Get-Process python | Where-Object {
    $_.CommandLine -like "*field_service.bots*"
} | Group-Object CommandLine | Where-Object Count -gt 1 | 
  ForEach-Object { $_.Group[1..($_.Count-1)] | Stop-Process -Force }
```

---

## 📊 Мониторинг после запуска

### Через 5 минут проверить:
```powershell
docker exec field-service-postgres-1 psql -U fs_user -d field_service -c "
SELECT 
    state,
    COUNT(*) AS count,
    MIN(expires_at) AS oldest_expires,
    MAX(expires_at) AS newest_expires
FROM offers
WHERE created_at > NOW() - INTERVAL '1 hour'
GROUP BY state
ORDER BY state;
"
```

### Через 1 час проверить:
```powershell
docker exec field-service-postgres-1 psql -U fs_user -d field_service -c "
SELECT 
    DATE_TRUNC('minute', responded_at) AS minute,
    COUNT(*) AS expired_count
FROM offers
WHERE state = 'EXPIRED'
  AND responded_at > NOW() - INTERVAL '1 hour'
GROUP BY minute
ORDER BY minute DESC
LIMIT 10;
"
```

---

## 📚 Дополнительная документация

- **Полное описание:** `docs/BUGFIX_EXPIRED_OFFERS_WATCHDOG.md`
- **Тесты:** `tests/test_watchdog_expired_offers.py`
- **Код watchdog:** `field_service/services/watchdogs.py`

---

**Последнее обновление:** 2025-10-10  
**Статус:** ✅ Готово к использованию
