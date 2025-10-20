# 🧪 Инструкция по запуску тестов FIX 1.3 и нагрузочных тестов

## 📋 Обзор

Созданы два набора тестов:

### 1. **test_fix_1_3_comprehensive.py** - Комплексные тесты для FIX 1.3
Тестирование гарантийных заказов и fallback при недоступном preferred мастере

### 2. **test_load_race_condition.py** - Нагрузочные тесты для FIX 1.1
Стресс-тестирование Race Condition при параллельном принятии офферов

---

## 🔧 Предварительные требования

### Для test_fix_1_3_comprehensive.py:
- ✅ **PostgreSQL** (через docker-compose)
- ✅ Реальная база данных
- ✅ Все миграции применены

### Для test_load_race_condition.py:
- ✅ PostgreSQL (через docker-compose)
- ✅ Достаточно ресурсов (100+ параллельных соединений)

---

## 🚀 Запуск тестов

### 1. Запуск PostgreSQL через Docker

```bash
# Перейти в директорию проекта
cd C:\ProjectF\field-service

# Запустить PostgreSQL
docker-compose up -d postgres

# Проверить статус
docker-compose ps
```

### 2. Применение миграций

```bash
# Применить все миграции
alembic upgrade head
```

### 3. Запуск тестов FIX 1.3 (Guarantee Orders)

```bash
# Все тесты FIX 1.3
pytest tests/test_fix_1_3_comprehensive.py -v -s

# Конкретный тест
pytest tests/test_fix_1_3_comprehensive.py::test_preferred_not_on_shift_fallback -v -s

# С детальным выводом
pytest tests/test_fix_1_3_comprehensive.py -vv -s --tb=short
```

#### Тесты FIX 1.3:
- ✅ `test_preferred_not_on_shift_fallback` - Preferred не на смене
- ✅ `test_preferred_on_break_fallback` - Preferred на перерыве
- ✅ `test_preferred_blocked_fallback` - Preferred заблокирован
- ✅ `test_preferred_at_limit_fallback` - Preferred достиг лимита заказов
- ✅ `test_preferred_available_gets_priority` - Preferred доступен (получает приоритет)
- ✅ `test_no_candidates_no_immediate_escalation` - Нет кандидатов (не эскалировать)
- ✅ `test_full_distribution_cycle_with_preferred` - Полный цикл распределения

### 4. Запуск нагрузочных тестов (Load Tests)

```bash
# Быстрые нагрузочные тесты (10 и 50 мастеров)
pytest tests/test_load_race_condition.py -v -s -m "not slow"

# Все нагрузочные тесты (включая 100 мастеров)
pytest tests/test_load_race_condition.py -v -s

# Только стресс-тесты (100 мастеров)
pytest tests/test_load_race_condition.py -v -s -m slow

# Бенчмарк производительности
pytest tests/test_load_race_condition.py::test_lock_performance_benchmark -v -s
```

#### Нагрузочные тесты:
- ✅ `test_race_10_masters` - 10 мастеров → 1 заказ (быстрый)
- ✅ `test_race_50_masters` - 50 мастеров → 1 заказ (средний)
- ✅ `test_race_100_masters` - 100 мастеров → 1 заказ (медленный, @slow)
- ✅ `test_lock_performance_benchmark` - Бенчмарк FOR UPDATE SKIP LOCKED

### 5. Запуск всех тестов вместе

```bash
# Все тесты (FIX 1.3 + Load Tests), кроме медленных
pytest tests/test_fix_1_3_comprehensive.py tests/test_load_race_condition.py -v -s -m "not slow"

# Все тесты включая медленные
pytest tests/test_fix_1_3_comprehensive.py tests/test_load_race_condition.py -v -s
```

---

## 📊 Интерпретация результатов

### Успешный тест FIX 1.3:
```
✅ TEST PASSED: Fallback при preferred not_on_shift работает
   - Preferred недоступен: not_on_shift
   - Найдены альтернативные мастера: 1
   - Оффер отправлен fallback мастеру
```

### Успешный нагрузочный тест:
```
✅ LOAD TEST PASSED: 50 мастеров
   - Успешных: 1
   - Неудачных: 49
   - Min latency: 0.012s
   - Avg latency: 0.156s
   - Max latency: 0.892s
   - Total time: 1.234s
   - Throughput: 40.5 req/s
```

### Метрики производительности (ожидаемые):

| Тест | Мастера | Success | Avg Latency | Max Latency | Throughput |
|------|---------|---------|-------------|-------------|------------|
| 10 мастеров | 10 | 1 | < 0.1s | < 2s | > 5 req/s |
| 50 мастеров | 50 | 1 | < 0.2s | < 5s | > 10 req/s |
| 100 мастеров | 100 | 1 | < 0.5s | < 15s | > 8 req/s |

---

## ❌ Типичные проблемы

### 1. PostgreSQL не запущен
```
Error: could not connect to server
```
**Решение:**
```bash
docker-compose up -d postgres
```

### 2. Миграции не применены
```
ProgrammingError: relation "masters" does not exist
```
**Решение:**
```bash
alembic upgrade head
```

### 3. Timeout на больших тестах
```
asyncio.TimeoutError
```
**Решение:** Увеличить timeout в PostgreSQL:
```sql
ALTER SYSTEM SET statement_timeout = '60s';
SELECT pg_reload_conf();
```

### 4. Deadlock в нагрузочных тестах
```
DeadlockDetected
```
**Решение:** Это нормально! `FOR UPDATE SKIP LOCKED` должен предотвращать deadlock, но PostgreSQL может детектировать их при экстремальной нагрузке.

---

## 🔍 Отладка

### Включить детальное логирование SQL:
```bash
export SQLALCHEMY_ECHO=true
pytest tests/test_fix_1_3_comprehensive.py -v -s
```

### Запустить с дебаггером:
```bash
pytest tests/test_fix_1_3_comprehensive.py::test_preferred_not_on_shift_fallback -v -s --pdb
```

### Проверить состояние БД после теста:
```bash
docker exec -it field-service-postgres-1 psql -U fieldservice -d fieldservice

# Проверить мастеров
SELECT id, full_name, is_on_shift, is_blocked FROM masters ORDER BY id;

# Проверить заказы
SELECT id, status, assigned_master_id, preferred_master_id FROM orders ORDER BY id;

# Проверить офферы
SELECT id, order_id, master_id, state FROM offers ORDER BY id;
```

---

## 📈 Мониторинг производительности

### Профилирование тестов:
```bash
pytest tests/test_load_race_condition.py -v -s --durations=10
```

### Замер времени выполнения:
```bash
time pytest tests/test_fix_1_3_comprehensive.py -v -s
```

---

## ✅ Чеклист перед запуском

- [ ] PostgreSQL запущен (`docker-compose ps`)
- [ ] Миграции применены (`alembic upgrade head`)
- [ ] База данных пустая или очищена
- [ ] Достаточно ресурсов (для 100+ мастеров: 8GB RAM, 4 CPU)
- [ ] Установлены зависимости (`pip install -r requirements.txt`)
- [ ] Правильная директория (`cd C:\ProjectF\field-service`)

---

## 🎯 Следующие шаги

После успешного прохождения тестов:

1. ✅ **Анализ результатов** - Проверить метрики производительности
2. ✅ **Деплой FIX 1.1-1.3** - Применить исправления на продакшн
3. ✅ **Мониторинг** - Настроить алерты на deadlock и высокую latency
4. 🔄 **Оптимизация** - Если метрики не соответствуют ожиданиям

---

## 📞 Поддержка

Если тесты не проходят или возникли вопросы, проверьте:
1. Логи PostgreSQL: `docker-compose logs postgres`
2. Логи тестов: `pytest ... -v -s --tb=long`
3. Состояние БД (см. раздел "Отладка")

---

**Автор:** AI Assistant  
**Дата:** 2025-01-06  
**Версия:** 1.0
