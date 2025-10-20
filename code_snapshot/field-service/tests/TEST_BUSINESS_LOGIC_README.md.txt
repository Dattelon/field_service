# Комплексные тесты бизнес-логики

## 📋 Что тестируется

Полный набор интеграционных тестов, покрывающих все аспекты бизнес-логики системы:

### ✅ test_full_business_logic.py

**Основные интеграционные сценарии:**

1. **test_full_order_lifecycle_with_commission** - Полный цикл заказа
   - Создание заказа SEARCHING
   - Автораспределение (tick_once)
   - Отправка оффера мастеру
   - Принятие оффера
   - Смена статусов: ASSIGNED → EN_ROUTE → WORKING → PAYMENT
   - Создание комиссии 50%

2. **test_distribution_two_rounds_with_sla_timeout** - Двухраундовое распределение
   - Раунд 1: Мастер получает оффер, не отвечает
   - Истечение SLA (EXPIRED)
   - Раунд 2: Второй мастер получает оффер

3. **test_guarantee_order_with_preferred_master** - Гарантийные заказы
   - type=GUARANTEE
   - preferred_master_id указан
   - Приоритет preferred мастера
   - Комиссия НЕ создаётся (company_payment)

4. **test_high_avg_check_master_gets_40_percent_commission** - Расчёт комиссии 40%
   - avg_week_check >= 7000 руб
   - Комиссия 40% вместо 50%

5. **test_no_candidates_leads_to_escalation_logist** - Эскалация к логисту
   - Нет мастеров с нужным навыком
   - 2 раунда без кандидатов
   - dist_escalated_logist_at устанавливается

6. **test_escalation_to_admin_after_timeout** - Эскалация к админу
   - Эскалация к логисту
   - 10+ минут без назначения
   - dist_escalated_admin_at устанавливается

7. **test_master_cannot_receive_duplicate_offers** - Защита от дублей
   - Мастер получил оффер
   - Оффер истёк
   - Повторный оффер НЕ отправляется

8. **test_status_history_tracking** - История статусов
   - Запись в order_status_history
   - Полный цикл CREATED → CLOSED

9. **test_multiple_masters_ranking** - Ранжирование мастеров
   - 3 мастера с разными параметрами
   - Приоритет: has_vehicle > rating > avg_week_check

10. **test_master_on_break_cannot_receive_offers** - Перерыв
    - shift_status=BREAK
    - break_until в будущем
    - Мастер пропускается

### ✅ test_business_logic_edge_cases.py

**Граничные случаи и специальные сценарии:**

1. **test_master_max_active_orders_limit** - Лимит активных заказов
   - max_active_orders_override=2
   - 2 активных заказа
   - Новый заказ НЕ распределяется

2. **test_commission_overdue_blocks_master** - Блокировка при просрочке
   - Комиссия WAIT_PAY с истёкшим дедлайном
   - apply_overdue_commissions()
   - Мастер блокируется (is_blocked=True)

3. **test_order_without_district_fallback_to_city** - Fallback на город
   - district_id=None
   - Мастер в другом районе города
   - Распределение находит мастера (поиск по городу)

4. **test_different_categories_require_different_skills** - Навыки по категориям
   - Мастер с ELEC
   - Заказ PLUMBING
   - Распределение НЕ находит мастера

5. **test_master_with_multiple_skills_and_districts** - Универсальный мастер
   - 2 навыка (ELEC + PLUMB)
   - 2 района
   - Распределение для обоих категорий в обоих районах

6. **test_commission_deadline_notifications_table** - Уведомления о дедлайне
   - Таблица commission_deadline_notifications
   - hours_before: 24, 6, 1
   - UNIQUE constraint (commission_id, hours_before)

7. **test_order_with_timeslot_priority** - Приоритет просроченных слотов
   - Заказ с timeslot в прошлом
   - Заказ без timeslot (создан раньше)
   - Приоритет просроченному

8. **test_idempotent_commission_creation** - Идемпотентность
   - Повторный вызов create_for_order
   - Возвращается та же комиссия

9. **test_distribution_metrics_creation** - Метрики распределения
   - Запись в distribution_metrics
   - Проверка полей

## 🚀 Запуск тестов

### Запуск всех тестов
```powershell
$env:PYTHONIOENCODING='utf-8'; pytest tests/test_full_business_logic.py tests/test_business_logic_edge_cases.py -v -s
```

### Запуск отдельного теста
```powershell
$env:PYTHONIOENCODING='utf-8'; pytest tests/test_full_business_logic.py::test_full_order_lifecycle_with_commission -v -s
```

### Запуск с отчётом о покрытии
```powershell
$env:PYTHONIOENCODING='utf-8'; pytest tests/test_full_business_logic.py tests/test_business_logic_edge_cases.py --cov=field_service --cov-report=html -v
```

### Запуск только быстрых тестов (без sleep)
```powershell
$env:PYTHONIOENCODING='utf-8'; pytest tests/test_full_business_logic.py tests/test_business_logic_edge_cases.py -v -m "not slow"
```

## 📊 Покрытие

Эти тесты покрывают:

### Модели БД
- ✅ orders (все статусы, типы, категории)
- ✅ offers (все состояния, раунды, SLA)
- ✅ commissions (статусы, расчёт ставок, дедлайны)
- ✅ masters (навыки, районы, лимиты, блокировка)
- ✅ order_status_history (запись истории)
- ✅ commission_deadline_notifications (уведомления)
- ✅ distribution_metrics (метрики)

### Сервисы
- ✅ distribution_scheduler.py (автораспределение)
- ✅ commission_service.py (создание комиссий)
- ✅ candidates.py (подбор кандидатов)
- ✅ settings_service.py (конфигурация)

### Бизнес-логика
- ✅ Создание заказов в БД
- ✅ Автораспределение офферов (2 раунда)
- ✅ Смену статусов (полный lifecycle)
- ✅ Создание комиссий (50%/40%)
- ✅ Гарантийные заказы
- ✅ Эскалации (логист/админ)
- ✅ Ранжирование мастеров
- ✅ Работу с районами и навыками

## 🔧 Требования

### БД
Тесты используют PostgreSQL (не SQLite):
```yaml
TEST_DATABASE_URL=postgresql+asyncpg://fs_user:fs_password@localhost:5439/field_service_test
```

### Зависимости
- pytest>=7.0.0
- pytest-asyncio>=0.21.0
- sqlalchemy>=2.0.0
- asyncpg>=0.27.0

### Конфигурация
Файл `pytest.ini` должен содержать:
```ini
[pytest]
pythonpath = .
asyncio_mode = auto
```

## 📝 Правила написания тестов

### КРИТИЧНО
1. **Datetime**: ТОЛЬКО `datetime.now(timezone.utc)`, НИКОГДА `datetime.utcnow()`
2. **Кэш SQLAlchemy**: ВСЕГДА `session.expire_all()` перед `await session.refresh(obj)`
3. **MissingGreenlet**: Сохранять `.id` ПЕРЕД `expire_all()`, не обращаться к lazy-loaded после
4. **Кодировка**: БЕЗ эмодзи в print/комментариях (Windows cp1251)
5. **Очистка БД**: TRUNCATE CASCADE с fallback на DELETE

### Паттерны
```python
# ❌ WRONG - читаем устаревшие данные
await session.refresh(order)
assert order.status == "ASSIGNED"

# ✅ CORRECT - expire перед refresh
session.expire_all()
await session.refresh(order)
assert order.status == "ASSIGNED"

# ❌ WRONG - Python время не синхронно с БД
order_time = datetime.now(timezone.utc) - timedelta(hours=1)

# ✅ CORRECT - используем время БД
async def _get_db_now(session):
    row = await session.execute(text("SELECT NOW()"))
    return row.scalar()

db_now = await _get_db_now(session)
order_time = db_now - timedelta(hours=1)

# ❌ WRONG - обращение после expire
session.expire_all()
print(offer.master_id)  # MissingGreenlet!

# ✅ CORRECT - сохранить ID перед expire
offer_id = offer.id
master_id = offer.master_id
session.expire_all()
print(f"Offer {offer_id}, Master {master_id}")
```

## 🐛 Типичные ошибки

1. **"Event loop is closed"** → отсутствует pool_size в engine или дубликат fixtures
2. **"UnicodeEncodeError"** → эмодзи в print/комментариях
3. **"can't compare datetime"** → смешивание utcnow() и now(UTC)
4. **"TRUNCATE failed"** → нет fallback на DELETE в except
5. **"MissingGreenlet"** → обращение к атрибутам после expire_all()
6. **Устаревшие данные** → нет expire_all() перед refresh

## 📈 Результаты

После запуска всех тестов вы должны увидеть:

```
tests/test_full_business_logic.py::test_full_order_lifecycle_with_commission PASSED
tests/test_full_business_logic.py::test_distribution_two_rounds_with_sla_timeout PASSED
tests/test_full_business_logic.py::test_guarantee_order_with_preferred_master PASSED
tests/test_full_business_logic.py::test_high_avg_check_master_gets_40_percent_commission PASSED
tests/test_full_business_logic.py::test_no_candidates_leads_to_escalation_logist PASSED
tests/test_full_business_logic.py::test_escalation_to_admin_after_timeout PASSED
tests/test_full_business_logic.py::test_master_cannot_receive_duplicate_offers PASSED
tests/test_full_business_logic.py::test_status_history_tracking PASSED
tests/test_full_business_logic.py::test_multiple_masters_ranking PASSED
tests/test_full_business_logic.py::test_master_on_break_cannot_receive_offers PASSED

tests/test_business_logic_edge_cases.py::test_master_max_active_orders_limit PASSED
tests/test_business_logic_edge_cases.py::test_commission_overdue_blocks_master PASSED
tests/test_business_logic_edge_cases.py::test_order_without_district_fallback_to_city PASSED
tests/test_business_logic_edge_cases.py::test_different_categories_require_different_skills PASSED
tests/test_business_logic_edge_cases.py::test_master_with_multiple_skills_and_districts PASSED
tests/test_business_logic_edge_cases.py::test_commission_deadline_notifications_table PASSED
tests/test_business_logic_edge_cases.py::test_order_with_timeslot_priority PASSED
tests/test_business_logic_edge_cases.py::test_idempotent_commission_creation PASSED
tests/test_business_logic_edge_cases.py::test_distribution_metrics_creation PASSED

==================== 19 passed in X.XXs ====================
```

## 🎯 Что дальше

После успешного прохождения этих тестов можно:
1. Добавить тесты на рефералку (10%/5%)
2. Добавить тесты на экспорты (CSV/XLSX)
3. Добавить нагрузочные тесты (1000+ заказов)
4. Добавить тесты на уведомления (push, email)
5. Добавить тесты на админ-бот (модерация, финансы)

## 📞 Поддержка

При проблемах с тестами:
1. Проверьте БД (должна быть доступна)
2. Проверьте `pytest.ini` (asyncio_mode = auto)
3. Проверьте что нет дублирующих fixtures
4. Используйте `-v -s` для детального вывода
5. Проверьте логи в `tests/*.log`
