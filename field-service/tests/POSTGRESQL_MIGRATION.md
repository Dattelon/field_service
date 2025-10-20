# 🔄 МИГРАЦИЯ НА POSTGRESQL В ТЕСТАХ

## ✅ Что сделано

1. **Удалён SQLite** из `conftest.py`
2. **Добавлен PostgreSQL** с полной поддержкой всех функций
3. **Создана тестовая БД** `field_service_test`

## 🎯 Преимущества

- ✅ Все PostgreSQL функции работают (`NOW()`, `pg_try_advisory_lock()`, JSONB, etc.)
- ✅ Полная идентичность test/dev/prod окружений
- ✅ Реальное тестирование индексов и производительности
- ✅ Нет проблем с несовместимостью SQL диалектов

## 🔧 Конфигурация

### Параметры подключения (conftest.py):
```python
TEST_DATABASE_URL = "postgresql+asyncpg://fs_user:fs_password@localhost:5439/field_service_test"
```

### Переменная окружения (опционально):
```bash
export TEST_DATABASE_URL="postgresql+asyncpg://fs_user:fs_password@localhost:5439/field_service_test"
```

## 📋 Структура fixtures

### Session-scoped (создаётся 1 раз):
- `engine` - Engine для всех тестов

### Function-scoped (для каждого теста):
- `async_session` / `session` - Чистая БД для каждого теста
- `sample_city` - Тестовый город
- `sample_district` - Тестовый район  
- `sample_skill` - Тестовый навык
- `sample_master` - Тестовый мастер с навыком и районом

## 🧹 Очистка БД между тестами

Используется `TRUNCATE CASCADE` (быстро) с fallback на `DELETE` (медленно):

```python
async def _clean_database(session: AsyncSession) -> None:
    """Очищает все таблицы перед каждым тестом"""
    try:
        for table in tables_to_clean:
            await session.execute(sa.text(f"TRUNCATE TABLE {table} CASCADE"))
        await session.commit()
    except Exception:
        # Fallback на DELETE
        ...
```

## 🚀 Запуск тестов

### Все тесты:
```powershell
cd C:\ProjectF\field-service
$env:PYTHONIOENCODING='utf-8'
pytest tests/ -v
```

### Конкретный файл:
```powershell
pytest tests/test_step_2_logical_improvements.py -v -s
```

### С покрытием:
```powershell
pytest tests/ --cov=field_service --cov-report=html
```

## 🐛 Troubleshooting

### БД не подключается:
```powershell
# Проверить что контейнер запущен
docker ps

# Проверить доступность БД
docker exec field-service-postgres-1 psql -U fs_user -d field_service_test -c "\l"
```

### Пересоздать тестовую БД:
```powershell
docker exec field-service-postgres-1 psql -U fs_user -d field_service -c "DROP DATABASE IF EXISTS field_service_test;"
docker exec field-service-postgres-1 psql -U fs_user -d field_service -c "CREATE DATABASE field_service_test;"
```

### Очистить все таблицы вручную:
```sql
DO $$ 
DECLARE 
    r RECORD;
BEGIN
    FOR r IN (SELECT tablename FROM pg_tables WHERE schemaname = 'public') LOOP
        EXECUTE 'TRUNCATE TABLE ' || quote_ident(r.tablename) || ' CASCADE';
    END LOOP;
END $$;
```

## 📊 Производительность

- **Первый запуск**: ~2-3 секунды (создание таблиц)
- **Последующие тесты**: ~100-200ms на тест (TRUNCATE)
- **Session-scoped engine**: Используется один connection pool

## ⚠️ Важно

1. **Не используйте production БД** для тестов!
2. **Тестовая БД должна быть отдельной**: `field_service_test`
3. **Тесты очищают БД**: Все данные удаляются между тестами

## 📝 Примеры использования

### Простой тест:
```python
@pytest.mark.asyncio
async def test_something(session: AsyncSession, sample_city: m.cities):
    order = m.orders(city_id=sample_city.id, status="SEARCHING")
    session.add(order)
    await session.commit()
    
    result = await session.execute(select(m.orders))
    assert result.scalar_one().status == "SEARCHING"
```

### С использованием NOW():
```python
@pytest.mark.asyncio
async def test_with_db_time(session: AsyncSession):
    row = await session.execute(text("SELECT NOW()"))
    db_now = row.scalar()
    # Теперь работает! 
```

### С advisory lock:
```python
@pytest.mark.asyncio  
async def test_with_lock(session: AsyncSession):
    row = await session.execute(text("SELECT pg_try_advisory_lock(123)"))
    locked = row.scalar()
    assert locked is True
    # Теперь работает!
```
