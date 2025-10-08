# ИНСТРУКЦИИ ПО НАПИСАНИЮ ТЕСТОВ ДЛЯ FIELD SERVICE

## Критичные правила для async тестов с PostgreSQL

### 1. Конфигурация async fixtures
```python
# ПРАВИЛЬНО - session scope для engine
@pytest_asyncio.fixture(scope="session")
async def db_engine():
    engine = create_async_engine(
        DATABASE_URL,
        echo=False,
        pool_pre_ping=True,
        pool_size=10,        # ОБЯЗАТЕЛЬНО для стабильности
        max_overflow=20      # ОБЯЗАТЕЛЬНО для стабильности
    )
    yield engine
    await engine.dispose()

# ПРАВИЛЬНО - function scope для session
@pytest_asyncio.fixture(scope="function")
async def async_session(db_engine):
    # Всегда используйте session maker
    async_session_maker = sessionmaker(
        db_engine,
        class_=AsyncSession,
        expire_on_commit=False
    )
    async with async_session_maker() as session:
        await session.begin()
        # Очистка БД здесь
        yield session
        try:
            await session.rollback()
        except:
            pass
```

### 2. Очистка БД между тестами
```python
# ПРАВИЛЬНО - TRUNCATE с fallback
try:
    await session.execute(text("TRUNCATE TABLE offers CASCADE"))
    await session.execute(text("TRUNCATE TABLE orders CASCADE"))
    await session.commit()
except Exception:
    await session.rollback()
    # Fallback на DELETE если TRUNCATE не работает
    await session.execute(m.offers.__table__.delete())
    await session.execute(m.orders.__table__.delete())
    await session.commit()

# НЕПРАВИЛЬНО - только DELETE без обработки ошибок
await session.execute(m.offers.__table__.delete())
```

### 3. Работа с datetime
```python
# ПРАВИЛЬНО - aware datetime
from datetime import datetime, timezone
break_until = datetime.now(timezone.utc) + timedelta(hours=1)
created_at = datetime.now(timezone.utc)

# НЕПРАВИЛЬНО - naive datetime
break_until = datetime.utcnow() + timedelta(hours=1)  # ОШИБКА
```

### 4. Кодировка и совместимость с Windows
```python
# ПРАВИЛЬНО - без эмодзи
print("[OK] TEST PASSED: test description")
print("FAILED: error description")

# НЕПРАВИЛЬНО - эмодзи вызывают UnicodeEncodeError в Windows
print("✅ TEST PASSED")  # ОШИБКА в Windows cp1251
```

### 5. Конфигурация pytest.ini
```ini
[pytest]
pythonpath = .
asyncio_mode = auto          # ОБЯЗАТЕЛЬНО для async тестов
markers =
    slow: marks tests as slow
    load: marks tests as load tests
    integration: marks tests as integration tests
```

### 6. Запуск тестов в PowerShell
```powershell
# ПРАВИЛЬНО - с указанием кодировки
$env:PYTHONIOENCODING='utf-8'; pytest tests/test_name.py -v -s

# НЕПРАВИЛЬНО - без кодировки могут быть проблемы с кириллицей
pytest tests/test_name.py -v -s
```

## Типичные ошибки и решения

### Ошибка: RuntimeError: Event loop is closed
**Причина:** Неправильный scope fixtures или отсутствие pool_size  
**Решение:** Использовать scope="session" для engine + pool_size=10

### Ошибка: AttributeError: 'NoneType' object has no attribute 'send'
**Причина:** Закрытие соединений при проблемах с event loop  
**Решение:** Добавить pool_pre_ping=True + обработку исключений в rollback

### Ошибка: UnicodeEncodeError
**Причина:** Эмодзи или специальные символы в print()  
**Решение:** Убрать все эмодзи, использовать только ASCII символы

### Ошибка: TypeError: can't compare offset-naive and offset-aware datetimes
**Причина:** Смешивание datetime.utcnow() и datetime.now(UTC)  
**Решение:** Всегда использовать datetime.now(timezone.utc)

## Структура тестов

### Минимальный шаблон теста
```python
@pytest.mark.asyncio
async def test_feature_name(
    async_session: AsyncSession,
    test_city,
    test_district,
):
    """
    Описание теста
    
    Ожидаемое поведение:
    - Пункт 1
    - Пункт 2
    """
    # Arrange - подготовка данных
    master = await create_master(...)
    order = await create_order(...)
    
    # Act - выполнение действия
    result = await function_under_test(...)
    
    # Assert - проверка результатов
    assert result.status == expected_status
    assert result.value == expected_value
    
    print("[OK] TEST PASSED: feature_name works correctly")
```

## Нагрузочные тесты

### Параллельное выполнение
```python
# ПРАВИЛЬНО - gather с обработкой исключений
tasks = [async_function(param) for param in params]
results = await asyncio.gather(*tasks, return_exceptions=False)

# Анализ результатов
successful = [r for r in results if r[0]]
failed = [r for r in results if not r[0]]
```

### Метрики производительности
```python
start_time = time.perf_counter()
# Выполнение операций
total_time = time.perf_counter() - start_time

latencies = [operation_time for operation_time in times]
avg_latency = sum(latencies) / len(latencies)
throughput = len(operations) / total_time
```

## Чек-лист перед коммитом тестов

- [ ] Все fixtures с правильными scope (session для engine, function для session)
- [ ] Добавлен pool_size и max_overflow для engine
- [ ] Используется datetime.now(timezone.utc) вместо utcnow()
- [ ] Нет эмодзи в print() и комментариях
- [ ] Добавлена обработка исключений в rollback
- [ ] TRUNCATE с fallback на DELETE для очистки БД
- [ ] asyncio_mode = auto в pytest.ini
- [ ] Тесты запускаются с $env:PYTHONIOENCODING='utf-8' в PowerShell
- [ ] Все assert имеют информативные сообщения об ошибках
- [ ] Добавлены docstring с описанием ожидаемого поведения

## Запуск тестов

```bash
# Все тесты
pytest tests/ -v -s

# Конкретный файл
pytest tests/test_name.py -v -s

# Конкретный тест
pytest tests/test_name.py::test_function -v -s

# Исключить медленные тесты
pytest tests/ -v -s -m "not slow"

# Только нагрузочные тесты
pytest tests/ -v -s -m "load"

# С детальным traceback
pytest tests/ -v -s --tb=short

# PowerShell с кодировкой
$env:PYTHONIOENCODING='utf-8'; pytest tests/test_name.py -v -s
```

## База данных для тестов

```python
# Конфигурация подключения
DATABASE_URL = "postgresql+asyncpg://fs_user:fs_password@localhost:5439/field_service"

# Проверка доступности PostgreSQL (Docker)
docker-compose ps
docker-compose up -d postgres
```

## Дополнительные рекомендации

1. Всегда используйте absolute paths для надежности
2. Избегайте datetime.utcnow() - используйте datetime.now(timezone.utc)
3. Добавляйте print() с описанием результатов для отладки
4. Для Windows используйте только ASCII в консольном выводе
5. Тесты должны быть идемпотентными (повторяемыми)
6. Очищайте БД перед каждым тестом через TRUNCATE CASCADE
7. Используйте try-except для rollback в cleanup
8. Добавляйте метрики времени для нагрузочных тестов
