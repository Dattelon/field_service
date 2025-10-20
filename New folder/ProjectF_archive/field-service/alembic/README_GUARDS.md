# Migration Guards and Environment-Specific Seeds

## Обзор

Система guards позволяет контролировать применение миграций в зависимости от окружения:
- **Dev-only seeds**: Данные с пустыми именами (только для локальной разработки)
- **CI-minimal seeds**: Минимальный набор для CI/тестов
- **Production**: Только реальные данные

## Файлы

### Guards

`alembic/guards.py` - Функции для проверки окружения:

```python
from guards import skip_unless_dev, ensure_ci_environment

def upgrade():
    # Пропустить в production/CI
    if skip_unless_dev(op, "demo data"):
        return
    
    # ... применяем dev-only данные
```

### Миграции

1. **2025_09_17_0003_seed_demo_data.py** (обновлено)
   - Применяется только в dev окружении
   - Содержит тестовые города/районы/навыки с пустыми именами
   - Требует: `APP_ENV=development` или `ALLOW_DEV_SEEDS=1`

2. **2025_10_15_0001_seed_ci_minimal.py** (новое)
   - Минимальный набор для CI/тестов
   - 1 город (Москва)
   - 3 района (ЦАО, СВАО, ЮАО)
   - 4 базовых навыка (ELEC, PLUMB, APPLI, HAND)
   - Без пустых имён

### E2E тесты

`tests/test_e2e_order_full_lifecycle.py` (новое)
- Полный цикл заказа: создание → дистрибуция → принятие → закрытие
- Проверка защиты от переназначения ASSIGNED заказа
- Тесты эскалации (логист → админ)
- Тесты отклонения и повторной дистрибуции

## Переменные окружения

### Для dev-окружения

```bash
# Разрешить dev-only seeds
APP_ENV=development
# ИЛИ
ALLOW_DEV_SEEDS=1
```

### Для CI/тестов

```bash
# CI автоматически определяется
CI=1
# ИЛИ pytest автоматически устанавливает
PYTEST_CURRENT_TEST=...
```

### Для production

```bash
# Не устанавливать APP_ENV и ALLOW_DEV_SEEDS
# Dev-only seeds будут пропущены
```

## Применение миграций

### Локальная разработка

```bash
# С dev-only seeds
cd C:\ProjectF\field-service
$env:APP_ENV="development"
alembic upgrade head
```

### CI/тесты

```bash
# Только минимальный набор
cd C:\ProjectF\field-service
# CI=1 устанавливается автоматически в CI
alembic upgrade head
```

### Production

```bash
# Без dev-only seeds
cd /opt/field-service
# APP_ENV не установлен
alembic upgrade head
```

## Проверка окружения

```python
# В Python
from alembic.guards import is_dev_environment, is_ci_environment

if is_dev_environment():
    print("Development mode")

if is_ci_environment():
    print("CI/Test mode")
```

## Логирование

Guards выводят информативные сообщения:

```
⏭️  Skipping demo data with empty names (not in development environment)
```

## Правила использования

1. **Dev-only seeds**:
   - Только для локальной разработки
   - Могут содержать пустые имена, демо-данные
   - Должны использовать `skip_unless_dev()`

2. **CI-minimal seeds**:
   - Минимальный чистый набор
   - Без пустых имён
   - Только реальные данные
   - Применяются во всех окружениях

3. **Production seeds**:
   - Только реальные данные из справочников
   - Без демо-данных
   - Обязательная валидация

## Примеры

### Dev-only миграция

```python
from guards import skip_unless_dev

def upgrade():
    if skip_unless_dev(op, "test cities"):
        return
    
    op.execute("""
        INSERT INTO cities (name) 
        VALUES ('Тестовград')
    """)
```

### CI-only миграция

```python
from guards import ensure_ci_environment

def upgrade():
    ensure_ci_environment(op, "test fixtures")
    
    # Эта миграция выполнится ТОЛЬКО в CI/тестах
    op.execute("""
        INSERT INTO test_data ...
    """)
```

### Универсальная миграция

```python
def upgrade():
    # Выполняется во всех окружениях
    op.execute("""
        INSERT INTO cities (name) 
        SELECT * FROM real_cities_catalog
    """)
```

## Troubleshooting

### Проблема: Dev-only seed не применяется локально

**Решение:**
```bash
$env:APP_ENV="development"
# ИЛИ
$env:ALLOW_DEV_SEEDS="1"
```

### Проблема: Dev-only seed применился на production

**Решение:** Проверить что на production НЕ установлены:
- `APP_ENV=development`
- `ALLOW_DEV_SEEDS=1`

### Проблема: Тесты падают из-за отсутствия данных

**Решение:** Убедиться что применена миграция `2025_10_15_0001_seed_ci_minimal.py`:

```bash
cd C:\ProjectF\field-service
alembic upgrade 2025_10_15_0001
```

## Проверка статуса миграций

```bash
# Показать текущую версию
alembic current

# Показать историю
alembic history

# Показать какие миграции будут применены
alembic upgrade head --sql
```

## Связанные задачи

- [x] Создан `guards.py` с проверками окружения
- [x] Обновлена `seed_demo_data.py` с защитой от production
- [x] Создана `seed_ci_minimal.py` для CI/тестов
- [x] Добавлены e2e тесты `test_e2e_order_full_lifecycle.py`
- [ ] Обновить CI pipeline для установки `CI=1`
- [ ] Добавить pre-commit hook для проверки guards в новых миграциях
