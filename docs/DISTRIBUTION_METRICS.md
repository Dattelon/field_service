# 📊 Метрики распределения заказов (STEP 4.1)

## Обзор

Система метрик распределения собирает подробную аналитику о процессе назначения мастеров на заказы для:
- Мониторинга производительности распределения
- Выявления узких мест
- Оптимизации алгоритмов
- Анализа эффективности мастеров и городов

## Таблица `distribution_metrics`

### Структура

```sql
CREATE TABLE distribution_metrics (
    id SERIAL PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    master_id INTEGER REFERENCES masters(id) ON DELETE SET NULL,
    
    -- Метрики назначения
    assigned_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    round_number SMALLINT NOT NULL,
    candidates_count SMALLINT NOT NULL,
    time_to_assign_seconds INTEGER,
    
    -- Флаги процесса
    preferred_master_used BOOLEAN NOT NULL DEFAULT FALSE,
    was_escalated_to_logist BOOLEAN NOT NULL DEFAULT FALSE,
    was_escalated_to_admin BOOLEAN NOT NULL DEFAULT FALSE,
    
    -- География
    city_id INTEGER NOT NULL REFERENCES cities(id) ON DELETE CASCADE,
    district_id INTEGER REFERENCES districts(id) ON DELETE SET NULL,
    category ordercategory,
    order_type VARCHAR(32),
    
    -- Дополнительные данные
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);
```

### Индексы

- `ix_distribution_metrics_order_id` - быстрый поиск по заказу
- `ix_distribution_metrics_master_id` - статистика по мастеру
- `ix_distribution_metrics_assigned_at` - временные срезы
- `ix_distribution_metrics__city_assigned` - аналитика по городам
- `ix_distribution_metrics__performance` - анализ производительности

## Когда записываются метрики

### 1. При принятии оффера мастером

**Файл:** `field_service/bots/master_bot/handlers/orders.py`  
**Функция:** `offer_accept()`

Метрики записываются после успешного назначения заказа на мастера:

```python
metrics = m.distribution_metrics(
    order_id=order_id,
    master_id=master.id,
    round_number=max_round,
    candidates_count=total_candidates,
    time_to_assign_seconds=time_to_assign,
    preferred_master_used=(master.id == preferred_master_id),
    was_escalated_to_logist=escalated_logist,
    was_escalated_to_admin=escalated_admin,
    city_id=city_id,
    district_id=district_id,
    category=category,
    order_type=order_type,
    metadata_json={"assigned_via": "master_bot"}
)
```

### 2. При ручном назначении админом

**Файл:** `field_service/bots/admin_bot/services/orders.py`  
**Функция:** `assign_master()`

Метрики записываются при ручном назначении заказа сотрудником:

```python
metadata_json={
    "assigned_via": "admin_manual",
    "staff_id": staff.id,
    "from_status": prev_status
}
```

## Сервис аналитики

### Класс `DistributionMetricsService`

**Файл:** `field_service/services/distribution_metrics_service.py`

#### Методы

##### `get_stats()`

Возвращает общую статистику за период:

```python
service = DistributionMetricsService()
stats = await service.get_stats(
    start_date=datetime.now() - timedelta(days=7),
    end_date=datetime.now(),
    city_id=1  # optional
)

print(f"Всего назначений: {stats.total_assignments}")
print(f"Среднее время назначения: {stats.avg_time_to_assign}с")
print(f"Средний раунд: {stats.avg_round_number}")
print(f"% эскалаций к логисту: {stats.escalated_to_logist_pct}%")
print(f"% назначений с раунда 1: {stats.round_1_pct}%")
```

##### `get_city_performance()`

Статистика по городам:

```python
cities = await service.get_city_performance(
    start_date=datetime.now() - timedelta(days=7),
    limit=20
)

for city in cities:
    print(f"{city.city_name}: {city.total_assignments} назначений, "
          f"avg time: {city.avg_time_to_assign}с, "
          f"escalation rate: {city.escalation_rate}%")
```

##### `get_master_performance()`

Статистика по мастерам:

```python
masters = await service.get_master_performance(
    start_date=datetime.now() - timedelta(days=30),
    master_id=100,  # optional
    limit=50
)

for master in masters:
    print(f"{master.master_name}: {master.total_assignments} заказов, "
          f"auto: {master.from_auto}, manual: {master.from_manual}, "
          f"preferred: {master.from_preferred}")
```

##### `get_hourly_distribution()`

Распределение по часам суток:

```python
hourly = await service.get_hourly_distribution(
    start_date=datetime.now() - timedelta(days=7)
)

for hour, count in hourly.items():
    print(f"{hour:02d}:00 - {count} назначений")
```

## Примеры запросов

### Средняя скорость назначения по городам

```sql
SELECT 
    c.name AS city,
    COUNT(*) AS total_assignments,
    ROUND(AVG(dm.time_to_assign_seconds)) AS avg_seconds,
    ROUND(AVG(dm.time_to_assign_seconds) / 60.0, 1) AS avg_minutes
FROM distribution_metrics dm
JOIN cities c ON c.id = dm.city_id
WHERE dm.assigned_at >= NOW() - INTERVAL '7 days'
GROUP BY c.name
ORDER BY total_assignments DESC
LIMIT 20;
```

### Распределение по раундам

```sql
SELECT 
    round_number,
    COUNT(*) AS count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 2) AS percentage
FROM distribution_metrics
WHERE assigned_at >= NOW() - INTERVAL '7 days'
GROUP BY round_number
ORDER BY round_number;
```

### Топ мастеров по скорости принятия

```sql
SELECT 
    m.full_name,
    COUNT(*) AS total_assignments,
    ROUND(AVG(dm.time_to_assign_seconds / 60.0), 1) AS avg_minutes,
    SUM(CASE WHEN dm.preferred_master_used THEN 1 ELSE 0 END) AS from_preferred
FROM distribution_metrics dm
JOIN masters m ON m.id = dm.master_id
WHERE dm.assigned_at >= NOW() - INTERVAL '30 days'
GROUP BY m.id, m.full_name
HAVING COUNT(*) >= 5
ORDER BY avg_minutes ASC
LIMIT 20;
```

### Эффективность распределения по времени суток

```sql
SELECT 
    EXTRACT(HOUR FROM assigned_at) AS hour,
    COUNT(*) AS assignments,
    ROUND(AVG(time_to_assign_seconds / 60.0), 1) AS avg_minutes,
    ROUND(SUM(CASE WHEN was_escalated_to_logist OR was_escalated_to_admin 
              THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS escalation_pct
FROM distribution_metrics
WHERE assigned_at >= NOW() - INTERVAL '7 days'
GROUP BY EXTRACT(HOUR FROM assigned_at)
ORDER BY hour;
```

## Применение миграции

### 1. Проверить текущую ревизию

```bash
cd C:\ProjectF\field-service
docker exec field-service-db psql -U postgres -d field_service -c "SELECT * FROM alembic_version;"
```

### 2. Применить миграцию

```bash
# Внутри контейнера или локально
alembic upgrade head
```

Или через Docker:

```bash
docker exec field-service-web alembic upgrade head
```

### 3. Проверить создание таблицы

```bash
docker exec field-service-db psql -U postgres -d field_service -c "\d distribution_metrics"
```

## Мониторинг

### Проверить количество записанных метрик

```sql
SELECT COUNT(*) FROM distribution_metrics;
```

### Проверить последние записи

```sql
SELECT 
    dm.id,
    dm.order_id,
    m.full_name AS master,
    dm.round_number,
    dm.time_to_assign_seconds,
    dm.assigned_at
FROM distribution_metrics dm
LEFT JOIN masters m ON m.id = dm.master_id
ORDER BY dm.assigned_at DESC
LIMIT 10;
```

### Проверить метрики за сегодня

```sql
SELECT 
    COUNT(*) AS total,
    AVG(time_to_assign_seconds) AS avg_time,
    AVG(round_number) AS avg_round,
    SUM(CASE WHEN preferred_master_used THEN 1 ELSE 0 END) AS preferred_used,
    SUM(CASE WHEN was_escalated_to_logist THEN 1 ELSE 0 END) AS escalated_logist,
    SUM(CASE WHEN was_escalated_to_admin THEN 1 ELSE 0 END) AS escalated_admin
FROM distribution_metrics
WHERE assigned_at >= CURRENT_DATE;
```

## Ограничения и замечания

1. **Не блокирует основной процесс**: Ошибки записи метрик не должны прерывать назначение заказов
2. **Nullable поля**: `time_to_assign_seconds` может быть NULL если не удалось рассчитать
3. **Метаданные**: Дополнительная информация хранится в `metadata_json` (способ назначения, staff_id и т.д.)
4. **Каскадное удаление**: При удалении заказа метрики также удаляются (CASCADE)

## Дальнейшее развитие

- [ ] Dashboard для визуализации метрик
- [ ] Автоматические алерты при деградации метрик
- [ ] Интеграция с системой отчётности
- [ ] ML-модель для предсказания времени назначения
- [ ] A/B тестирование алгоритмов распределения

## См. также

- [Тесты метрик](../tests/test_distribution_metrics.py)
- [Сервис аналитики](../field_service/services/distribution_metrics_service.py)
- [Миграция](../alembic/versions/2025_10_06_0001_distribution_metrics.py)
