# 🔧 Исправление городов и районов в админ-боте

## 🐛 Обнаруженная проблема

При создании заявки в админ-боте:
- **Отображается только 21 город** из 78 доступных в каталоге
- **У всех городов 0 районов** (кроме тестового города)
- Города не в алфавитном порядке в БД

## 🔍 Причина

В базе данных:
```sql
-- Текущее состояние
SELECT COUNT(*) FROM cities WHERE is_active = true;
-- Результат: 21 (должно быть 78)

SELECT COUNT(*) FROM districts;
-- Результат: 1 (только тестовый)
```

В каталоге `field_service/data/cities.py` есть все 78 городов, но в БД добавлены не все.

## ✅ Решение

Созданы два миграционных скрипта:

### 1️⃣ Добавление всех 78 городов
**Файл:** `migrations/2025-10-07_add_all_cities.sql`
- Добавляет все города из каталога
- Устанавливает правильные timezone
- Использует `ON CONFLICT DO UPDATE` для безопасности

### 2️⃣ Добавление районов для 20 основных городов
**Файл:** `migrations/2025-10-07_add_districts.sql`
- Москва (12 округов: ЦАО, САО, СВАО, ВАО, ЮВАО, ЮАО, ЮЗАО, ЗАО, СЗАО, ЗелАО, НАО, ТАО)
- Санкт-Петербург (18 районов)
- Новосибирск (10 районов)
- Екатеринбург (7 районов)
- Казань (7 районов)
- Нижний Новгород (8 районов)
- Челябинск (7 районов)
- Красноярск (7 районов)
- Самара (9 районов)
- Уфа (7 районов)
- Ростов-на-Дону (8 районов)
- Краснодар (4 района)
- Омск (5 районов)
- Воронеж (6 районов)
- Пермь (7 районов)
- Волгоград (8 районов)
- Саратов (6 районов)
- Тюмень (4 района)
- Тольятти (3 района)
- Ижевск (5 районов)

## 🚀 Как применить

### Шаг 1: Проверить текущее состояние
```powershell
docker exec -i field-service-db psql -U field_service -d field_service -c "SELECT COUNT(*) as total, COUNT(*) FILTER (WHERE is_active = true) as active FROM cities;"
docker exec -i field-service-db psql -U field_service -d field_service -c "SELECT COUNT(*) FROM districts;"
```

### Шаг 2: Применить миграции
```powershell
# Добавить все 78 городов
docker exec -i field-service-db psql -U field_service -d field_service < migrations/2025-10-07_add_all_cities.sql

# Добавить районы для основных городов
docker exec -i field-service-db psql -U field_service -d field_service < migrations/2025-10-07_add_districts.sql
```

### Шаг 3: Проверить результат
```powershell
# Проверить города (должно быть 78+)
docker exec -i field-service-db psql -U field_service -d field_service -c "SELECT COUNT(*) as total FROM cities WHERE is_active = true;"

# Проверить районы по городам
docker exec -i field-service-db psql -U field_service -d field_service -c "SELECT c.name as city, COUNT(d.id) as districts FROM cities c LEFT JOIN districts d ON d.city_id = c.id WHERE c.id IN (203, 204, 205, 206, 207, 208, 209, 210, 211, 212, 213, 214, 215, 216, 217, 218, 219, 220, 221, 222) GROUP BY c.id, c.name ORDER BY c.name;"

# Показать все города в алфавитном порядке
docker exec -i field-service-db psql -U field_service -d field_service -c "SELECT name FROM cities WHERE is_active = true ORDER BY name;"
```

## 📝 Что изменится в админ-боте

### До исправления:
- ❌ Показывает только 21 город
- ❌ Районов нет вообще
- ❌ При создании заявки нельзя выбрать район

### После исправления:
- ✅ Показывает все 78 городов в алфавитном порядке
- ✅ Для 20 основных городов доступны районы
- ✅ Для остальных городов можно создавать заявки без района (кнопка "🚫 Без района")
- ✅ Пагинация работает корректно

## 🔄 Откат (если что-то пошло не так)

```powershell
# Удалить добавленные районы
docker exec -i field-service-db psql -U field_service -d field_service -c "DELETE FROM districts WHERE city_id IN (203, 204, 205, 206, 207, 208, 209, 210, 211, 212, 213, 214, 215, 216, 217, 218, 219, 220, 221, 222);"

# Деактивировать добавленные города (оставить только исходные 21)
docker exec -i field-service-db psql -U field_service -d field_service -c "UPDATE cities SET is_active = false WHERE id > 222;"
```

## 📊 Техническая информация

### Структура таблицы cities:
```sql
CREATE TABLE cities (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    is_active BOOLEAN DEFAULT true,
    timezone VARCHAR(50) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

### Структура таблицы districts:
```sql
CREATE TABLE districts (
    id SERIAL PRIMARY KEY,
    city_id INTEGER NOT NULL REFERENCES cities(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(city_id, name)
);
```

### Как работает выбор города и района в коде:

1. **orders_service.list_cities()** в `admin_bot/services/orders.py`:
   - Получает список городов из каталога `cities.py` (с алфавитной сортировкой)
   - Проверяет наличие городов в БД с `is_active = true`
   - Возвращает только те города, которые есть и в каталоге, и в БД

2. **orders_service.list_districts()** в том же файле:
   - Получает районы из БД для указанного city_id
   - Возвращает пагинированный список (5 районов на страницу)
   - Если районов нет, показывается только кнопка "🚫 Без района"

## 🎯 Следующие шаги

После применения миграций админ-бот сразу начнёт работать правильно:
- Все 78 городов в алфавитном порядке
- Районы для 20 основных городов
- Корректная пагинация

Для добавления районов в остальные города:
- Используйте `tools/load_geo_catalog.py` для импорта из CSV
- Или вручную через SQL INSERT

## 📞 Проблемы?

Если после применения миграций что-то работает не так:
1. Проверьте логи контейнера: `docker logs field-service-db`
2. Проверьте состояние БД командами из Шага 3
3. Проверьте, что файлы миграций существуют в правильном пути
