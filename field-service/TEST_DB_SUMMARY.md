# 📊 Сводка по тестовой БД field_service_test

**Дата:** 2025-10-16  
**Полный отчёт:** `TEST_DB_FULL_REPORT.md` (1078 строк, 162 КБ)

---

## ✅ Статус БД

**Версия миграций:** `2025_10_16_0002` (актуальная)  
**Таблиц:** 27  
**Контейнер:** field-service-postgres-1 (postgres:15-alpine)  
**Порт:** 5439 → 5432

---

## 📊 Таблицы и данные

| # | Таблица | Записей | Комментарий |
|---|---------|----------|-------------|
| 1 | admin_audit_log | 0 | Аудит действий администраторов |
| 2 | alembic_version | 1 | ✅ Версия 2025_10_16_0002 |
| 3 | attachments | 0 | Вложения к заказам/комиссиям |
| 4 | cities | 3 | ⚠️ Тестовые данные (ZZZ Seed City, City #1, Москва Load Test) |
| 5 | **commission_deadline_notifications** | 0 | **✅ СОЗДАНА миграцией 2025_10_16_0001** |
| 6 | commissions | 0 | Комиссии мастеров |
| 7 | distribution_metrics | 0 | Метрики распределения (owner: **fs_user** ⚠️) |
| 8 | districts | 2 | ZZZ Seed District, Центральный |
| 9 | geocache | 0 | Кэш геокодирования |
| 10 | master_districts | 0 | М2М: Мастера ↔ Районы |
| 11 | master_invite_codes | 0 | Пригласительные коды |
| 12 | master_skills | 0 | М2М: Мастера ↔ Навыки |
| 13 | masters | 20 | ✅ Load Test Masters (10000-10019) |
| 14 | notifications_outbox | 0 | Очередь уведомлений |
| 15 | offers | 20 | ✅ Тестовые офферы (1 ACCEPTED, 19 CANCELED) |
| 16 | order_autoclose_queue | 0 | Очередь автозакрытия |
| 17 | order_status_history | 1 | ✅ История перехода SEARCHING → ASSIGNED |
| 18 | orders | 1 | ✅ Тестовый заказ #305 (ASSIGNED) |
| 19 | referral_rewards | 0 | Реферальные начисления |
| 20 | referrals | 0 | Реферальные связи |
| 21 | settings | 0 | Настройки системы |
| 22 | skills | 0 | ⚠️ Навыки (справочник ПУСТ!) |
| 23 | staff_access_code_cities | 0 | М2М: Коды доступа ↔ Города |
| 24 | staff_access_codes | 0 | Коды доступа персонала |
| 25 | staff_cities | 0 | М2М: Персонал ↔ Города |
| 26 | staff_users | 2 | ✅ Два пользователя персонала |
| 27 | streets | 0 | Улицы |

---

## 🔍 Ключевые индексы и констрейнты

### ✅ Критичные индексы (есть)

1. **offers.uix_offers__order_accepted_once** - partial unique index  
   ```sql
   UNIQUE (order_id) WHERE state = 'ACCEPTED'
   ```
   Предотвращает двойное принятие оффера ✅

2. **offers.uq_offers__order_master_active** - partial unique constraint  
   ```sql
   UNIQUE (order_id, master_id) WHERE state IN ('SENT', 'VIEWED', 'ACCEPTED')
   ```

3. **commission_deadline_notifications индексы:**
   ```sql
   - PRIMARY KEY (id)
   - INDEX (commission_id)
   - UNIQUE (commission_id, hours_before)
   ```

### ✅ masters таблица

- **37 колонок** (включая все необходимые поля)
- ✅ **tg_user_id** есть (NO NULL constraint для тестов)
- ✅ **full_name** есть (NOT NULL)
- ❌ **patronymic** нет (не нужна, используем full_name)
- ✅ **is_on_shift**, **verified**, **is_deleted** есть

### ✅ order_status_history

- **10 колонок**
- ✅ **actor_type** - **NOT NULL** (фикс 5 применён)
- ✅ **context** - **jsonb NOT NULL** default '{}'

---

## ⚠️ Проблемы и требования

### 1. ❌ Пустой справочник skills
**Записей:** 0  
**Требуется:** 6 навыков (ELECTRICS, PLUMBING, APPLIANCES, WINDOWS, HANDYMAN, ROADSIDE)  
**Решение:** Улучшить autouse фикстуру в tests/conftest.py

### 2. ⚠️ Владелец distribution_metrics
**Текущий:** fs_user  
**Ожидаемый:** field_user  
**Риск:** Возможные проблемы с правами доступа при миграциях

### 3. ⚠️ Минимальные тестовые данные
**cities:** 3 записи (тестовые, не 79 городов)  
**districts:** 2 записи  
**streets:** 0 записей

**Причина:** Тесты используют фабрики для создания данных "на лету"  
**Это нормально:** Каждый тест создаёт свои данные через фикстуры

---

## ✅ Что уже исправлено

1. ✅ **commission_deadline_notifications таблица создана**  
   - Миграция 2025_10_16_0001 применена
   - Все индексы и констрейнты на месте

2. ✅ **actor_type NOT NULL**  
   - Миграция 2025_10_16_0002 применена
   - Default value: SYSTEM

3. ✅ **Partial unique index на offers**  
   - uix_offers__order_accepted_once работает
   - Предотвращает race condition при двойном принятии

4. ✅ **Структура masters полная**  
   - Все 37 колонок на месте
   - tg_user_id, full_name, is_on_shift, verified, is_deleted

---

## 📝 Следующие шаги

### Высокий приоритет
1. ⚠️ Добавить seed для **skills** в autouse фикстуру
2. ⚠️ Проверить/исправить owner у distribution_metrics (fs_user → field_user)

### Средний приоритет  
3. Завершить применение maybe_managed_session ко всем сервисам
4. Добавить @pytest.mark.asyncio где нужно

---

## 🔗 Связанные файлы

- **TEST_DB_FULL_REPORT.md** - полный отчёт со структурой всех таблиц (1078 строк)
- **TEST_DB_REPORT.md** - краткий отчёт с выводами
- **FIXES_SUMMARY.md** - сводка по применённым фиксам 1-6
- **generate_db_report.sh** - скрипт для генерации отчёта

---

**Токенов осталось:** ~50,000 из 190,000
