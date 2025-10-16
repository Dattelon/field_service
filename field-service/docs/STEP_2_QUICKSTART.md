# STEP 2: Централизация accept_offer - QUICKSTART

## Что сделано

✅ Создан сервис `OrdersService` с атомарным `accept_offer`  
✅ Добавлены частичные индексы для таблицы `offers`  
✅ Упрощён обработчик в мастер-боте (440 → 82 строки)  
✅ Использован `SELECT ... FOR UPDATE SKIP LOCKED`  

## Применение миграций

```powershell
# Локально (тестирование)
cd C:\ProjectF\field-service
docker compose up -d postgres
docker exec -i fs_postgres psql -U field_user -d field_service < migrations\2025-10-15_add_offers_partial_indexes.sql

# Проверка индексов
docker exec fs_postgres psql -U field_user -d field_service -c "SELECT indexname FROM pg_indexes WHERE tablename = 'offers' AND indexname LIKE 'idx_offers_%';"
```

## Деплой на сервер

```powershell
# 1. Загрузить файлы через WinSCP:
#    - field_service/services/orders_service.py (новый)
#    - field_service/services/distribution_metrics_service.py (обновлён)
#    - field_service/bots/master_bot/handlers/orders.py (обновлён)
#    - migrations/2025-10-15_add_offers_partial_indexes.sql

# 2. Подключиться к серверу
$pass = ConvertTo-SecureString "owo?8x-YA@vRN*" -AsPlainText -Force
$cred = New-Object System.Management.Automation.PSCredential("root", $pass)
$s = New-SSHSession -ComputerName 217.199.254.27 -Credential $cred -AcceptKey

# 3. Применить миграцию
Invoke-SSHCommand -SessionId $s.SessionId -Command @"
cd /opt/field-service
docker exec -i fs_postgres psql -U field_user -d field_service < migrations/2025-10-15_add_offers_partial_indexes.sql
"@

# 4. Перезапустить боты
Invoke-SSHCommand -SessionId $s.SessionId -Command "cd /opt/field-service && docker compose restart master-bot admin-bot"

# 5. Проверить логи
Invoke-SSHCommand -SessionId $s.SessionId -Command "cd /opt/field-service && docker compose logs --tail=50 master-bot"

Remove-SSHSession -SessionId $s.SessionId
```

## Проверка работы

```sql
-- Проверить индексы
docker exec fs_postgres psql -U field_user -d field_service -c "
SELECT schemaname, tablename, indexname
FROM pg_indexes
WHERE tablename = 'offers' AND indexname LIKE 'idx_offers_%'
ORDER BY indexname;"

-- Должны быть:
-- idx_offers_active_state
-- idx_offers_master_active
-- idx_offers_not_expired
-- idx_offers_order_master_active
```

## Тестирование

```bash
# Локально
cd C:\ProjectF\field-service
pytest tests/ -v -k "accept" --tb=short

# Ожидаемый результат: все тесты проходят
```

## Откат (если что-то сломалось)

```sql
-- Удалить индексы
DROP INDEX CONCURRENTLY IF EXISTS idx_offers_active_state;
DROP INDEX CONCURRENTLY IF EXISTS idx_offers_not_expired;
DROP INDEX CONCURRENTLY IF EXISTS idx_offers_order_master_active;
DROP INDEX CONCURRENTLY IF EXISTS idx_offers_master_active;
```

```bash
# Откатить код (восстановить из git)
cd /opt/field-service
git checkout HEAD~1 field_service/services/orders_service.py
git checkout HEAD~1 field_service/bots/master_bot/handlers/orders.py
docker compose restart master-bot
```

## Мониторинг

```bash
# Следить за логами
docker compose logs -f master-bot | grep "offer_accept"

# Должны видеть:
# - "offer_accept START: master=X order_id=Y"
# - "offer_accept: found offer_id=Z"
# - "offer_accept SUCCESS: order=Y assigned to master=X"
```

## Готово! ✅

**Токенов осталось:** 61409/190000
