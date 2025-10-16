# 📊 Отчёт о тестовой БД field_service_test

**Дата:** 2025-10-16  
**Контейнер:** field-service-postgres-1  
**Образ:** postgres:15-alpine  
**Статус:** Up 2 hours (healthy)  
**Порт:** 5439 → 5432  
**Пользователь:** field_user  
**БД:** field_service_test

---

## 🗄️ Версия миграций Alembic

**Текущая версия:** `4c2465ccb4e5`

---

## 📋 Список таблиц (26 таблиц)

| # | Таблица | Описание | Размер |
|---|---------|----------|---------|
| 1 | admin_audit_log | Аудит действий администраторов | 8 KB |
| 2 | alembic_version | Версии миграций Alembic | 8 KB |
| 3 | attachments | Вложения к заказам/комиссиям | 16 KB |
| 4 | cities | Города (справочник) | 16 KB |
| 5 | commissions | Комиссии мастеров | 32 KB |
| 6 | **distribution_metrics** | Метрики распределения (owner: fs_user) | 32 KB |
| 7 | districts | Районы городов | 16 KB |
| 8 | geocache | Кэш геокодирования | 0 bytes |
| 9 | master_districts | М2М: Мастера ↔ Районы | 16 KB |
| 10 | master_invite_codes | Пригласительные коды мастеров | 8 KB |
| 11 | master_skills | М2М: Мастера ↔ Навыки | 16 KB |
| 12 | masters | Мастера | 24 KB |
| 13 | notifications_outbox | Очередь уведомлений | 56 KB |
| 14 | offers | Офферы мастерам | 16 KB |
| 15 | order_autoclose_queue | Очередь автозакрытия заказов | 0 bytes |
| 16 | order_status_history | История статусов заказов | 24 KB |
| 17 | orders | Заказы | 24 KB |
| 18 | referral_rewards | Реферальные начисления | 8 KB |
| 19 | referrals | Реферальные связи | 8 KB |
| 20 | settings | Настройки системы | 48 KB |
| 21 | skills | Навыки (справочник) | 16 KB |
| 22 | staff_access_code_cities | М2М: Коды доступа ↔ Города | 8 KB |
| 23 | staff_access_codes | Коды доступа персонала | 16 KB |
| 24 | staff_cities | М2М: Персонал ↔ Города | 0 bytes |
| 25 | staff_users | Пользователи персонала (админы/логисты) | 48 KB |
| 26 | streets | Улицы | 24 KB |

---

## 📊 Статистика данных

| Таблица | Записей |
|---------|---------|
| cities | **0** ⚠️ |
| districts | **0** ⚠️ |
| streets | **0** ⚠️ |
| masters | **0** |
| orders | **0** |
| staff_users | **2** ✅ |
| skills | **0** ⚠️ |

---

## ⚠️ ОТСУТСТВУЮЩАЯ ТАБЛИЦА

### ❌ commission_deadline_notifications

**Статус:** Таблица НЕ существует в БД  
**Требуется:** Миграция `2025_10_16_0001_add_commission_deadline_notifications.py`  
**Ожидаемая структура:**
- `id` INTEGER PRIMARY KEY
- `commission_id` INTEGER FK → commissions(id) ON DELETE CASCADE
- `hours_before` SMALLINT NOT NULL
- `sent_at` TIMESTAMPTZ NULL
- UNIQUE CONSTRAINT (commission_id, hours_before)
- INDEX ON commission_id

**Версия миграции для применения:** После `4c2465ccb4e5`

---

## 🔍 Детали критичных таблиц

### 📋 masters (37 колонок)

| Колонка | Тип | NULL | Примечание |
|---------|-----|------|------------|
| id | integer | NO | PK |
| tg_user_id | bigint | YES | Telegram ID |
| full_name | varchar | NO | ФИО |
| phone | varchar | YES | Телефон |
| city_id | integer | YES | FK → cities |
| rating | double precision | NO | Рейтинг |
| is_active | boolean | NO | Активен |
| is_blocked | boolean | NO | Заблокирован |
| moderation_status | enum | NO | Статус модерации |
| shift_status | enum | NO | Статус смены |
| break_until | timestamptz | YES | Конец перерыва |
| has_vehicle | boolean | NO | Есть авто |
| max_active_orders_override | smallint | YES | Лимит заказов |
| is_on_shift | boolean | NO | На смене |
| verified | boolean | NO | Верифицирован |
| is_deleted | boolean | NO | Удалён |
| ... | ... | ... | +20 колонок |

**✅ Нет колонки:** `patronymic` (не нужна, есть `full_name`)  
**✅ Алиас работает:** `tg_id` → `tg_user_id` через synonym

---

### 📋 order_status_history (10 колонок)

| Колонка | Тип | NULL | Примечание |
|---------|-----|------|------------|
| id | integer | NO | PK |
| order_id | integer | NO | FK → orders |
| from_status | enum | YES | Из статуса |
| to_status | enum | NO | В статус |
| reason | text | YES | Причина |
| changed_by_staff_id | integer | YES | ID персонала |
| changed_by_master_id | integer | YES | ID мастера |
| created_at | timestamptz | YES | Время |
| **actor_type** | **enum** | **NO** | **Тип актора** ✅ |
| context | jsonb | NO | Контекст |

**✅ actor_type уже NOT NULL** - фикс 5 применён в миграции!

---

### 📋 offers (индексы)

| Индекс | Тип | Определение |
|--------|-----|-------------|
| pk_offers | UNIQUE | (id) |
| uq_offers__order_master | UNIQUE | (order_id, master_id) |
| ix_offers__order_state | INDEX | (order_id, state) |
| ix_offers__master_state | INDEX | (master_id, state) |
| **uix_offers__order_accepted_once** | **UNIQUE PARTIAL** | **(order_id) WHERE state='ACCEPTED'** ✅ |
| ix_offers__expires_at | INDEX | (expires_at) |

**✅ Partial unique index существует** - предотвращает двойное принятие!

---

## 🚨 Проблемы и требования

### 1. ❌ Отсутствует таблица commission_deadline_notifications
**Действие:** Применить миграцию

### 2. ⚠️ Пустые справочники
- **cities:** 0 записей (должно быть 79)
- **districts:** 0 записей
- **skills:** 0 записей

**Причина:** Тесты создают данные через фабрики/фикстуры  
**Решение:** Улучшить `autouse` фикстуру для базовых seed-данных

### 3. ⚠️ Пользователь distribution_metrics
Таблица `distribution_metrics` принадлежит `fs_user`, а не `field_user`  
**Возможная проблема:** При миграциях могут быть права доступа

---

## 🎯 Что нужно сделать

### Высокий приоритет
1. ✅ Применить миграцию `2025_10_16_0001_add_commission_deadline_notifications.py`
2. ⚠️ Засидить минимальные данные:
   - 1 город (Москва)
   - 1 район (Центральный)
   - 6 навыков (ELECTRICS, PLUMBING, etc.)

### Средний приоритет
3. Проверить права на `distribution_metrics` (fs_user vs field_user)

---

## 📝 Команды для работы с БД

### Подключение
```bash
docker exec -it field-service-postgres-1 psql -U field_user -d field_service_test
```

### Применить миграцию
```bash
cd C:\ProjectF\field-service
.venv\Scripts\python.exe -m alembic upgrade head
```

### Экспорт схемы
```bash
docker exec field-service-postgres-1 pg_dump -U field_user -d field_service_test --schema-only > schema.sql
```

### Очистить данные
```sql
TRUNCATE TABLE orders, masters, commissions, offers CASCADE;
```

---

## ✅ Что уже исправлено

1. ✅ **actor_type NOT NULL** - уже применено в миграции `2025_10_16_0002_make_actor_type_not_null.py`
2. ✅ **Partial unique index на offers** - предотвращает race condition
3. ✅ **Алиас tg_id в models.py** - работает через synonym
4. ✅ **Структура masters** - полная, без patronymic

---

**Статус:** База готова к тестам, требуется только добавить таблицу `commission_deadline_notifications`
