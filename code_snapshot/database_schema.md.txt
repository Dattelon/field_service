# База данных Field Service - Структура и описание

**Дата создания документа:** 14.10.2025  
**Версия БД:** PostgreSQL (asyncpg)  
**Назначение:** Система управления заявками на выезд мастеров (Field Service Management)

---

## 📋 Содержание

1. [Обзор системы](#обзор-системы)
2. [ENUM типы](#enum-типы)
3. [Таблицы](#таблицы)
4. [Связи между таблицами](#связи-между-таблицами)
5. [Индексы](#индексы)

---

## 🔍 Обзор системы

Система Field Service состоит из двух основных Telegram-ботов:
- **Master Bot** - для мастеров (исполнителей)
- **Admin Bot** - для администраторов и логистов

База данных обслуживает полный цикл работы с заказами:
- Создание и распределение заказов
- Управление мастерами и их навыками
- Финансовые операции (комиссии)
- Реферальная программа
- Географические данные (города, районы, улицы)
- Система доступа для персонала

**Всего таблиц:** 28  
**ENUM типов:** 11  
**Foreign Keys:** 50  
**Индексов:** 107

---

## 📊 ENUM типы

### actor_type
Тип актора, выполнившего действие
```sql
'SYSTEM'            -- Системное действие
'ADMIN'             -- Администратор
'MASTER'            -- Мастер
'AUTO_DISTRIBUTION' -- Автоматическое распределение
```

### attachment_entity
Тип сущности, к которой привязано вложение
```sql
'ORDER'      -- Заказ
'OFFER'      -- Оффер
'COMMISSION' -- Комиссия
'MASTER'     -- Мастер
```

### attachment_file_type
Тип файла вложения
```sql
'PHOTO'    -- Фотография
'DOCUMENT' -- Документ
'AUDIO'    -- Аудио
'VIDEO'    -- Видео
'OTHER'    -- Другое
```

### commission_status
Статус комиссии
```sql
'PENDING'  -- Ожидает создания
'PAID'     -- Оплачена (устаревший)
'OVERDUE'  -- Просрочена
'WAIT_PAY' -- Ожидает оплаты
'REPORTED' -- Мастер сообщил об оплате
'APPROVED' -- Админ подтвердил оплату
```

### moderation_status
Статус модерации мастера
```sql
'PENDING'  -- На модерации
'APPROVED' -- Одобрен
'REJECTED' -- Отклонен
```

### offer_state
Состояние оффера (предложения заказа мастеру)
```sql
'SENT'     -- Отправлен
'VIEWED'   -- Просмотрен
'ACCEPTED' -- Принят
'DECLINED' -- Отклонен
'EXPIRED'  -- Истёк срок
'CANCELED' -- Отменён
```

### order_category
Категория работ
```sql
'ELECTRICS'  -- Электрика
'PLUMBING'   -- Сантехника
'APPLIANCES' -- Бытовая техника
'WINDOWS'    -- Окна
'HANDYMAN'   -- Мастер на час
'ROADSIDE'   -- Автопомощь
```

### order_status
Статус заказа
```sql
'CREATED'   -- Создан
'SEARCHING' -- Поиск мастера
'ASSIGNED'  -- Назначен мастер
'EN_ROUTE'  -- Мастер в пути
'WORKING'   -- Мастер работает
'PAYMENT'   -- Ожидание оплаты
'CLOSED'    -- Закрыт
'DEFERRED'  -- Отложен
'GUARANTEE' -- Гарантийный
'CANCELED'  -- Отменён
```

### order_type
Тип заказа
```sql
'NORMAL'    -- Обычный
'GUARANTEE' -- Гарантийный
```

### payout_method
Способ выплаты мастеру
```sql
'CARD'         -- Банковская карта
'SBP'          -- Система быстрых платежей
'YOOMONEY'     -- ЮMoney
'BANK_ACCOUNT' -- Банковский счёт
```

### referral_reward_status
Статус реферальной награды
```sql
'ACCRUED'  -- Начислена
'PAID'     -- Выплачена
'CANCELED' -- Отменена
```

### shift_status
Статус смены мастера
```sql
'SHIFT_OFF' -- Смена выключена
'SHIFT_ON'  -- Смена включена
'BREAK'     -- Перерыв
```

### staff_role
Роль персонала
```sql
'ADMIN'        -- Администратор (устаревший)
'LOGIST'       -- Логист
'CITY_ADMIN'   -- Городской админ
'GLOBAL_ADMIN' -- Глобальный админ
```

---

## 📦 Таблицы

### 1. admin_audit_log
**Назначение:** Журнал действий администраторов

| Колонка | Тип | Nullable | Default | Описание |
|---------|-----|----------|---------|----------|
| id | integer | NO | nextval | ID записи |
| admin_id | integer | YES | null | ID администратора (FK → staff_users) |
| master_id | integer | YES | null | ID мастера (FK → masters) |
| action | varchar(64) | NO | - | Тип действия |
| payload_json | jsonb | NO | '{}' | Данные действия |
| created_at | timestamptz | NO | now() | Время создания |

**Индексы:**
- `pk_admin_audit_log` (UNIQUE) на id
- `ix_admin_audit_log_admin_id` на admin_id
- `ix_admin_audit_log_master_id` на master_id
- `ix_admin_audit_log_created_at` на created_at

---

### 2. alembic_version
**Назначение:** Версия миграций БД (Alembic)

| Колонка | Тип | Nullable | Default | Описание |
|---------|-----|----------|---------|----------|
| version_num | varchar(32) | NO | - | Номер версии |

**Индексы:**
- `alembic_version_pkc` (UNIQUE) на version_num

---

### 3. attachments
**Назначение:** Вложения (файлы) к различным сущностям

| Колонка | Тип | Nullable | Default | Описание |
|---------|-----|----------|---------|----------|
| id | integer | NO | nextval | ID вложения |
| entity_type | attachment_entity | NO | - | Тип сущности |
| entity_id | bigint | NO | - | ID сущности |
| file_type | attachment_file_type | NO | - | Тип файла |
| file_id | varchar(256) | NO | - | Telegram file_id |
| file_unique_id | varchar(256) | YES | null | Уникальный ID файла |
| file_name | varchar(256) | YES | null | Имя файла |
| mime_type | varchar(128) | YES | null | MIME тип |
| size | integer | YES | null | Размер в байтах |
| caption | text | YES | null | Подпись |
| uploaded_by_master_id | integer | YES | null | Загружено мастером (FK → masters) |
| uploaded_by_staff_id | integer | YES | null | Загружено персоналом (FK → staff_users) |
| created_at | timestamptz | YES | now() | Время загрузки |
| document_type | varchar(32) | YES | null | Тип документа |

**Индексы:**
- `pk_attachments` (UNIQUE) на id
- `ix_attachments__etype_eid` на (entity_type, entity_id)

---

### 4. cities
**Назначение:** Справочник городов

| Колонка | Тип | Nullable | Default | Описание |
|---------|-----|----------|---------|----------|
| id | integer | NO | nextval | ID города |
| name | varchar(120) | NO | - | Название города |
| is_active | boolean | NO | true | Активен ли |
| created_at | timestamptz | YES | now() | Время создания |
| updated_at | timestamptz | YES | now() | Время обновления |
| timezone | varchar(64) | YES | null | Часовой пояс |
| centroid_lat | double precision | YES | null | Широта центра |
| centroid_lon | double precision | YES | null | Долгота центра |

**Индексы:**
- `pk_cities` (UNIQUE) на id
- `uq_cities__name` (UNIQUE) на name

---

### 5. commission_deadline_notifications
**Назначение:** Уведомления о дедлайне комиссий

| Колонка | Тип | Nullable | Default | Описание |
|---------|-----|----------|---------|----------|
| id | integer | NO | nextval | ID уведомления |
| commission_id | integer | NO | - | ID комиссии (FK → commissions) |
| hours_before | smallint | NO | - | За сколько часов до дедлайна |
| sent_at | timestamptz | NO | now() | Время отправки |

**Индексы:**
- `commission_deadline_notifications_pkey` (UNIQUE) на id
- `ix_commission_deadline_notifications__commission` на commission_id
- `uq_commission_deadline_notifications__commission_hours` (UNIQUE) на (commission_id, hours_before)

---

### 6. commissions
**Назначение:** Комиссии с мастеров за выполненные заказы

| Колонка | Тип | Nullable | Default | Описание |
|---------|-----|----------|---------|----------|
| id | integer | NO | nextval | ID комиссии |
| order_id | integer | NO | - | ID заказа (FK → orders) |
| master_id | integer | NO | - | ID мастера (FK → masters) |
| amount | numeric | NO | - | Сумма комиссии |
| percent | numeric | YES | null | Процент (устаревший) |
| status | commission_status | NO | - | Статус |
| deadline_at | timestamptz | NO | - | Дедлайн оплаты |
| paid_at | timestamptz | YES | null | Время оплаты (устаревший) |
| blocked_applied | boolean | NO | false | Применена ли блокировка |
| blocked_at | timestamptz | YES | null | Время блокировки |
| payment_reference | varchar(120) | YES | null | Ссылка на платёж |
| created_at | timestamptz | YES | now() | Время создания |
| updated_at | timestamptz | YES | now() | Время обновления |
| rate | numeric | YES | null | Ставка комиссии (%) |
| paid_reported_at | timestamptz | YES | null | Мастер сообщил об оплате |
| paid_approved_at | timestamptz | YES | null | Админ подтвердил оплату |
| paid_amount | numeric | YES | null | Сумма оплаты |
| is_paid | boolean | NO | false | Оплачена ли |
| has_checks | boolean | NO | false | Есть ли чеки |
| pay_to_snapshot | jsonb | YES | null | Снапшот реквизитов |

**Индексы:**
- `pk_commissions` (UNIQUE) на id
- `uq_commissions__order_id` (UNIQUE) на order_id
- `ix_commissions__ispaid_deadline` на (is_paid, deadline_at)
- `ix_commissions__master_status` на (master_id, status)
- `ix_commissions__status_deadline` на (status, deadline_at)

---

### 7. distribution_metrics
**Назначение:** Метрики распределения заказов

| Колонка | Тип | Nullable | Default | Описание |
|---------|-----|----------|---------|----------|
| id | integer | NO | nextval | ID записи |
| order_id | integer | NO | - | ID заказа (FK → orders) |
| master_id | integer | YES | - | ID мастера (FK → masters) |
| assigned_at | timestamptz | NO | now() | Время назначения |
| round_number | smallint | NO | - | Номер раунда |
| candidates_count | smallint | NO | - | Кол-во кандидатов |
| time_to_assign_seconds | integer | YES | null | Время до назначения (сек) |
| preferred_master_used | boolean | NO | false | Использован приоритетный мастер |
| was_escalated_to_logist | boolean | NO | false | Эскалировано логисту |
| was_escalated_to_admin | boolean | NO | false | Эскалировано админу |
| city_id | integer | NO | - | ID города (FK → cities) |
| district_id | integer | YES | - | ID района (FK → districts) |
| category | varchar(50) | YES | null | Категория |
| order_type | varchar(32) | YES | null | Тип заказа |
| metadata_json | jsonb | NO | '{}' | Метаданные |
| created_at | timestamptz | NO | now() | Время создания |

**Индексы:**
- `distribution_metrics_pkey` (UNIQUE) на id
- `idx_distribution_metrics_city_id` на city_id
- `idx_distribution_metrics_district_id` на district_id
- `idx_distribution_metrics_master_id` на master_id
- `idx_distribution_metrics_order_id` на order_id
- `ix_distribution_metrics__assigned_at_desc` на (assigned_at DESC)
- `ix_distribution_metrics__city_assigned` на (city_id, assigned_at)
- `ix_distribution_metrics__performance` на (round_number, time_to_assign_seconds)

---

### 8. districts
**Назначение:** Справочник районов городов

| Колонка | Тип | Nullable | Default | Описание |
|---------|-----|----------|---------|----------|
| id | integer | NO | nextval | ID района |
| city_id | integer | NO | - | ID города (FK → cities) |
| name | varchar(120) | NO | - | Название района |
| created_at | timestamptz | YES | now() | Время создания |
| centroid_lat | double precision | YES | null | Широта центра |
| centroid_lon | double precision | YES | null | Долгота центра |

**Индексы:**
- `pk_districts` (UNIQUE) на id
- `uq_districts__city_name` (UNIQUE) на (city_id, name)
- `ix_districts__city_id` на city_id

---

### 9. geocache
**Назначение:** Кэш геокодирования адресов

| Колонка | Тип | Nullable | Default | Описание |
|---------|-----|----------|---------|----------|
| query | varchar(255) | NO | - | Запрос геокодирования |
| lat | double precision | YES | null | Широта |
| lon | double precision | YES | null | Долгота |
| provider | varchar(32) | YES | null | Провайдер геокодирования |
| confidence | integer | YES | null | Уровень уверенности |
| created_at | timestamptz | NO | CURRENT_TIMESTAMP | Время создания |

**Индексы:**
- `pk_geocache` (UNIQUE) на query
- `ix_geocache_created_at` на created_at

---

### 10. master_districts
**Назначение:** Связь мастеров с районами (многие-ко-многим)

| Колонка | Тип | Nullable | Default | Описание |
|---------|-----|----------|---------|----------|
| master_id | integer | NO | - | ID мастера (FK → masters) |
| district_id | integer | NO | - | ID района (FK → districts) |
| created_at | timestamptz | YES | now() | Время создания |

**Индексы:**
- `pk_master_districts` (UNIQUE) на (master_id, district_id)
- `ix_master_districts__district` на district_id

---

### 11. master_invite_codes
**Назначение:** Коды приглашения для мастеров

| Колонка | Тип | Nullable | Default | Описание |
|---------|-----|----------|---------|----------|
| id | integer | NO | nextval | ID кода |
| code | varchar(32) | NO | - | Код приглашения |
| city_id | integer | YES | - | ID города (FK → cities) |
| issued_by_staff_id | integer | YES | - | Выдал персонал (FK → staff_users) |
| used_by_master_id | integer | YES | - | Использовал мастер (FK → masters) |
| expires_at | timestamptz | YES | null | Истекает |
| is_revoked | boolean | NO | false | Отозван ли |
| used_at | timestamptz | YES | null | Время использования |
| comment | varchar(255) | YES | null | Комментарий |
| created_at | timestamptz | YES | now() | Время создания |
| updated_at | timestamptz | YES | now() | Время обновления |

**Индексы:**
- `pk_master_invite_codes` (UNIQUE) на id
- `ix_master_invite_codes__code` (UNIQUE) на code
- `ix_master_invite_codes__available` (UNIQUE) на code WHERE (используется условие)