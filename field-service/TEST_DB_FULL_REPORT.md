# База данных Field Service - Полная структура (ТЕСТОВАЯ БД)

**Дата сбора:** 2025-10-16  
**База данных:** field_service_test  
**Контейнер:** field-service-postgres-1  
**Порт:** 5439 → 5432  

---

## Версия миграций Alembic

**Текущая версия:** `2025_10_16_0002`

---

## Сводка по таблицам

**Всего таблиц:** 27

### Список с количеством записей

| Таблица | Записей | Описание |
|---------|----------|----------|
| admin_audit_log | 0 | Аудит действий администраторов |
| alembic_version | 1 | Версии миграций |
| attachments | 0 | Вложения к заказам/комиссиям |
| cities | 3 | Города (тестовые данные) |
| commission_deadline_notifications | 0 | **✅ Уведомления о дедлайнах комиссий** |
| commissions | 0 | Комиссии мастеров |
| distribution_metrics | 0 | Метрики распределения |
| districts | 2 | Районы городов |
| geocache | 0 | Кэш геокодирования |
| master_districts | 0 | М2М: Мастера ↔ Районы |
| master_invite_codes | 0 | Пригласительные коды |
| master_skills | 0 | М2М: Мастера ↔ Навыки |
| masters | 20 | Мастера (тестовые данные) |
| notifications_outbox | 0 | Очередь уведомлений |
| offers | 20 | Офферы мастерам |
| order_autoclose_queue | 0 | Очередь автозакрытия |
| order_status_history | 1 | История статусов заказов |
| orders | 1 | Заказы |
| referral_rewards | 0 | Реферальные начисления |
| referrals | 0 | Реферальные связи |
| settings | 0 | Настройки системы |
| skills | 0 | **⚠️ Навыки (ПУСТО - нужен seed)** |
| staff_access_code_cities | 0 | М2М: Коды доступа ↔ Города |
| staff_access_codes | 0 | Коды доступа персонала |
| staff_cities | 0 | М2М: Персонал ↔ Города |
| staff_users | 2 | Пользователи персонала |
| streets | 0 | Улицы |

---

## Критичные таблицы - детали

### commission_deadline_notifications ✅

**Статус:** СОЗДАНА миграцией `2025_10_16_0001`

**Структура:**
- `id` INTEGER PRIMARY KEY
- `commission_id` INTEGER FK → commissions(id) CASCADE
- `hours_before` SMALLINT NOT NULL (CHECK: 1, 6, 24)
- `sent_at` TIMESTAMPTZ NOT NULL DEFAULT now()

**Индексы:**
- PRIMARY KEY (id)
- INDEX ON commission_id
- UNIQUE (commission_id, hours_before)

**Записей:** 0

---

### masters (37 колонок)

**Записей:** 20 (тестовые Load Test Master 1-20)

**Ключевые поля:**
- ✅ `tg_user_id` BIGINT (есть, можно NULL для тестов)
- ✅ `full_name` VARCHAR(160) NOT NULL
- ❌ `patronymic` - НЕТ (не нужна, используется full_name)
- ✅ `is_on_shift` BOOLEAN NOT NULL
- ✅ `verified` BOOLEAN NOT NULL
- ✅ `is_deleted` BOOLEAN NOT NULL
- ✅ `actor_type` в order_status_history - NOT NULL ✅

**Все поля присутствуют согласно схеме!**

---

### order_status_history (10 колонок)

**Записей:** 1

**Критичное поле:**
- ✅ `actor_type` - **NOT NULL** (фикс 5 применён)
- ✅ `context` - jsonb NOT NULL default '{}'

**Пример записи:**
```
id: 266
order_id: 305
from_status: SEARCHING
to_status: ASSIGNED
actor_type: MASTER
context: {"action": "offer_accepted", "method": "atomic_accept", "offer_id": 2898, "master_id": 3378}
```

---

### offers - критичные индексы ✅

**Записей:** 20 (1 ACCEPTED, 19 CANCELED)

**Partial Unique Index (защита от race condition):**
```sql
CREATE UNIQUE INDEX uix_offers__order_accepted_once 
ON offers (order_id) 
WHERE state = 'ACCEPTED'
```
**Статус:** ✅ РАБОТАЕТ

**Дополнительный unique constraint:**
```sql
CREATE UNIQUE INDEX uq_offers__order_master_active
ON offers (order_id, master_id)
WHERE state IN ('SENT', 'VIEWED', 'ACCEPTED')
```

---

### cities (8 колонок)

**Записей:** 3 (тестовые данные)

**Данные:**
```
id      | name              | timezone
--------|-------------------|-------------
999999  | ZZZ Seed City     | Europe/Moscow
1       | City #1           | Europe/Moscow  
1000000 | Москва Load Test  | Europe/Moscow
```

**Примечание:** В проде должно быть 79 городов. В тестах создаются через фикстуры.

---

### districts (6 колонок)

**Записей:** 2

**Данные:**
```
id      | city_id | name
--------|---------|------------------
999999  | 999999  | ZZZ Seed District
3460    | 1000000 | Центральный
```

---

### skills (3 колонки) ⚠️

**Записей:** 0

**ПРОБЛЕМА:** Справочник пуст!

**Требуется:** 6 навыков
- ELECTRICS
- PLUMBING
- APPLIANCES
- WINDOWS
- HANDYMAN
- ROADSIDE

**Решение:** Добавить в autouse фикстуру tests/conftest.py

---

### orders (36 колонок)

**Записей:** 1 (тестовый заказ)

**Пример:**
```
id: 305
city_id: 1000000 (Москва Load Test)
district_id: 3460 (Центральный)
status: ASSIGNED
assigned_master_id: 3378
type: NORMAL
category: ELECTRICS
total_sum: 0.00
no_district: false
```

---

### staff_users

**Записей:** 2

Это нормально - два пользователя персонала для тестов.

---

## Проблемы и рекомендации

### ❌ Критичные

1. **skills таблица пуста**
   - Тесты падают из-за FK violations
   - Решение: autouse seed в conftest.py

### ⚠️ Средние

2. **distribution_metrics owner = fs_user**
   - Ожидается: field_user
   - Риск: проблемы с миграциями

3. **cities/districts - минимальные данные**
   - Это нормально для тестов
   - Данные создаются через фикстуры

---

## Применённые миграции

**Версия:** `2025_10_16_0002`

**История:**
1. `4c2465ccb4e5` → базовая схема
2. `2025_10_16_0001` → commission_deadline_notifications
3. `2025_10_16_0002` → actor_type NOT NULL

**Статус:** ✅ Все актуальные миграции применены

---

## Следующие шаги

### Высокий приоритет
1. ✅ Миграция commission_deadline_notifications - DONE
2. ⚠️ Добавить seed для skills в autouse фикстуру
3. ⚠️ Проверить owner у distribution_metrics

### Средний приоритет  
4. Завершить maybe_managed_session для всех сервисов
5. Добавить @pytest.mark.asyncio где нужно

---

**Статус БД:** ✅ Готова к тестам, требуется только seed для skills

**Токенов осталось:** ~47,000 из 190,000
