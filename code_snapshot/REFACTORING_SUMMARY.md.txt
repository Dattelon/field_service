# Рефакторинг test_e2e_escalation_debug.py

## Цель рефакторинга
Избавиться от зависаний на TRUNCATE и сделать тест идемпотентным, быстрым и совместимым с общими фикстурами.

## Проблемы до рефакторинга
1. **Собственные фикстуры**: тест создавал свой `SessionLocal()` вместо использования общих фикстур
2. **TRUNCATE блокировки**: ручная очистка БД через TRUNCATE могла вызывать блокировки
3. **Дублирование кода**: фикстуры `sample_city`, `sample_district`, `sample_skill` были дублированы
4. **Нет таймаутов**: тест мог зависнуть навсегда

## Изменения

### 1. test_e2e_escalation_debug.py
**Удалено:**
- Локальная фикстура `session()` с `SessionLocal()`
- Локальная фикстура `clean_db()` с ручными TRUNCATE
- Локальные фикстуры `sample_city()`, `sample_district()`, `sample_skill()`
- Импорт `pytest_asyncio`, `asyncio`, `timezone`
- Импорт `SessionLocal`

**Изменено:**
- Параметр `session` → `async_session` (использует общую фикстуру из conftest.py)
- Все обращения к `session` → `async_session`
- Добавлены type hints для фикстур (`: m.cities`, `: m.districts`, `: m.skills`)

**Как работает теперь:**
1. `async_session` из conftest.py автоматически очищает БД перед тестом (через TRUNCATE в одной транзакции)
2. Стандартные фикстуры `sample_city`, `sample_district`, `sample_skill` создаются из conftest.py
3. Автопатчинг `tick_once` из conftest.py обеспечивает использование тестовой сессии

### 2. pytest.ini (новый файл)
```ini
[pytest]
timeout = 60
asyncio_mode = strict
```

**Что делает:**
- `timeout = 60`: автоматически прерывает зависшие тесты через 60 секунд
- `asyncio_mode = strict`: строгий режим для async тестов (требуется pytest-asyncio)

## Архитектура общих фикстур (conftest.py)

```
engine (session-scoped)
  └─> async_session (function-scoped)
        ├─> Очистка БД через _clean_database() (TRUNCATE CASCADE)
        ├─> PatchedAsyncSession с умным expire_all()
        └─> Автоматический rollback после теста

Стандартные фикстуры:
  - sample_city
  - sample_district  
  - sample_skill
  - sample_master (с привязкой к skill и district)

Автопатчинг:
  - distribution_scheduler.tick_once → использует async_session
  - session_module.engine → тестовый engine
```

## Преимущества после рефакторинга

1. **Нет блокировок**: централизованная очистка БД в conftest.py без конкуренции
2. **Быстрее**: один TRUNCATE CASCADE вместо множества отдельных операций
3. **Идемпотентность**: каждый тест получает чистую БД автоматически
4. **Меньше кода**: удалено ~80 строк дублированного кода
5. **Защита от зависаний**: pytest.ini с таймаутом 60 секунд
6. **Type safety**: добавлены type hints для фикстур

## Запуск теста

```bash
# Запуск конкретного теста
pytest -k test_e2e_escalation_debug -vv -s

# С детальным выводом
pytest tests/test_e2e_escalation_debug.py -vv -s --tb=short

# С замером времени
pytest -k test_e2e_escalation_debug -vv -s --durations=10
```

## Критерии успешности

✅ Тест использует общие фикстуры из conftest.py  
✅ Нет локальных фикстур session/clean_db  
✅ Нет обращений к TRUNCATE из теста  
✅ Нет создания engine/SessionLocal в тесте  
✅ Тест не зависает (защита через pytest.ini timeout)  
✅ Тест идемпотентен (можно запускать многократно)  

## Устранение проблем

Если тест всё равно зависает:

1. **Проверить активные транзакции:**
```sql
SELECT pid, usename, application_name, state, query 
FROM pg_stat_activity 
WHERE datname = 'field_service_test';
```

2. **Убить зависшие процессы:**
```sql
SELECT pg_terminate_backend(pid) 
FROM pg_stat_activity 
WHERE datname = 'field_service_test' AND pid <> pg_backend_pid();
```

3. **Проверить блокировки:**
```sql
SELECT * FROM pg_locks WHERE NOT granted;
```

4. **Принудительный VACUUM:**
```bash
docker exec -it fs_postgres psql -U fs_user -d field_service_test -c "VACUUM FULL;"
```
