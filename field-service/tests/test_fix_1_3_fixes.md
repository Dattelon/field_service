# Исправления для test_fix_1_3_comprehensive.py

## Проблемы найдены:

1. **Unicode/Emoji** - Windows console не поддерживает
2. **Event loop scope** - нужен scope="module" для engine
3. **Неверные имена полей**:
   - `escalated_logist_at` → `dist_escalated_logist_at`
   - `escalated_admin_at` → `dist_escalated_admin_at`

## Изменения:

### 1. Убрать все emoji из print()
Заменить ✅ на [OK] или просто убрать

### 2. Изменить scope фикстуры
```python
@pytest_asyncio.fixture(scope="module")  # было: session
async def db_engine():
```

### 3. Исправить имена полей во всех тестах
```python
assert order.dist_escalated_logist_at is None  # было: escalated_logist_at
assert order.dist_escalated_admin_at is None   # было: escalated_admin_at
```

## Файлы для изменения:
- tests/test_fix_1_3_comprehensive.py - все упоминания полей
- tests/test_load_race_condition.py - scope fixture
