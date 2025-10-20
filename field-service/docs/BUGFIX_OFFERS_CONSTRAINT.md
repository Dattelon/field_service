# Изменение Constraint для офферов

**Дата:** 2025-10-10  
**Приоритет:** P0  
**Статус:** ✅ Применено

---

## 🐛 Проблема

### Описание
Constraint `uq_offers__order_master UNIQUE (order_id, master_id)` блокировал создание новых офферов для той же пары (заказ + мастер), даже если предыдущий оффер был EXPIRED или DECLINED.

### Сценарий:
1. Мастер получил оффер на заказ #15
2. Оффер истёк (EXPIRED)
3. Админ пытается назначить того же мастера снова
4. ❌ Ошибка: `duplicate key value violates unique constraint`

---

## ✅ Решение

### Изменён constraint на partial unique index

```sql
-- Удалён старый constraint
ALTER TABLE offers DROP CONSTRAINT uq_offers__order_master;

-- Создан новый partial unique index
CREATE UNIQUE INDEX uq_offers__order_master_active 
ON offers (order_id, master_id) 
WHERE state IN ('SENT', 'VIEWED', 'ACCEPTED');
```

### Что изменилось:

**До:**
- Constraint применялся ко **всем** офферам
- Нельзя было создать повторный оффер даже после EXPIRED/DECLINED

**После:**
- Index применяется **только к активным** офферам (SENT, VIEWED, ACCEPTED)
- ✅ Можно создавать новые офферы после EXPIRED/DECLINED
- ✅ Защита от дублирования активных офферов сохранена

---

## 🧪 Тестирование

### Тест 1: Повторные офферы работают ✅
```sql
-- Создаём EXPIRED оффер
INSERT INTO offers (order_id, master_id, state, ...) 
VALUES (15, 86, 'EXPIRED', ...);
-- ✅ Успешно

-- Создаём новый SENT оффер для той же пары
INSERT INTO offers (order_id, master_id, state, ...) 
VALUES (15, 86, 'SENT', ...);
-- ✅ Успешно (раньше упало бы с ошибкой)
```

### Тест 2: Защита от дублирования активных офферов ✅
```sql
-- Пытаемся создать второй активный оффер
INSERT INTO offers (order_id, master_id, state, ...) 
VALUES (15, 86, 'SENT', ...);
-- ❌ Ошибка: duplicate key (защита работает)
```

---

## 📊 Преимущества

### Функциональные:
- ✅ Админ может повторно назначать мастеров на заказы
- ✅ Система автоматически может пересылать офферы после таймаута
- ✅ Гарантийные заказы могут отправляться прежнему мастеру

### Технические:
- ✅ Меньше размер индекса (не индексирует EXPIRED/DECLINED)
- ✅ Более быстрые вставки (меньше проверок)
- ✅ Логичная семантика (защита только где нужна)

---

## 🔄 Обратная совместимость

### Влияние на код:
- ✅ Код не требует изменений
- ✅ SQL запросы работают как раньше
- ✅ `ON CONFLICT ON CONSTRAINT uq_offers__order_master DO NOTHING` продолжит работать

### Влияние на данные:
- ✅ Существующие данные не затронуты
- ✅ История офферов сохранена
- ✅ Статистика не изменилась

---

## 📝 Миграция

**Файл:** `migrations/2025-10-10_fix_offers_constraint.sql`

**Применено:**
```bash
docker exec field-service-postgres-1 psql -U fs_user -d field_service \
  -f migrations/2025-10-10_fix_offers_constraint.sql
```

**Откат (если нужен):**
```sql
-- Удалить новый index
DROP INDEX IF EXISTS uq_offers__order_master_active;

-- Восстановить старый constraint
ALTER TABLE offers 
ADD CONSTRAINT uq_offers__order_master 
UNIQUE (order_id, master_id);
```

---

## 🎯 Use Cases

### 1. Повторное назначение после истечения
```
Заказ #15 → Мастер #86 → EXPIRED (таймаут)
                ↓
Админ назначает вручную → Мастер #86 → SENT ✅
```

### 2. Повторное назначение после отклонения
```
Заказ #20 → Мастер #50 → DECLINED (занят)
                ↓
Позже мастер освободился
                ↓
Автораспределение → Мастер #50 → SENT ✅
```

### 3. Гарантийные заказы
```
Заказ #30 (гарантия) → Ищем прежнего мастера #60
                ↓
Был старый оффер EXPIRED
                ↓
Создаём новый → Мастер #60 → SENT ✅
```

---

## 🔍 Мониторинг

### Проверка constraint:
```sql
SELECT 
    indexname,
    indexdef
FROM pg_indexes 
WHERE tablename = 'offers' 
  AND indexname = 'uq_offers__order_master_active';
```

### Статистика повторных офферов:
```sql
SELECT 
    order_id,
    master_id,
    COUNT(*) as offer_count,
    STRING_AGG(state::text, ' → ' ORDER BY id) as state_history
FROM offers
GROUP BY order_id, master_id
HAVING COUNT(*) > 1
ORDER BY offer_count DESC
LIMIT 10;
```

---

## 📚 Связанные изменения

- **P0-BUGFIX-EXPIRED-OFFERS**: Watchdog для истёкших офферов
- **IMPORT-FIX-MASTERS**: Исправлен импорт select_candidates
- **MIDDLEWARE-FIX**: Исправлен DbSessionMiddleware в мастер-боте

---

**Автор:** Claude + Simzikov  
**Применено:** 2025-10-10  
**Тестирование:** ✅ Пройдено
