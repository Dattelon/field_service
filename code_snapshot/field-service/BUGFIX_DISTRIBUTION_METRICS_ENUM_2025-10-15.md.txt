# BUGFIX: Distribution Metrics ENUM Type Mismatch

## Дата: 2025-10-15
## Статус: RESOLVED ✅

## Проблема

При запуске тестов `test_distribution_metrics.py` возникала ошибка:

```
asyncpg.exceptions.DatatypeMismatchError: column "category" is of type ordercategory 
but expression is of type character varying
```

## Причина

В тестовой БД таблица `distribution_metrics` была создана с колонкой `category` типа `ordercategory` (ENUM) вместо VARCHAR.

### Почему это произошло?

1. В таблице `orders` есть ENUM типы `order_category` и `order_type`
2. Когда SQLAlchemy создавала таблицу `distribution_metrics`, она обнаружила существующие ENUM типы
3. Asyncpg автоматически ассоциировал колонки с похожими названиями (`category`, `order_type`) с этими ENUM типами
4. Хотя в модели явно указан `String(32)`, asyncpg игнорировал это и использовал ENUM

## Решение

1. **Пересоздана таблица в тестовой БД** с явным указанием VARCHAR:
```sql
DROP TABLE IF EXISTS distribution_metrics CASCADE;

CREATE TABLE distribution_metrics (
    -- ... другие колонки ...
    category VARCHAR(32),
    order_type VARCHAR(32),
    -- ... остальные колонки ...
);
```

2. **Модель остаётся без изменений** - в ней уже правильно указан String:
```python
category: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
order_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
```

3. **Миграция production уже правильная** - файл `2025-10-07_create_distribution_metrics.sql` использует VARCHAR.

## Файлы изменены

- `fix_test_db_table.py` - скрипт для пересоздания таблицы
- `check_column_types.py` - скрипт для проверки типов колонок

## Результаты тестирования

После исправления все тесты прошли успешно:
```
tests/test_distribution_metrics.py .....            5 passed in 1.86s
```

## Рекомендации на будущее

Если в будущем потребуется создавать колонки с именами, совпадающими с существующими ENUM типами:

1. **Вариант 1**: Использовать другие имена колонок (например, `category_name` вместо `category`)
2. **Вариант 2**: Явно указывать CAST к VARCHAR в SQL-запросах
3. **Вариант 3**: Удалить ENUM типы из БД (если они не используются в других таблицах)

В данном случае мы выбрали самое простое решение - пересоздать таблицу с правильными типами.
