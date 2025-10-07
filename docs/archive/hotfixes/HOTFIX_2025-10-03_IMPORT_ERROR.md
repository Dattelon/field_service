# 🔥 HOTFIX: ImportError distribution_worker

## ❌ Проблема

```python
ImportError: cannot import name 'distribution_worker' from 'field_service.services'
```

При запуске `admin_bot` обнаружена ошибка:
- Файл `candidates.py` импортировал удалённый `distribution_worker`
- CR-2025-10-03-010 удалил этот модуль, но пропустил один импорт

## ✅ Решение

### 1. Добавлена функция `_max_active_limit_for()` в `distribution_scheduler.py`

```python
async def _max_active_limit_for(session: AsyncSession) -> int:
    """Return the global default max active orders (fallback 5)."""
    row = await session.execute(
        select(m.settings.value).where(m.settings.key == "max_active_orders")
    )
    value = row.scalar_one_or_none()
    try:
        result = int(value) if value is not None else DEFAULT_MAX_ACTIVE_LIMIT
    except Exception:
        result = DEFAULT_MAX_ACTIVE_LIMIT
    return max(1, result)
```

### 2. Обновлён импорт в `candidates.py`

**Было:**
```python
from field_service.services import distribution_worker as dw

skill_code = dw._skill_code_for_category(...)
global_limit = await dw._max_active_limit_for(session)
```

**Стало:**
```python
from field_service.services import distribution_scheduler as ds

skill_code = ds._skill_code_for_category(...)
global_limit = await ds._max_active_limit_for(session)
```

## 📝 Изменённые файлы

1. ✅ `field_service/services/distribution_scheduler.py`
   - Добавлена функция `_max_active_limit_for()`
   
2. ✅ `field_service/services/candidates.py`
   - Импорт: `distribution_worker` → `distribution_scheduler`
   - Использование: `dw.` → `ds.`

## ✅ Тестирование

```bash
# Проверка запуска admin_bot
python -m field_service.bots.admin_bot.main

# Должен запуститься без ошибок импорта
```

## 🎯 Корневая причина

При миграции CR-2025-10-03-010:
- ✅ Обновлены тесты
- ✅ Удалён `distribution_worker.py`
- ❌ Пропущен импорт в `candidates.py`

**Урок:** При удалении модулей нужно проверять все импорты в проекте:
```bash
# Поиск всех импортов
grep -r "import distribution_worker" field_service/
grep -r "from.*distribution_worker" field_service/
```

## 📊 Статус

- **Status:** ✅ FIXED
- **Severity:** HIGH (блокирует запуск admin_bot)
- **Time to fix:** 5 минут
- **Files changed:** 2

---

**Готово к запуску! 🎉**
