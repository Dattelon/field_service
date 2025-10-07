# P1.1: Инструкция по применению недостающих индексов

## Проблема
В `models.py` определены индексы, которые отсутствуют в БД:
- `ix_commissions__status_deadline` (status, deadline_at)
- `ix_commissions__master_status` (master_id, status)

## Влияние
- Медленные запросы при поиске просроченных комиссий
- Проблемы производительности в админ-панели (финансы мастера)
- Watchdog комиссий работает неоптимально

## Решение

### Вариант 1: Через docker exec (РЕКОМЕНДУЕТСЯ)

```powershell
# 1. Скопировать SQL файл в контейнер
docker cp C:\ProjectF\field-service\migrations\P1_1_add_missing_commissions_indexes.sql field-service-postgres-1:/tmp/

# 2. Выполнить миграцию
docker exec -i field-service-postgres-1 psql -U postgres -d field_service -f /tmp/P1_1_add_missing_commissions_indexes.sql

# 3. Проверить результат
docker exec -i field-service-postgres-1 psql -U postgres -d field_service -c "SELECT indexname FROM pg_indexes WHERE tablename = 'commissions' ORDER BY indexname;"
```

### Вариант 2: Напрямую через psql

```powershell
# Если psql установлен на хосте
psql -h localhost -p 5432 -U postgres -d field_service -f C:\ProjectF\field-service\migrations\P1_1_add_missing_commissions_indexes.sql
```

### Вариант 3: Через docker exec без файла

```powershell
docker exec -i field-service-postgres-1 psql -U postgres -d field_service <<'EOF'
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_commissions__status_deadline 
ON commissions (status, deadline_at);

CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_commissions__master_status 
ON commissions (master_id, status);

SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'commissions' ORDER BY indexname;
EOF
```

## Проверка после применения

```sql
-- Должно быть 5 индексов:
-- 1. pk_commissions (id) - PRIMARY KEY
-- 2. uq_commissions__order_id (order_id) - UNIQUE
-- 3. ix_commissions__ispaid_deadline (is_paid, deadline_at)
-- 4. ix_commissions__status_deadline (status, deadline_at) - НОВЫЙ
-- 5. ix_commissions__master_status (master_id, status) - НОВЫЙ

SELECT indexname, indexdef 
FROM pg_indexes 
WHERE tablename = 'commissions' 
ORDER BY indexname;
```

## Важные замечания

1. **CONCURRENTLY** - создание индекса без блокировки таблицы
2. **IF NOT EXISTS** - безопасное повторное выполнение
3. Время создания: ~1-5 секунд (зависит от количества записей)
4. После создания индексов рекомендуется выполнить `ANALYZE commissions;`

## Откат (если что-то пошло не так)

```sql
DROP INDEX CONCURRENTLY IF EXISTS ix_commissions__status_deadline;
DROP INDEX CONCURRENTLY IF EXISTS ix_commissions__master_status;
```

## Статус
- [ ] Индексы созданы
- [ ] Проверка выполнена
- [ ] ANALYZE выполнен
