# TESTING RULES FOR PROJECT INSTRUCTIONS

При написании тестов для Field Service ОБЯЗАТЕЛЬНО соблюдать:

## Async Fixtures
```python
# Engine: scope="session", pool_size=10, max_overflow=20, pool_pre_ping=True
# Session: scope="function", всегда try-except вокруг rollback()
```

## Критичные правила
1. Datetime: ТОЛЬКО `datetime.now(timezone.utc)`, НИКОГДА `datetime.utcnow()`
2. Кодировка: БЕЗ эмодзи в print/комментариях (Windows cp1251)
3. Очистка БД: TRUNCATE CASCADE с fallback на DELETE в except
4. pytest.ini: ОБЯЗАТЕЛЬНО `asyncio_mode = auto`

## DB Cleanup Pattern
```python
try:
    await session.execute(text("TRUNCATE TABLE name CASCADE"))
    await session.commit()
except:
    await session.rollback()
    await session.execute(m.name.__table__.delete())
    await session.commit()
```

## PowerShell запуск
```powershell
$env:PYTHONIOENCODING='utf-8'; pytest tests/test_name.py -v -s
```

## Типичные ошибки
- "Event loop is closed" - отсутствует pool_size в engine
- "UnicodeEncodeError" - эмодзи в выводе
- "can't compare datetime" - смешивание utcnow() и now(UTC)
- "TRUNCATE failed" - нет fallback на DELETE
