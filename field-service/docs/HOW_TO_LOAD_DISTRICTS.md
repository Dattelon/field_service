# 📚 Инструкция: Как загружались районы для Иркутска, Москвы и СПб

## 🎯 Найденный скрипт

**Путь:** `tools/load_geo_catalog.py`

Это универсальный скрипт для загрузки географических данных (города, районы, улицы) из CSV файла.

---

## 📋 Формат CSV для загрузки

Скрипт ожидает CSV файл с колонками:

```csv
type,city,district,name,centroid_lat,centroid_lon
city,,,Москва,55.7558,37.6173
district,Москва,,Центральный район,,
district,Москва,,Северный район,,
street,Москва,Центральный район,Тверская улица,,
```

### Колонки:
- **type** - тип записи: `city` | `district` | `street`
- **city** - название города (обязательно для district/street)
- **district** - название района (обязательно для street)
- **name** - название объекта
- **centroid_lat** - широта центра (опционально)
- **centroid_lon** - долгота центра (опционально)

---

## 🔧 Как работает скрипт

### 1. Загрузка данных
```bash
python -m tools.load_geo_catalog --input geo_catalog.csv
```

### 2. Дедупликация через RapidFuzz
Скрипт автоматически находит дубликаты:
- **score ≥ 93%** - дубликат, пропускается
- **85% ≤ score < 93%** - "questionable", требует проверки
- **score < 85%** - добавляется

### 3. Нормализация названий
Через модуль `field_service.data.cities`:
- Исправляет алиасы: "СПб" → "Санкт Петербург"
- Нормализует регистр и пробелы
- Проверяет по белому списку `ALLOWED_CITIES`

---

## 📊 Откуда взялись данные для Иркутска, Москвы и СПб?

### Возможные источники:

1. **OpenStreetMap (OSM)** ✅ Наиболее вероятно
   - Административные границы
   - Районы, кварталы, микрорайоны
   - API: Overpass Turbo

2. **ФИАС (ГИС ЖКХ)** ✅ Официальный реестр
   - Федеральная информационная адресная система
   - Содержит все населенные пункты и районы РФ
   - [fias.nalog.ru](https://fias.nalog.ru)

3. **Геокодеры**
   - Yandex Geocoder API
   - Dadata API
   - 2GIS API

4. **Ручной экспорт из муниципальных сайтов**

---

## 🎬 Как загрузить районы для других городов

### Вариант 1: Использовать load_geo_catalog.py (рекомендуется)

#### Шаг 1: Подготовьте CSV файл

**Пример для Новосибирска:**
```csv
type,city,district,name,centroid_lat,centroid_lon
district,Новосибирск,,Центральный район,55.0415,82.9346
district,Новосибирск,,Железнодорожный район,55.0451,82.8934
district,Новосибирск,,Заельцовский район,54.9884,83.0065
district,Новосибирск,,Ленинский район,55.0271,82.9557
district,Новосибирск,,Дзержинский район,55.0530,82.8934
district,Новосибирск,,Калининский район,54.8996,82.9863
district,Новосибирск,,Кировский район,54.9924,83.0868
district,Новосибирск,,Октябрьский район,55.0828,82.9478
district,Новосибирск,,Первомайский район,54.9721,82.8934
district,Новосибирск,,Советский район,55.0656,83.0198
```

#### Шаг 2: Запустите импорт
```bash
# Тестовый прогон (без сохранения)
python -m tools.load_geo_catalog --input data/novosibirsk.csv --dry-run

# Реальный импорт
python -m tools.load_geo_catalog --input data/novosibirsk.csv
```

#### Шаг 3: Удалите "Город целиком"
```bash
python scripts/import_districts.py --remove-placeholder
```

---

### Вариант 2: Использовать новый скрипт import_districts.py

#### Подготовьте простой CSV:
```csv
city_name,district_name
Новосибирск,Центральный район
Новосибирск,Железнодорожный район
```

#### Запустите:
```bash
python scripts/import_districts.py --file data/districts.csv
```

---

## 🌐 Где взять данные для районов?

### 1. OpenStreetMap (Самый простой)

**Overpass Turbo Query:**
```overpass
[out:json];
area["name"="Новосибирск"]["admin_level"="6"]->.city;
(
  relation(area.city)["admin_level"="9"];
);
out geom;
```

**Шаги:**
1. Зайти на [overpass-turbo.eu](https://overpass-turbo.eu/)
2. Вставить запрос
3. Нажать "Выполнить"
4. Экспорт → GeoJSON или CSV

### 2. ФИАС (Официальный реестр РФ)

**Ссылка:** https://fias.nalog.ru/

**Как использовать:**
1. Скачать полную базу (XML/DBF)
2. Извлечь районы для нужного города
3. Конвертировать в CSV

### 3. Yandex Geocoder API

```python
import requests

def get_districts(city_name):
    url = "https://geocode-maps.yandex.ru/1.x/"
    params = {
        "apikey": "YOUR_API_KEY",
        "geocode": city_name,
        "kind": "district",
        "format": "json"
    }
    response = requests.get(url, params=params)
    # Parse response...
```

### 4. 2GIS API

```python
import requests

def get_districts_2gis(city_id):
    url = f"https://catalog.api.2gis.com/3.0/items"
    params = {
        "q": "район",
        "region_id": city_id,
        "type": "district",
        "key": "YOUR_API_KEY"
    }
    # ...
```

---

## 🔍 Как узнать что было загружено для Иркутска?

### SQL запрос:
```sql
-- Все районы Иркутска
SELECT name 
FROM districts 
WHERE city_id = 4 
ORDER BY name;

-- Группировка по типу
SELECT 
    CASE 
        WHEN name LIKE '%микрорайон%' THEN 'микрорайон'
        WHEN name LIKE '%квартал%' THEN 'квартал'
        WHEN name LIKE '%ЖК%' THEN 'ЖК'
        WHEN name LIKE '%СНТ%' THEN 'СНТ'
        WHEN name LIKE '%район%' THEN 'район'
        WHEN name LIKE '%округ%' THEN 'округ'
        ELSE 'другое'
    END as type,
    COUNT(*) as count
FROM districts 
WHERE city_id = 4
GROUP BY type
ORDER BY count DESC;
```

---

## 📝 Примеры готовых CSV для загрузки

Я создал для вас:

1. **`data/districts_sample.csv`** - Примеры для 5 городов (45 районов)
2. **`scripts/import_districts.py`** - Новый скрипт для массового импорта

---

## ⚡ Быстрый старт для Калининграда

```bash
# 1. Создайте файл
cat > data/kaliningrad.csv << EOF
type,city,district,name
district,Калининград,,Центральный район
district,Калининград,,Балтийский район  
district,Калининград,,Ленинградский район
district,Калининград,,Московский район
EOF

# 2. Загрузите
python -m tools.load_geo_catalog --input data/kaliningrad.csv

# 3. Проверьте
psql -U postgres -d field_service -c "SELECT * FROM districts WHERE city_id = 40;"
```

---

## 💡 Рекомендации

### Для крупных городов (1+ млн):
- ✅ Используйте детальную разбивку по районам
- ✅ Добавляйте координаты центров (для будущего)
- ✅ Источник: OSM + ФИАС

### Для средних городов (500к - 1 млн):
- ✅ Административные районы (5-10 штук)
- ⚠️ Координаты опционально

### Для малых городов (<500к):
- ✅ "Город целиком" достаточно
- ℹ️ Детализация при необходимости

---

## 🎯 Итог

**Скрипт найден:** `tools/load_geo_catalog.py`  
**Формат данных:** CSV с типом, городом, названием  
**Источники данных:** OSM, ФИАС, Геокодеры  
**Новый скрипт:** `scripts/import_districts.py` (упрощённая версия)  

**Для загрузки районов нужно:**
1. Получить список районов (OSM/ФИАС)
2. Создать CSV файл
3. Запустить `load_geo_catalog.py`
4. Удалить "Город целиком" если нужно

Хотите чтобы я помог найти и загрузить районы для конкретного города? 🚀
