# 🧪 E2E ТЕСТЫ: Проверка остановки повторных уведомлений эскалации (Шаг 1.4)

**Дата создания:** 2025-10-06  
**Статус:** ✅ Готово к запуску  
**Файл тестов:** `tests/test_e2e_escalation_notifications.py`

---

## 📋 ОПИСАНИЕ

Нагрузочные тесты для проверки **Шага 1.4**: остановка повторных уведомлений эскалации.

### ✅ Проверяемое исправление

**Проблема:**  
При каждом тике scheduler'а (каждые 30 секунд) отправлялось уведомление об эскалации, даже если оно уже было отправлено ранее.

**Решение:**
- Добавлены поля `escalation_logist_notified_at` и `escalation_admin_notified_at`
- Уведомление отправляется только один раз
- При сбросе эскалации (новый оффер) флаги очищаются

---

## 🎯 ПРОВЕРЯЕМЫЕ СЦЕНАРИИ

### ✅ Тест 1: Уведомление логисту отправляется только один раз
**Сценарий:**
1. Создаём заказ без кандидатов (эскалация неизбежна)
2. Запускаем `tick_once()` 10 раз подряд
3. Проверяем что уведомление отправлено только 1 раз

**Проверки:**
- ✅ `escalation_logist_notified_at` устанавливается
- ✅ Уведомление отправлено ровно 1 раз
- ✅ Повторные тики не вызывают дублирование

---

### ✅ Тест 2: Уведомление админу отправляется только один раз
**Сценарий:**
1. Заказ эскалирован к логисту 15 минут назад
2. Запускаем `tick_once()` 10 раз подряд
3. Проверяем что уведомление админу отправлено только 1 раз

**Проверки:**
- ✅ `escalation_admin_notified_at` устанавливается
- ✅ Уведомление отправлено ровно 1 раз
- ✅ Эскалация происходит после `to_admin_after_min` минут

---

### ✅ Тест 3: Сброс уведомлений при новом оффере
**Сценарий:**
1. Заказ эскалирован (уведомление отправлено)
2. Приходит новый оффер (SENT)
3. Эскалация сбрасывается
4. Оффер истекает
5. Заказ эскалируется снова
6. Уведомление отправляется повторно

**Проверки:**
- ✅ При активном оффере эскалация сбрасывается
- ✅ `escalation_logist_notified_at` сбрасывается в NULL
- ✅ При повторной эскалации уведомление отправляется снова

---

### ✅ Тест 4: Параллельные тики не вызывают дублирование
**Сценарий:**
1. Создаём заказ без кандидатов
2. Запускаем 5 параллельных `tick_once()`
3. Проверяем что уведомление отправлено максимум 1 раз

**Проверки:**
- ✅ Advisory lock предотвращает race condition
- ✅ Только один тик отправляет уведомление
- ✅ Нет дублирования `escalation_logist_notified_at`

---

### ✅ Тест 5: Заказы без района (no_district)
**Сценарий:**
1. Заказ с `district_id = NULL`
2. Запускаем `tick_once()` 10 раз
3. Проверяем одноразовую отправку уведомления

**Проверки:**
- ✅ Немедленная эскалация к логисту
- ✅ Уведомление отправлено только 1 раз
- ✅ Флаг `escalation_logist_notified_at` установлен

---

### ✅ Тест 6: Заказы без категории
**Сценарий:**
1. Заказ с `category = NULL`
2. Запускаем `tick_once()` 10 раз
3. Проверяем одноразовую отправку уведомления

**Проверки:**
- ✅ Немедленная эскалация к логисту
- ✅ Уведомление отправлено только 1 раз

---

### ✅ Тест 7: Исчерпание раундов
**Сценарий:**
1. Заказ с 2 истёкшими офферами (раунды исчерпаны)
2. Запускаем `tick_once()` 10 раз
3. Проверяем одноразовую отправку уведомления

**Проверки:**
- ✅ Эскалация после исчерпания раундов
- ✅ Уведомление отправлено только 1 раз

---

## 🚀 ЗАПУСК ТЕСТОВ

### Предварительные требования

```bash
# 1. Перейдите в директорию проекта
cd C:\ProjectF\field-service

# 2. Активируйте виртуальное окружение (если используется)
.venv\Scripts\activate  # Windows

# 3. Убедитесь что зависимости установлены
pip install pytest pytest-asyncio sqlalchemy aiosqlite
```

---

### Запуск всех тестов

```powershell
# Windows PowerShell (рекомендуется)
$env:PYTHONIOENCODING='utf-8'; pytest tests/test_e2e_escalation_notifications.py -v -s
```

---

### Запуск конкретного теста

```powershell
# Тест 1: Уведомление логисту
$env:PYTHONIOENCODING='utf-8'; pytest tests/test_e2e_escalation_notifications.py::TestEscalationNotifications::test_logist_notification_sent_once -v -s

# Тест 2: Уведомление админу
$env:PYTHONIOENCODING='utf-8'; pytest tests/test_e2e_escalation_notifications.py::TestEscalationNotifications::test_admin_notification_sent_once -v -s

# Тест 3: Сброс при новом оффере
$env:PYTHONIOENCODING='utf-8'; pytest tests/test_e2e_escalation_notifications.py::TestEscalationNotifications::test_notification_reset_on_new_offer -v -s

# Тест 4: Параллельные тики
$env:PYTHONIOENCODING='utf-8'; pytest tests/test_e2e_escalation_notifications.py::TestEscalationNotifications::test_parallel_ticks_no_duplicate_notifications -v -s
```

---

## 📊 ОЖИДАЕМЫЙ РЕЗУЛЬТАТ

```
tests/test_e2e_escalation_notifications.py::TestEscalationNotifications::test_logist_notification_sent_once PASSED
tests/test_e2e_escalation_notifications.py::TestEscalationNotifications::test_admin_notification_sent_once PASSED
tests/test_e2e_escalation_notifications.py::TestEscalationNotifications::test_notification_reset_on_new_offer PASSED
tests/test_e2e_escalation_notifications.py::TestEscalationNotifications::test_parallel_ticks_no_duplicate_notifications PASSED
tests/test_e2e_escalation_notifications.py::TestEscalationNotifications::test_no_district_escalation_notification_once PASSED
tests/test_e2e_escalation_notifications.py::TestEscalationNotifications::test_no_category_escalation_notification_once PASSED
tests/test_e2e_escalation_notifications.py::TestEscalationNotifications::test_rounds_exhausted_escalation_notification_once PASSED

========================= 7 passed in X.XXs =========================

✅ Все тесты Шага 1.4 пройдены:
   - Уведомления отправляются только один раз
   - Сброс работает корректно
   - Нет race condition при параллельных тиках
```

---

## 🔍 АНАЛИЗ РЕЗУЛЬТАТОВ

### ✅ Успешное прохождение означает:

1. **Нет дублирования уведомлений**
   - Логист получает уведомление только 1 раз
   - Админ получает уведомление только 1 раз
   - Повторные тики не вызывают spam

2. **Корректная работа сброса**
   - При новом оффере эскалация сбрасывается
   - Флаги `escalation_*_notified_at` очищаются
   - При повторной эскалации уведомление отправляется снова

3. **Защита от race condition**
   - Advisory lock работает корректно
   - Параллельные тики не вызывают дублирование
   - Только один процесс обрабатывает заказ

---

## ⚠️ TROUBLESHOOTING

### Проблема: `ImportError: cannot import name 'tick_once'`

**Причина:** Неправильный путь импорта

**Решение:**
```python
# Убедитесь что импорт выглядит так:
from field_service.services.distribution_scheduler import tick_once, DistConfig
```

---

### Проблема: `Fixture 'sample_city' not found`

**Причина:** Фикстуры не добавлены в `conftest.py`

**Решение:**
```bash
# Убедитесь что conftest.py содержит фикстуры:
# - sample_city
# - sample_district
# - sample_skill
# - sample_master
```

---

### Проблема: `AttributeError: 'orders' object has no attribute 'escalation_logist_notified_at'`

**Причина:** Миграция `2025_10_05_0005` не применена

**Решение:**
```bash
# Примените миграцию
cd C:\ProjectF\field-service
alembic upgrade head
```

---

## 📈 МЕТРИКИ ПРОИЗВОДИТЕЛЬНОСТИ

Ожидаемое время выполнения:
- **Все 7 тестов:** ~3-5 секунд
- **Один тест:** ~0.3-0.7 секунд

Если тесты выполняются дольше:
- Проверьте нагрузку на систему
- Убедитесь что БД не перегружена

---

## 🔄 NEXT STEPS

После успешного прохождения тестов:

1. ✅ **Шаг 1.4 завершён**
2. ➡️ **Переход к Этапу 2:** Логические улучшения
3. ➡️ **Шаг 2.1:** Приоритизация заказов в очереди

---

## 📝 CHANGELOG

**2025-10-06:**
- ✅ Созданы тесты для Шага 1.4
- ✅ Добавлены фикстуры в `conftest.py`
- ✅ 7 тестовых сценариев покрывают все случаи эскалации

---

**Автор:** Ведущий разработчик проекта  
**Версия:** 1.0  
**Проект:** Field Service Management System
