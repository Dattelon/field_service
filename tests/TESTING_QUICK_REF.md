# TESTING QUICK REFERENCE

## Обязательные настройки

### pytest.ini
```ini
asyncio_mode = auto
```

### DB Engine Fixture
```python
@pytest_asyncio.fixture(scope="session")
async def db_engine():
    engine = create_async_engine(
        DATABASE_URL,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True
    )
    yield engine
    await engine.dispose()
```

### Session Fixture
```python
@pytest_asyncio.fixture(scope="function")
async def async_session(db_engine):
    async_session_maker = sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session_maker() as session:
        await session.begin()
        try:
            await session.execute(text("TRUNCATE TABLE table_name CASCADE"))
            await session.commit()
        except:
            await session.rollback()
            await session.execute(m.table_name.__table__.delete())
            await session.commit()
        yield session
        try:
            await session.rollback()
        except:
            pass
```

## Критичные правила

1. ВСЕГДА: `datetime.now(timezone.utc)` вместо `datetime.utcnow()`
2. НИКОГДА: Эмодзи в print() или комментариях (Windows cp1251 ошибка)
3. ВСЕГДА: pool_size и max_overflow для engine
4. ВСЕГДА: try-except вокруг session.rollback()
5. ВСЕГДА: TRUNCATE с fallback на DELETE

## Типичные ошибки

| Ошибка | Причина | Решение |
|--------|---------|---------|
| Event loop is closed | Нет pool_size | Добавить pool_size=10 |
| UnicodeEncodeError | Эмодзи в выводе | Убрать все эмодзи |
| Datetime comparison error | utcnow() | Использовать now(timezone.utc) |
| TRUNCATE failed | Windows/права | Добавить fallback на DELETE |

## Запуск (PowerShell)
```powershell
$env:PYTHONIOENCODING='utf-8'; pytest tests/test_name.py -v -s
```

## Шаблон теста
```python
@pytest.mark.asyncio
async def test_name(async_session, test_city):
    # Arrange
    data = await create_test_data(...)
    
    # Act
    result = await function_under_test(...)
    
    # Assert
    assert result == expected
    print("[OK] TEST PASSED: description")
```
