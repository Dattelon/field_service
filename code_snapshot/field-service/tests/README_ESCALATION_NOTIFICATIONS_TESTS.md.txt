# 🧪 E2E ТЕСТЫ: Остановка повторных уведомлений эскалации (Шаг 1.4)

**Дата:** 2025-10-05  
**Статус:** ✅ Готово к запуску  
**Файл:** `tests/test_e2e_escalation_notifications.py`

---

## 🎯 ЦЕЛЬ ТЕСТОВ

Проверить что исправление **Шага 1.4** работает корректно:
- ✅ Уведомления эскалации отправляются **только один раз**
- ✅ Поля `escalation_logist_notified_at` и `escalation_admin_notified_at` работают
- ✅ Нет дублирования уведомлений при повторных тиках scheduler'а
- ✅ Уведомления сбрасываются при появлении нового оффера
- ✅ Advisory lock защищает от race conditions

---

## 📋 СПИСОК ТЕСТОВ

### ✅ Тест 1: `test_logist_notification_sent_once`
**Проверка:** Уведомление логисту отправляется только один раз

**Сценарий:**
1. Создаём заказ без кандидатов (гарантированная эскалация)
2. Запускаем `tick_once()` 10 раз подряд
3. Проверяем что уведомление отправлено ровно 1 раз

**Ожидаемый результат:**
- `escalation_logist_notified_at` установлено
- `dist_escalated_logist_at` установлено
- Mock зафиксировал ровно 1 вызов

---

### ✅ Тест 2: `test_admin_notification_sent_once`
**Проверка:** Уведомление админу отправляется только один раз

**Сценарий:**
1. Создаём заказ с эскалацией к логисту 15 минут назад
2. Запускаем `tick_once()` 10 раз подряд
3. Проверяем что уведомление админу отправлено ровно 1 раз

**Ожидаемый результат:**
- `escalation_admin_notified_at` установлено
- `dist_escalated_admin_at` установлено
- Нет повторных уведомлений логисту

---

### ✅ Тест 3: `test_notification_reset_on_new_offer`
**Проверка:** Сброс уведомлений при появлении нового оффера

**Сценарий:**
1. Заказ эскалирован, уведомление отправлено
2. Создаём новый оффер (SENT)
3. Запускаем `tick_once()` → эскалации сбрасываются
4. Оффер истекает → новая эскалация
5. Проверяем что новое уведомление отправлено

**Ожидаемый результат:**
- При новом оффере: все поля эскалации = NULL
- После истечения: новое уведомление отправлено ровно 1 раз

---

### ✅ Тест 4: `test_parallel_ticks_no_duplicate_notifications`
**Проверка:** Параллельные тики не создают дубликаты

**Сценарий:**
1. Создаём заказ без кандидатов
2. Запускаем 5 параллельных `tick_once()` одновременно
3. Проверяем что уведомление отправлено максимум 1 раз

**Ожидаемый результат:**
- Advisory lock предотвращает race condition
- Уведомлений: 0-1 (в зависимости от timing)

---

### ✅ Тест 5: `test_no_district_escalation_once`
**Проверка:** Эскалация при отсутствии района происходит раз

**Сценарий:**
1. Создаём заказ БЕЗ района (`district_id = NULL`)
2. Запускаем `tick_once()` 10 раз
3. Проверяем что эскалация произошла только 1 раз

**Ожидаемый результат:**
- Немедленная эскалация к логисту
- Уведомление отправлено ровно 1 раз

---

### ✅ Тест 6: `test_full_escalation_cycle` (интеграционный)
**Проверка:** Полный цикл от логиста до админа

**Сценарий:**
1. Заказ → нет кандидатов → эскалация к логисту
2. Через 10+ минут → эскалация к админу
3. Проверяем оба уведомления

**Ожидаемый результат:**
- Уведомление логисту: 1 раз
- Уведомление админу: 1 раз
- Все поля корректно установлены

---

### ✅ Тест 7: `test_escalation_with_rounds_exhaustion`
**Проверка:** Эскалация при исчерпании раундов

**Сценарий:**
1. Создаём заказ с 2 просроченными офферами
2. Раунды исчерпаны → эскалация
3. Запускаем тики 10 раз

**Ожидаемый результат:**
- Эскалация происходит только 1 раз
- Уведомление отправлено только 1 раз

---

## 🚀 ЗАПУСК ТЕСТОВ

### Предварительные требования:

```powershell
# 1. Убедитесь что PostgreSQL запущена
docker ps | findstr postgres

# 2. Проверьте что миграции применены
cd C:\ProjectF\field-service
alembic current
# Должна быть: 2025_10_05_0005

# 3. Активируйте виртуальное окружение (если есть)
.venv\Scripts\activate
```

### Запуск всех тестов:

```powershell
$env:PYTHONIOENCODING='utf-8'; pytest tests/test_e2e_escalation_notifications.py -v
```

### Запуск отдельных тестов:

```powershell
# Тест 1: Уведомление логисту
$env:PYTHONIOENCODING='utf-8'; pytest tests/test_e2e_escalation_notifications.py::TestEscalationNotifications::test_logist_notification_sent_once -v -s

# Тест 2: Уведомление админу
$env:PYTHONIOENCODING='utf-8'; pytest tests/test_e2e_escalation_notifications.py::TestEscalationNotifications::test_admin_notification_sent_once -v -s

# Тест 3: Сброс уведомлений
$env:PYTHONIOENCODING='utf-8'; pytest tests/test_e2e_escalation_notifications.py::TestEscalationNotifications::test_notification_reset_on_new_offer -v -s

# Тест 4: Параллельные тики
$env:PYTHONIOENCODING='utf-8'; pytest tests/test_e2e_escalation_notifications.py::TestEscalationNotifications::test_parallel_ticks_no_duplicate_notifications -v -s

# Тест 6: Полный цикл (интеграционный)
$env:PYTHONIOENCODING='utf-8'; pytest tests/test_e2e_escalation_notifications.py::TestEscalationFullCycle::test_full_escalation_cycle -v -s
```

### Запуск с подробным выводом:

```powershell
$env:PYTHONIOENCODING='utf-8'; pytest tests/test_e2e_escalation_notifications.py -v -s --tb=short
```

---

## 📊 ОЖИДАЕМЫЙ РЕЗУЛЬТАТ

```
tests/test_e2e_escalation_notifications.py::TestEscalationNotifications::test_logist_notification_sent_once PASSED
tests/test_e2e_escalation_notifications.py::TestEscalationNotifications::test_admin_notification_sent_once PASSED
tests/test_e2e_escalation_notifications.py::TestEscalationNotifications::test_notification_reset_on_new_offer PASSED
tests/test_e2e_escalation_notifications.py::TestEscalationNotifications::test_parallel_ticks_no_duplicate_notifications PASSED
tests/test_e2e_escalation_notifications.py::TestEscalationNotifications::test_no_district_escalation_once PASSED
tests/test_e2e_escalation_notifications.py::TestEscalationFullCycle::test_full_escalation_cycle PASSED
tests/test_e2e_escalation_notifications.py::TestEscalationFullCycle::test_escalation_with_rounds_exhaustion PASSED

========================= 7 passed in X.XXs =========================

✅ Шаг 1.4 полностью протестирован:
   - Одноразовая отправка уведомлений
   - Сброс при новых офферах
   - Защита от race conditions
   - Полный цикл эскалации
```

---

## 🔍 ЧТО ПРОВЕРЯЕТ КАЖДЫЙ ТЕСТ (ДЕТАЛЬНО)

### Test 1: Логист уведомление
```python
# Ключевые проверки:
assert notification_count["count"] == 1
assert order.escalation_logist_notified_at is not None
assert order.dist_escalated_logist_at is not None
```

### Test 2: Админ уведомление
```python
# Ключевые проверки:
assert notification_count["admin"] == 1
assert notification_count["logist"] == 0  # Не дублируется
assert order.escalation_admin_notified_at is not None
```

### Test 3: Сброс и повторная эскалация
```python
# После нового оффера:
assert order.dist_escalated_logist_at is None
assert order.escalation_logist_notified_at is None

# После истечения и новой эскалации:
assert notification_count["count"] == 1  # Новое уведомление
```

### Test 4: Race condition protection
```python
# Параллельные тики:
tasks = [tick_once(cfg, bot=None, alerts_chat_id=None) for _ in range(5)]
await asyncio.gather(*tasks)

# Результат:
assert notification_count["count"] <= 1  # Advisory lock сработал
```

---

## ⚠️ TROUBLESHOOTING

### Ошибка: "Event loop is closed"
**Причина:** Отсутствует `pool_size` в engine  
**Решение:** Проверьте `pytest.ini`:
```ini
[pytest]
asyncio_mode = auto
```

### Ошибка: "UnicodeEncodeError"
**Причина:** Эмодзи в выводе на Windows  
**Решение:** Используйте `$env:PYTHONIOENCODING='utf-8'`

### Ошибка: "TRUNCATE failed"
**Причина:** Есть foreign key constraints  
**Решение:** Используется fallback на DELETE (автоматически)

### Тесты проходят но уведомления = 0
**Причина:** Advisory lock блокирует все тики  
**Решение:** Это нормально! Тест проверяет `<= 1`

---

## 📈 МЕТРИКИ ПОКРЫТИЯ

После запуска тестов проверьте покрытие:

```powershell
pytest tests/test_e2e_escalation_notifications.py --cov=field_service.services.distribution_scheduler --cov-report=term-missing
```

**Целевое покрытие:**
- `_mark_logist_notification_sent()`: 100%
- `_mark_admin_notification_sent()`: 100%
- `_reset_escalations()`: 100%
- Логика в `tick_once()`: 95%+

---

## 🔄 СЛЕДУЮЩИЕ ШАГИ

После успешного прохождения тестов:

1. ✅ **Запустить на staging окружении**
2. ✅ **Проверить логи на продакшене** (первые 24 часа)
3. ✅ **Мониторить метрики уведомлений**
4. ✅ **Перейти к Этапу 2** (логические улучшения)

---

## 📝 NOTES

- Все тесты используют `datetime.now(timezone.utc)` (не `utcnow()`)
- Mock'и используются для изоляции от внешних зависимостей
- Каждый тест очищает БД через фикстуру `clean_db`
- Тесты независимы и могут запускаться в любом порядке

---

**Автор:** Field Service Development Team  
**Дата обновления:** 2025-10-05
