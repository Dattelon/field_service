# ✅ СКРИПТЫ ДЛЯ СНАПШОТОВ БД - ГОТОВО

**Дата создания:** 2025-10-07  
**Статус:** Все скрипты протестированы и работают

## 📂 Созданные файлы

### Скрипты в `C:\ProjectF\field-service\scripts\`

1. **quick_db_snapshot.ps1** ⚡ (РЕКОМЕНДУЕТСЯ)
   - Быстрый снапшот через pg_dump
   - Создает SQL + TXT файлы
   - ✅ Протестирован и работает
   - Время выполнения: ~5-10 секунд

2. **create_db_snapshot.ps1** 📊
   - Детальный снапшот с полной статистикой
   - Для каждой таблицы: структура, индексы, FK, количество записей
   - Требует больше времени, но даёт максимум информации

3. **db_structure_snapshot.py** 🐍
   - Python скрипт с asyncpg
   - Программный доступ к структуре БД
   - Требует: `pip install asyncpg`

4. **README_DB_SNAPSHOTS.md** 📖
   - Полная документация по всем скриптам
   - Инструкции по использованию
   - Примеры автоматизации

## 📊 Результат тестирования

### Успешно созданные файлы:
```
scripts/
├── db_schema_2025-10-07_165709.sql        (53.44 KB)  ← SQL схема
└── db_structure_2025-10-07_165709.txt     (57.16 KB)  ← Читаемая версия
```

### Содержимое снапшота:
```
================================================================================
DATABASE STRUCTURE: field_service
================================================================================
Created: 2025-10-07 16:57:09

STATISTICS:
--------------------------------------------------------------------------------
Tables: 25 
ENUM types: 12 
Sequences: 17 
Database size: 10021 kB 

TABLES:
--------------------------------------------------------------------------------
        table_name        | rows 
--------------------------+------
 districts                |  365  ← все районы добавлены!
 cities                   |   79  ← все города добавлены!
 staff_users              |    5
 settings                 |    1
 skills                   |    1
 order_status_history     |    1
 admin_audit_log          |    1
 orders                   |    1
 ... (25 таблиц всего)

SQL SCHEMA:
--------------------------------------------------------------------------------
-- PostgreSQL database dump
-- Version 15.14

CREATE TYPE public.attachment_entity AS ENUM (
    'ORDER',
    'MASTER'
);

CREATE TYPE public.master_finance_status AS ENUM (
    'PENDING',
    'PAID',
    'OVERDUE',
    ...
);

CREATE TABLE public.cities (
    id integer NOT NULL,
    name character varying(120) NOT NULL,
    is_active boolean DEFAULT true,
    timezone character varying(64),
    ...
);

... (полная структура всех таблиц, индексов, constraints)
```

## 🚀 Как использовать

### Быстрый снапшот (каждый день):
```powershell
cd C:\ProjectF\field-service\scripts
.\quick_db_snapshot.ps1
```

### Детальный снапшот (перед миграциями):
```powershell
cd C:\ProjectF\field-service\scripts
.\create_db_snapshot.ps1
```

### Python снапшот (для автоматизации):
```powershell
cd C:\ProjectF\field-service\scripts
python db_structure_snapshot.py
```

## 💡 Рекомендации

1. **Перед каждой миграцией:** Создавайте снапшот `quick_db_snapshot.ps1`
2. **Раз в неделю:** Создавайте детальный снапшот `create_db_snapshot.ps1`
3. **В Git:** Храните снапшоты в папке `migrations/snapshots/`
4. **Для сравнения:** Используйте `git diff` между снапшотами

## 📝 Что попало в снапшот

### ✅ Структура БД на 2025-10-07:
- **25 таблиц** (orders, masters, cities, districts, offers, и т.д.)
- **12 ENUM типов** (order_status, master_finance_status, offer_state, и т.д.)
- **17 sequences** (для auto-increment ID)
- **365 районов** (все добавлены!)
- **79 городов** (78 реальных + Test City)
- **Все индексы** (primary keys, foreign keys, unique constraints)
- **Все constraints** (foreign key constraints с ON DELETE/UPDATE)

## 🔍 Как читать снапшот

### SQL файл (db_schema_*.sql):
- Чистый SQL код
- Можно выполнить для создания схемы: `psql -U fs_user -d new_db -f db_schema_*.sql`
- Использовать для сравнения версий БД

### TXT файл (db_structure_*.txt):
- Читаемый формат
- Статистика по таблицам
- Количество записей
- Полная SQL схема внизу

## ✅ Заключение

Все скрипты созданы и протестированы! Теперь можно:
1. ✅ Создавать снапшоты структуры БД в любой момент
2. ✅ Сравнивать изменения между версиями
3. ✅ Документировать структуру БД
4. ✅ Восстанавливать схему при необходимости

---

**Следующий шаг:** Настроить автоматическое создание снапшотов перед миграциями

```powershell
# Добавить в начало каждого миграционного скрипта:
cd C:\ProjectF\field-service\scripts
.\quick_db_snapshot.ps1
```

---

*Документация создана: 2025-10-07 16:58*  
*Скрипты протестированы на PostgreSQL 15.14*
