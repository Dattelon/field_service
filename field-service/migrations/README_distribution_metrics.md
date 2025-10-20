# 🔴 P0 - КРИТИЧЕСКАЯ МИГРАЦИЯ: distribution_metrics

## Описание проблемы
В `models.py` определена таблица `distribution_metrics`, но в БД она отсутствует.
Это блокирует работу системы метрик автораспределения заказов.

## Что делает миграция
1. ✅ Создаёт таблицу `distribution_metrics` с 14 колонками
2. ✅ Создаёт 7 индексов для производительности:
   - `idx_distribution_metrics_order_id` - поиск по заказу
   - `idx_distribution_metrics_master_id` - поиск по мастеру
   - `idx_distribution_metrics_city_id` - поиск по городу
   - `idx_distribution_metrics_district_id` - поиск по району
   - `ix_distribution_metrics__assigned_at_desc` - сортировка по времени
   - `ix_distribution_metrics__city_assigned` - аналитика по городам
   - `ix_distribution_metrics__performance` - анализ производительности

## Структура таблицы
```sql
id                          SERIAL PRIMARY KEY
order_id                    INTEGER NOT NULL → orders(id) CASCADE
master_id                   INTEGER NULL → masters(id) SET NULL
assigned_at                 TIMESTAMP WITH TIME ZONE NOT NULL
round_number                SMALLINT NOT NULL
candidates_count            SMALLINT NOT NULL
time_to_assign_seconds      INTEGER NULL
preferred_master_used       BOOLEAN NOT NULL DEFAULT FALSE
was_escalated_to_logist     BOOLEAN NOT NULL DEFAULT FALSE
was_escalated_to_admin      BOOLEAN NOT NULL DEFAULT FALSE
city_id                     INTEGER NOT NULL → cities(id) CASCADE
district_id                 INTEGER NULL → districts(id) SET NULL
category                    VARCHAR(50)
order_type                  VARCHAR(32)
metadata_json               JSONB NOT NULL DEFAULT '{}'
created_at                  TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
```

## Применение миграции

### Шаг 1: Проверка статуса контейнера
```powershell
docker ps | findstr postgres
```

### Шаг 2: Применение миграции
```powershell
# Через psql в контейнере (рекомендуется)
docker exec -i field-service_postgres_1 psql -U field_service_user -d field_service_db < migrations/2025-10-07_create_distribution_metrics.sql

# Или интерактивно
docker exec -it field-service_postgres_1 psql -U field_service_user -d field_service_db
\i /docker-entrypoint-initdb.d/migrations/2025-10-07_create_distribution_metrics.sql
```

### Шаг 3: Проверка успешного применения
```powershell
# Проверить что таблица создана
docker exec field-service_postgres_1 psql -U field_service_user -d field_service_db -c "\d distribution_metrics"

# Проверить индексы
docker exec field-service_postgres_1 psql -U field_service_user -d field_service_db -c "\di distribution_metrics*"

# Проверить количество записей (должно быть 0)
docker exec field-service_postgres_1 psql -U field_service_user -d field_service_db -c "SELECT COUNT(*) FROM distribution_metrics;"
```

## Ожидаемый результат

После успешного применения вы увидите:
```
NOTICE:  Creating table distribution_metrics...
NOTICE:  Table distribution_metrics created successfully
NOTICE:  Creating indexes...
NOTICE:  All indexes created successfully
NOTICE:  ✅ Migration completed: distribution_metrics table created
NOTICE:  ✅ Table distribution_metrics has 14 columns
NOTICE:  ✅ All 8 indexes created successfully
NOTICE:  ================================================
NOTICE:  MIGRATION STATUS: SUCCESS
NOTICE:  Table: distribution_metrics
NOTICE:  Columns: 14
NOTICE:  Indexes: 8
NOTICE:  ================================================
```

И далее будут показаны:
- Структура таблицы (все 14 колонок)
- Список созданных индексов

## Безопасность миграции

✅ **Идемпотентность**: Миграция проверяет существование таблицы и пропускает создание если она уже есть
✅ **Без потери данных**: Создаёт новую таблицу, не изменяет существующие
✅ **Откат**: Если что-то пойдёт не так, можно удалить таблицу:
```sql
DROP TABLE IF EXISTS distribution_metrics CASCADE;
```

## Влияние на систему

### ✅ Что ЗАРАБОТАЕТ после миграции:
- Запись метрик процесса распределения заказов
- Аналитика эффективности автораспределения
- Отчёты по времени назначения мастеров
- Анализ эскалаций к логистам/админам
- Статистика по городам и районам

### ⚠️ Что может сломаться БЕЗ миграции:
- Падение автораспределения при попытке записи метрик
- Ошибки в коде, который пытается записать данные в несуществующую таблицу
- Невозможность анализа производительности системы

## Связанные файлы
- `field_service/db/models.py` - определение модели (строки 918-974)
- `field_service/services/distribution_scheduler.py` - использование метрик

## После применения миграции

1. Перезапустить боты (если они работают):
```powershell
docker-compose restart master_bot admin_bot
```

2. Проверить логи на отсутствие ошибок:
```powershell
docker-compose logs -f master_bot | Select-String "distribution_metrics"
docker-compose logs -f admin_bot | Select-String "distribution_metrics"
```

3. Мониторить заполнение таблицы:
```sql
-- Через несколько минут после запуска должны появиться записи
SELECT COUNT(*), MAX(created_at) FROM distribution_metrics;

-- Проверить последние метрики
SELECT * FROM distribution_metrics ORDER BY created_at DESC LIMIT 5;
```

## Следующие шаги (из плана P0-P1)

После успешного применения этой миграции переходим к:
- ✅ P1-1: Добавить `with_for_update()` в `apply_overdue_commissions`
- ✅ P1-2: Обработка Conflict 409 в Telegram
- ✅ P2-1: Индексы для эскалации

---
**Статус**: 🟢 Готово к применению  
**Приоритет**: 🔴 P0 - КРИТИЧЕСКИЙ  
**Дата создания**: 2025-10-07
