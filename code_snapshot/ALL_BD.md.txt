# База данных Field Service - Полная структура

**Дата создания документа:** 2025-01-13  
**Версия системы:** v1.1  
**СУБД:** PostgreSQL 15+

## Оглавление

1. [Общее описание](#общее-описание)
2. [ENUM типы](#enum-типы)
3. [Таблицы](#таблицы)
4. [Связи между таблицами](#связи-между-таблицами)
5. [Индексы](#индексы)
6. [Диаграмма связей](#диаграмма-связей)

---

## Общее описание

База данных Field Service предназначена для управления системой выездного обслуживания. Содержит информацию о:
- Мастерах и их квалификациях
- Заказах и их статусах
- Административном персонале
- Географических данных (города, районы, улицы)
- Финансовых операциях (комиссии, реферальные вознаграждения)
- Системных настройках

**Основные принципы:**
- Использование ENUM типов для статусов и категорий
- Аудит всех изменений через таблицы истории
- Мягкое удаление записей (is_deleted, is_active флаги)
- Временные метки с часовыми поясами (timestamp with time zone)
- JSONB для гибких структур данных

---

## ENUM типы

### actor_type
Тип актора, совершающего действие в системе.

| Значение | Описание |
|----------|----------|
| SYSTEM | Системное действие (автоматика) |
| ADMIN | Действие администратора |
| MASTER | Действие мастера |
| AUTO_DISTRIBUTION | Действие автоматического распределения |

### attachment_entity
Тип сущности, к которой привязано вложение.

| Значение | Описание |
|----------|----------|
| ORDER | Заказ |
| OFFER | Предложение |
| COMMISSION | Комиссия |
| MASTER | Мастер |

### attachment_file_type
Тип файла вложения.

| Значение | Описание |
|----------|----------|
| PHOTO | Фотография |
| DOCUMENT | Документ |
| AUDIO | Аудио |
| VIDEO | Видео |
| OTHER | Другое |

### commission_status
Статус комиссии.

| Значение | Описание |
|----------|----------|
| PENDING | Ожидает оплаты |
| PAID | Оплачено |
| OVERDUE | Просрочено |
| WAIT_PAY | Ожидание оплаты |
| REPORTED | Мастер сообщил об оплате |
| APPROVED | Оплата подтверждена админом |

### moderation_status
Статус модерации мастера.

| Значение | Описание |
|----------|----------|
| PENDING | На модерации |
| APPROVED | Одобрен |
| REJECTED | Отклонен |

### offer_state
Состояние предложения (оффера) мастеру.

| Значение | Описание |
|----------|----------|
| SENT | Отправлено |
| VIEWED | Просмотрено |
| ACCEPTED | Принято |
| DECLINED | Отклонено |
| EXPIRED | Истекло |
| CANCELED | Отменено |

### order_category
Категория работ.

| Значение | Описание |
|----------|----------|
| ELECTRICS | Электрика |
| PLUMBING | Сантехника |
| APPLIANCES | Бытовая техника |
| WINDOWS | Окна |
| HANDYMAN | Универсал на час |
| ROADSIDE | Автопомощь |

### order_status
Статус заказа.

| Значение | Описание |
|----------|----------|
| CREATED | Создан |
| SEARCHING | В поиске мастера |
| ASSIGNED | Назначен мастер |
| EN_ROUTE | Мастер в пути |
| WORKING | Мастер работает |
| PAYMENT | Ожидание оплаты |
| CLOSED | Закрыт |
| DEFERRED | Отложен |
| GUARANTEE | Гарантийный |
| CANCELED | Отменен |

### order_type
Тип заказа.

| Значение | Описание |
|----------|----------|
| NORMAL | Обычный заказ |
| GUARANTEE | Гарантийный заказ |

### payout_method
Способ выплаты.

| Значение | Описание |
|----------|----------|
| CARD | Банковская карта |
| SBP | Система быстрых платежей |
| YOOMONEY | ЮМoney |
| BANK_ACCOUNT | Банковский счет |

### referral_reward_status
Статус реферального вознаграждения.

| Значение | Описание |
|----------|----------|
| ACCRUED | Начислено |
| PAID | Выплачено |
| CANCELED | Отменено |

### shift_status
Статус смены мастера.

| Значение | Описание |
|----------|----------|
| SHIFT_OFF | Смена выключена |
| SHIFT_ON | Смена включена |
| BREAK | Перерыв |

### staff_role
Роль административного персонала.

| Значение | Описание |
|----------|----------|
| ADMIN | Администратор (устаревшее) |
| LOGIST | Логист |
| CITY_ADMIN | Городской администратор |
| GLOBAL_ADMIN | Глобальный администратор |

---

## Таблицы

### admin_audit_log
Журнал действий администраторов.

| Колонка | Тип | NULL | По умолчанию | Описание |
|---------|-----|------|--------------|----------|
| id | integer | NO | nextval | Первичный ключ |
| admin_id | integer | YES | NULL | ID администратора (FK → staff_users) |
| master_id | integer | YES | NULL | ID мастера (FK → masters) |
| action | varchar(64) | NO | - | Действие |
| payload_json | jsonb | NO | '{}' | Данные действия |
| created_at | timestamptz | NO | now() | Время создания |

**Индексы:**
- PRIMARY KEY (id)
- INDEX (admin_id)
- INDEX (master_id)
- INDEX (created_at)

**Внешние ключи:**
- admin_id → staff_users(id)
- master_id → masters(id)

---

### alembic_version
Версия миграций Alembic.

| Колонка | Тип | NULL | Описание |
|---------|-----|------|----------|
| version_num | varchar(32) | NO | Номер версии |

**Индексы:**
- PRIMARY KEY (version_num)

---

### attachments
Вложения (файлы).

| Колонка | Тип | NULL | По умолчанию | Описание |
|---------|-----|------|--------------|----------|
| id | integer | NO | nextval | Первичный ключ |
| entity_type | attachment_entity | NO | - | Тип сущности |
| entity_id | bigint | NO | - | ID сущности |
| file_type | attachment_file_type | NO | - | Тип файла |
| file_id | varchar(256) | NO | - | Telegram file_id |
| file_unique_id | varchar(256) | YES | NULL | Уникальный ID файла |
| file_name | varchar(256) | YES | NULL | Имя файла |
| mime_type | varchar(128) | YES | NULL | MIME тип |
| size | integer | YES | NULL | Размер в байтах |
| caption | text | YES | NULL | Подпись |
| uploaded_by_master_id | integer | YES | NULL | Кто загрузил (мастер) |
| uploaded_by_staff_id | integer | YES | NULL | Кто загрузил (персонал) |
| created_at | timestamptz | YES | now() | Время создания |
| document_type | varchar(32) | YES | NULL | Тип документа |

**Индексы:**
- PRIMARY KEY (id)
- INDEX (entity_type, entity_id)

**Внешние ключи:**
- uploaded_by_master_id → masters(id)
- uploaded_by_staff_id → staff_users(id)

---

### cities
Города.

| Колонка | Тип | NULL | По умолчанию | Описание |
|---------|-----|------|--------------|----------|
| id | integer | NO | nextval | Первичный ключ |
| name | varchar(120) | NO | - | Название города |
| is_active | boolean | NO | true | Активен |
| created_at | timestamptz | YES | now() | Создан |
| updated_at | timestamptz | YES | now() | Обновлен |
| timezone | varchar(64) | YES | NULL | Часовой пояс (IANA) |
| centroid_lat | double precision | YES | NULL | Широта центра |
| centroid_lon | double precision | YES | NULL | Долгота центра |

**Индексы:**
- PRIMARY KEY (id)
- UNIQUE (name)

---

### commission_deadline_notifications
Уведомления о дедлайнах комиссий.

| Колонка | Тип | NULL | По умолчанию | Описание |
|---------|-----|------|--------------|----------|
| id | integer | NO | nextval | Первичный ключ |
| commission_id | integer | NO | - | ID комиссии |
| hours_before | smallint | NO | - | За сколько часов до дедлайна |
| sent_at | timestamptz | NO | now() | Когда отправлено |

**Индексы:**
- PRIMARY KEY (id)
- INDEX (commission_id)
- UNIQUE (commission_id, hours_before)

**Внешние ключи:**
- commission_id → commissions(id)

---

### commissions
Комиссии с мастеров.

| Колонка | Тип | NULL | По умолчанию | Описание |
|---------|-----|------|--------------|----------|
| id | integer | NO | nextval | Первичный ключ |
| order_id | integer | NO | - | ID заказа |
| master_id | integer | NO | - | ID мастера |
| amount | numeric | NO | - | Сумма комиссии |
| percent | numeric | YES | NULL | Процент комиссии |
| status | commission_status | NO | - | Статус |
| deadline_at | timestamptz | NO | - | Дедлайн оплаты |
| paid_at | timestamptz | YES | NULL | Когда оплачено |
| blocked_applied | boolean | NO | false | Блокировка применена |
| blocked_at | timestamptz | YES | NULL | Когда заблокирован |
| payment_reference | varchar(120) | YES | NULL | Референс платежа |
| created_at | timestamptz | YES | now() | Создано |
| updated_at | timestamptz | YES | now() | Обновлено |
| rate | numeric | YES | NULL | Ставка комиссии |
| paid_reported_at | timestamptz | YES | NULL | Мастер сообщил об оплате |
| paid_approved_at | timestamptz | YES | NULL | Админ подтвердил оплату |
| paid_amount | numeric | YES | NULL | Оплаченная сумма |
| is_paid | boolean | NO | false | Оплачено |
| has_checks | boolean | NO | false | Есть чеки |
| pay_to_snapshot | jsonb | YES | NULL | Снапшот реквизитов для оплаты |

**Индексы:**
- PRIMARY KEY (id)
- UNIQUE (order_id)
- INDEX (master_id, status)
- INDEX (status, deadline_at)
- INDEX (is_paid, deadline_at)

**Внешние ключи:**
- order_id → orders(id)
- master_id → masters(id)

---

### distribution_metrics
Метрики распределения заказов.

| Колонка | Тип | NULL | По умолчанию | Описание |
|---------|-----|------|--------------|----------|
| id | integer | NO | nextval | Первичный ключ |
| order_id | integer | NO | - | ID заказа |
| master_id | integer | YES | NULL | ID мастера |
| assigned_at | timestamptz | NO | now() | Время назначения |
| round_number | smallint | NO | - | Номер раунда |
| candidates_count | smallint | NO | - | Количество кандидатов |
| time_to_assign_seconds | integer | YES | NULL | Время до назначения (сек) |
| preferred_master_used | boolean | NO | false | Использован предпочт. мастер |
| was_escalated_to_logist | boolean | NO | false | Эскалация логисту |
| was_escalated_to_admin | boolean | NO | false | Эскалация админу |
| city_id | integer | NO | - | ID города |
| district_id | integer | YES | NULL | ID района |
| category | varchar(50) | YES | NULL | Категория |
| order_type | varchar(32) | YES | NULL | Тип заказа |
| metadata_json | jsonb | NO | '{}' | Дополнительные данные |
| created_at | timestamptz | NO | now() | Создано |

**Индексы:**
- PRIMARY KEY (id)
- INDEX (order_id)
- INDEX (master_id)
- INDEX (city_id)
- INDEX (district_id)
- INDEX (assigned_at DESC)
- INDEX (city_id, assigned_at)
- INDEX (round_number, time_to_assign_seconds)

**Внешние ключи:**
- order_id → orders(id)
- master_id → masters(id)
- city_id → cities(id)
- district_id → districts(id)

---

### districts
Районы/округа городов.

| Колонка | Тип | NULL | По умолчанию | Описание |
|---------|-----|------|--------------|----------|
| id | integer | NO | nextval | Первичный ключ |
| city_id | integer | NO | - | ID города |
| name | varchar(120) | NO | - | Название района |
| created_at | timestamptz | YES | now() | Создано |
| centroid_lat | double precision | YES | NULL | Широта центра |
| centroid_lon | double precision | YES | NULL | Долгота центра |

**Индексы:**
- PRIMARY KEY (id)
- INDEX (city_id)
- UNIQUE (city_id, name)

**Внешние ключи:**
- city_id → cities(id)

---

### geocache
Кэш геокодирования.

| Колонка | Тип | NULL | По умолчанию | Описание |
|---------|-----|------|--------------|----------|
| query | varchar(255) | NO | - | Запрос геокодирования |
| lat | double precision | YES | NULL | Широта |
| lon | double precision | YES | NULL | Долгота |
| provider | varchar(32) | YES | NULL | Провайдер геокодирования |
| confidence | integer | YES | NULL | Уверенность (0-100) |
| created_at | timestamptz | NO | CURRENT_TIMESTAMP | Создано |

**Индексы:**
- PRIMARY KEY (query)
- INDEX (created_at)

---

### master_districts
Связь мастеров и районов (многие-ко-многим).

| Колонка | Тип | NULL | По умолчанию | Описание |
|---------|-----|------|--------------|----------|
| master_id | integer | NO | - | ID мастера |
| district_id | integer | NO | - | ID района |
| created_at | timestamptz | YES | now() | Создано |

**Индексы:**
- PRIMARY KEY (master_id, district_id)
- INDEX (district_id)

**Внешние ключи:**
- master_id → masters(id)
- district_id → districts(id)

---

### master_invite_codes
Инвайт-коды для мастеров.

| Колонка | Тип | NULL | По умолчанию | Описание |
|---------|-----|------|--------------|----------|
| id | integer | NO | nextval | Первичный ключ |
| code | varchar(32) | NO | - | Код |
| city_id | integer | YES | NULL | ID города |
| issued_by_staff_id | integer | YES | NULL | Кто выдал |
| used_by_master_id | integer | YES | NULL | Кто использовал |
| expires_at | timestamptz | YES | NULL | Истекает |
| is_revoked | boolean | NO | false | Отозван |
| used_at | timestamptz | YES | NULL | Когда использован |
| comment | varchar(255) | YES | NULL | Комментарий |
| created_at | timestamptz | YES | now() | Создан |
| updated_at | timestamptz | YES | now() | Обновлен |

**Индексы:**
- PRIMARY KEY (id)
- UNIQUE (code)
- UNIQUE (code) WHERE used_by_master_id IS NULL AND is_revoked = false AND expires_at IS NULL

**Внешние ключи:**
- city_id → cities(id)
- issued_by_staff_id → staff_users(id)
- used_by_master_id → masters(id)

---

### master_skills
Связь мастеров и навыков (многие-ко-многим).

| Колонка | Тип | NULL | По умолчанию | Описание |
|---------|-----|------|--------------|----------|
| master_id | integer | NO | - | ID мастера |
| skill_id | integer | NO | - | ID навыка |
| created_at | timestamptz | YES | now() | Создано |

**Индексы:**
- PRIMARY KEY (master_id, skill_id)
- INDEX (skill_id)

**Внешние ключи:**
- master_id → masters(id)
- skill_id → skills(id)

---

### masters
Мастера.

| Колонка | Тип | NULL | По умолчанию | Описание |
|---------|-----|------|--------------|----------|
| id | integer | NO | nextval | Первичный ключ |
| tg_user_id | bigint | YES | NULL | Telegram user ID |
| full_name | varchar(160) | NO | - | ФИО |
| phone | varchar(32) | YES | NULL | Телефон |
| city_id | integer | YES | NULL | ID города |
| rating | double precision | NO | 5.0 | Рейтинг |
| is_active | boolean | NO | true | Активен |
| is_blocked | boolean | NO | false | Заблокирован |
| blocked_at | timestamptz | YES | NULL | Когда заблокирован |
| blocked_reason | text | YES | NULL | Причина блокировки |
| referral_code | varchar(32) | YES | NULL | Реферальный код |
| referred_by_master_id | integer | YES | NULL | Кто пригласил |
| last_heartbeat_at | timestamptz | YES | NULL | Последний heartbeat |
| created_at | timestamptz | YES | now() | Создан |
| updated_at | timestamptz | YES | now() | Обновлен |
| version | integer | NO | 1 | Версия (для оптимистичной блокировки) |
| moderation_status | moderation_status | NO | PENDING | Статус модерации |
| moderation_note | text | YES | NULL | Примечание модерации |
| shift_status | shift_status | NO | SHIFT_OFF | Статус смены |
| break_until | timestamptz | YES | NULL | Перерыв до |
| pdn_accepted_at | timestamptz | YES | NULL | Когда принял ПДн |
| payout_method | payout_method | YES | NULL | Способ выплаты |
| payout_data | jsonb | YES | NULL | Данные для выплаты |
| has_vehicle | boolean | NO | false | Есть авто |
| vehicle_plate | varchar(16) | YES | NULL | Номер авто |
| home_latitude | numeric | YES | NULL | Широта дома |
| home_longitude | numeric | YES | NULL | Долгота дома |
| max_active_orders_override | smallint | YES | NULL | Переопределение лимита заказов |
| is_on_shift | boolean | NO | false | На смене |
| verified | boolean | NO | false | Верифицирован |
| is_deleted | boolean | NO | false | Удален |
| moderation_reason | text | YES | NULL | Причина модерации |
| verified_at | timestamptz | YES | NULL | Когда верифицирован |
| verified_by | integer | YES | NULL | Кем верифицирован |

**Индексы:**
- PRIMARY KEY (id)
- UNIQUE (tg_user_id)
- UNIQUE (referral_code)
- INDEX (city_id)
- INDEX (tg_user_id)
- INDEX (phone)
- INDEX (is_on_shift, verified)
- INDEX (moderation_status, shift_status)
- INDEX (referred_by_master_id)
- INDEX (last_heartbeat_at)
- INDEX (verified, is_active, is_deleted, city_id)

**Внешние ключи:**
- city_id → cities(id)
- referred_by_master_id → masters(id)
- verified_by → staff_users(id)

---

### notifications_outbox
Очередь уведомлений.

| Колонка | Тип | NULL | По умолчанию | Описание |
|---------|-----|------|--------------|----------|
| id | integer | NO | nextval | Первичный ключ |
| master_id | integer | NO | - | ID мастера |
| event | varchar(64) | NO | - | Событие |
| payload | jsonb | NO | '{}' | Данные |
| created_at | timestamptz | NO | now() | Создано |
| processed_at | timestamptz | YES | NULL | Обработано |
| attempt_count | integer | NO | 0 | Количество попыток |
| last_error | text | YES | NULL | Последняя ошибка |

**Индексы:**
- PRIMARY KEY (id)
- INDEX (master_id)
- INDEX (created_at)

**Внешние ключи:**
- master_id → masters(id)

---

### offers
Предложения (офферы) мастерам.

| Колонка | Тип | NULL | По умолчанию | Описание |
|---------|-----|------|--------------|----------|
| id | integer | NO | nextval | Первичный ключ |
| order_id | integer | NO | - | ID заказа |
| master_id | integer | NO | - | ID мастера |
| round_number | smallint | NO | 1 | Номер раунда |
| state | offer_state | NO | - | Состояние |
| sent_at | timestamptz | YES | now() | Отправлено |
| responded_at | timestamptz | YES | NULL | Ответ получен |
| expires_at | timestamptz | YES | NULL | Истекает |
| created_at | timestamptz | YES | now() | Создано |

**Индексы:**
- PRIMARY KEY (id)
- INDEX (order_id, state)
- INDEX (master_id, state)
- INDEX (expires_at)
- UNIQUE (order_id, master_id) WHERE state IN ('SENT', 'VIEWED', 'ACCEPTED')
- UNIQUE (order_id) WHERE state = 'ACCEPTED'

**Внешние ключи:**
- order_id → orders(id)
- master_id → masters(id)

---

### order_autoclose_queue
Очередь автоматического закрытия заказов.

| Колонка | Тип | NULL | По умолчанию | Описание |
|---------|-----|------|--------------|----------|
| order_id | integer | NO | - | ID заказа |
| closed_at | timestamptz | NO | - | Когда закрыт |
| autoclose_at | timestamptz | NO | - | Когда автозакрыть |
| processed_at | timestamptz | YES | NULL | Когда обработан |
| created_at | timestamptz | NO | now() | Создано |

**Индексы:**
- PRIMARY KEY (order_id)
- INDEX (autoclose_at) WHERE processed_at IS NULL

**Внешние ключи:**
- order_id → orders(id)

---

### order_status_history
История статусов заказов.

| Колонка | Тип | NULL | По умолчанию | Описание |
|---------|-----|------|--------------|----------|
| id | integer | NO | nextval | Первичный ключ |
| order_id | integer | NO | - | ID заказа |
| from_status | order_status | YES | NULL | Из статуса |
| to_status | order_status | NO | - | В статус |
| reason | text | YES | NULL | Причина |
| changed_by_staff_id | integer | YES | NULL | Кем изменен (персонал) |
| changed_by_master_id | integer | YES | NULL | Кем изменен (мастер) |
| created_at | timestamptz | YES | now() | Создано |
| actor_type | actor_type | NO | - | Тип актора |
| context | jsonb | NO | '{}' | Контекст изменения |

**Индексы:**
- PRIMARY KEY (id)
- INDEX (order_id, created_at)
- INDEX (actor_type)

**Внешние ключи:**
- order_id → orders(id)
- changed_by_staff_id → staff_users(id)
- changed_by_master_id → masters(id)

---

### orders
Заказы.

| Колонка | Тип | NULL | По умолчанию | Описание |
|---------|-----|------|--------------|----------|
| id | integer | NO | nextval | Первичный ключ |
| city_id | integer | NO | - | ID города |
| district_id | integer | YES | NULL | ID района |
| street_id | integer | YES | NULL | ID улицы |
| house | varchar(32) | YES | NULL | Номер дома |
| apartment | varchar(32) | YES | NULL | Квартира |
| address_comment | text | YES | NULL | Комментарий к адресу |
| client_name | varchar(160) | YES | NULL | Имя клиента |
| client_phone | varchar(32) | YES | NULL | Телефон клиента |
| status | order_status | NO | CREATED | Статус |
| preferred_master_id | integer | YES | NULL | Предпочтительный мастер |
| assigned_master_id | integer | YES | NULL | Назначенный мастер |
| created_by_staff_id | integer | YES | NULL | Кем создан (персонал) |
| created_at | timestamptz | YES | now() | Создан |
| updated_at | timestamptz | YES | now() | Обновлен |
| version | integer | NO | 1 | Версия |
| company_payment | numeric | NO | 0 | Оплата от компании |
| guarantee_source_order_id | integer | YES | NULL | Исходный заказ (для гарантии) |
| order_type | order_type | NO | NORMAL | Тип заказа |
| category | order_category | YES | NULL | Категория |
| description | text | YES | NULL | Описание |
| late_visit | boolean | NO | false | Поздний визит |
| dist_escalated_logist_at | timestamptz | YES | NULL | Эскалация логисту |
| dist_escalated_admin_at | timestamptz | YES | NULL | Эскалация админу |
| lat | numeric | YES | NULL | Широта |
| lon | numeric | YES | NULL | Долгота |
| timeslot_start_utc | timestamptz | YES | NULL | Начало слота |
| timeslot_end_utc | timestamptz | YES | NULL | Конец слота |
| total_sum | numeric | NO | 0 | Итоговая сумма |
| cancel_reason | text | YES | NULL | Причина отмены |
| no_district | boolean | NO | false | Без района |
| type | order_type | NO | NORMAL | Тип (дубль) |
| geocode_provider | varchar(32) | YES | NULL | Провайдер геокодирования |
| geocode_confidence | integer | YES | NULL | Уверенность геокодирования |
| escalation_logist_notified_at | timestamptz | YES | NULL | Уведомление логиста |
| escalation_admin_notified_at | timestamptz | YES | NULL | Уведомление админа |

**Индексы:**
- PRIMARY KEY (id)
- INDEX (city_id)
- INDEX (district_id)
- INDEX (street_id)
- INDEX (status, city_id)
- INDEX (city_id, status)
- INDEX (assigned_master_id)
- INDEX (preferred_master_id)
- INDEX (guarantee_source_order_id)
- INDEX (client_phone)
- INDEX (category)
- INDEX (created_at)
- INDEX (status, city_id, timeslot_start_utc)

**Внешние ключи:**
- city_id → cities(id)
- district_id → districts(id)
- street_id → streets(id)
- assigned_master_id → masters(id)
- preferred_master_id → masters(id)
- created_by_staff_id → staff_users(id)
- guarantee_source_order_id → orders(id)

---

### referral_rewards
Реферальные вознаграждения.

| Колонка | Тип | NULL | По умолчанию | Описание |
|---------|-----|------|--------------|----------|
| id | integer | NO | nextval | Первичный ключ |
| referrer_id | integer | NO | - | ID реферера |
| referred_master_id | integer | NO | - | ID приглашенного мастера |
| commission_id | integer | NO | - | ID комиссии |
| level | smallint | NO | - | Уровень (1/2) |
| percent | numeric | NO | - | Процент |
| amount | numeric | NO | - | Сумма |
| status | referral_reward_status | NO | - | Статус |
| paid_at | timestamptz | YES | NULL | Когда выплачено |
| created_at | timestamptz | YES | now() | Создано |

**Индексы:**
- PRIMARY KEY (id)
- UNIQUE (commission_id, level)
- INDEX (referrer_id, status)
- INDEX (referrer_id, created_at)
- INDEX (referred_master_id)

**Внешние ключи:**
- referrer_id → masters(id)
- referred_master_id → masters(id)
- commission_id → commissions(id)

---

### referrals
Реферальные связи.

| Колонка | Тип | NULL | По умолчанию | Описание |
|---------|-----|------|--------------|----------|
| id | integer | NO | nextval | Первичный ключ |
| master_id | integer | NO | - | ID мастера |
| referrer_id | integer | NO | - | ID реферера |
| created_at | timestamptz | YES | now() | Создано |

**Индексы:**
- PRIMARY KEY (id)
- UNIQUE (master_id)
- INDEX (master_id)
- INDEX (referrer_id)

**Внешние ключи:**
- master_id → masters(id)
- referrer_id → masters(id)

---

### settings
Системные настройки.

| Колонка | Тип | NULL | По умолчанию | Описание |
|---------|-----|------|--------------|----------|
| key | varchar(80) | NO | - | Ключ |
| value | text | NO | - | Значение |
| value_type | varchar(16) | NO | 'STR' | Тип значения |
| description | text | YES | NULL | Описание |
| created_at | timestamptz | YES | now() | Создано |
| updated_at | timestamptz | YES | now() | Обновлено |

**Индексы:**
- PRIMARY KEY (key)

---

### skills
Навыки/категории работ.

| Колонка | Тип | NULL | По умолчанию | Описание |
|---------|-----|------|--------------|----------|
| id | integer | NO | nextval | Первичный ключ |
| code | varchar(64) | NO | - | Код навыка |
| name | varchar(160) | NO | - | Название |
| is_active | boolean | NO | true | Активен |
| created_at | timestamptz | YES | now() | Создано |

**Индексы:**
- PRIMARY KEY (id)
- UNIQUE (code)

---

### staff_access_code_cities
Связь кодов доступа персонала и городов.

| Колонка | Тип | NULL | По умолчанию | Описание |
|---------|-----|------|--------------|----------|
| access_code_id | integer | NO | - | ID кода доступа |
| city_id | integer | NO | - | ID города |
| created_at | timestamptz | YES | now() | Создано |

**Индексы:**
- PRIMARY KEY (access_code_id, city_id)
- INDEX (access_code_id)
- INDEX (city_id)

**Внешние ключи:**
- access_code_id → staff_access_codes(id)
- city_id → cities(id)

---

### staff_access_codes
Коды доступа для персонала.

| Колонка | Тип | NULL | По умолчанию | Описание |
|---------|-----|------|--------------|----------|
| id | integer | NO | nextval | Первичный ключ |
| code | varchar(16) | NO | - | Код |
| role | staff_role | NO | - | Роль |
| city_id | integer | YES | NULL | ID города (устаревшее) |
| created_by_staff_id | integer | YES | NULL | Кем создан |
| used_by_staff_id | integer | YES | NULL | Кем использован |
| expires_at | timestamptz | YES | NULL | Истекает |
| used_at | timestamptz | YES | NULL | Когда использован |
| created_at | timestamptz | YES | now() | Создан |
| comment | text | YES | NULL | Комментарий |
| revoked_at | timestamptz | YES | NULL | Когда отозван |

**Индексы:**
- PRIMARY KEY (id)
- UNIQUE (code)
- UNIQUE (code) WHERE used_by_staff_id IS NULL AND revoked_at IS NULL

**Внешние ключи:**
- city_id → cities(id)
- created_by_staff_id → staff_users(id)
- used_by_staff_id → staff_users(id)

---

### staff_cities
Связь персонала и городов (многие-ко-многим).

| Колонка | Тип | NULL | По умолчанию | Описание |
|---------|-----|------|--------------|----------|
| staff_user_id | integer | NO | - | ID персонала |
| city_id | integer | NO | - | ID города |
| created_at | timestamptz | YES | now() | Создано |

**Индексы:**
- PRIMARY KEY (staff_user_id, city_id)
- INDEX (staff_user_id)
- INDEX (city_id)

**Внешние ключи:**
- staff_user_id → staff_users(id)
- city_id → cities(id)

---

### staff_users
Административный персонал.

| Колонка | Тип | NULL | По умолчанию | Описание |
|---------|-----|------|--------------|----------|
| id | integer | NO | nextval | Первичный ключ |
| tg_user_id | bigint | YES | NULL | Telegram user ID |
| username | varchar(64) | YES | NULL | Username |
| full_name | varchar(160) | YES | NULL | ФИО |
| phone | varchar(32) | YES | NULL | Телефон |
| role | staff_role | NO | - | Роль |
| is_active | boolean | NO | true | Активен |
| created_at | timestamptz | YES | now() | Создан |
| updated_at | timestamptz | YES | now() | Обновлен |
| commission_requisites | jsonb | NO | '{}' | Реквизиты для комиссий |

**Индексы:**
- PRIMARY KEY (id)
- UNIQUE (tg_user_id)

---

### streets
Улицы.

| Колонка | Тип | NULL | По умолчанию | Описание |
|---------|-----|------|--------------|----------|
| id | integer | NO | nextval | Первичный ключ |
| city_id | integer | NO | - | ID города |
| district_id | integer | YES | NULL | ID района |
| name | varchar(200) | NO | - | Название улицы |
| created_at | timestamptz | YES | now() | Создано |
| centroid_lat | double precision | YES | NULL | Широта центра |
| centroid_lon | double precision | YES | NULL | Долгота центра |

**Индексы:**
- PRIMARY KEY (id)
- INDEX (city_id)
- INDEX (district_id)
- UNIQUE (city_id, district_id, name)

**Внешние ключи:**
- city_id → cities(id)
- district_id → districts(id)

---

## Связи между таблицами

### Основные связи

#### Географические связи
```
cities (1) ←→ (N) districts
cities (1) ←→ (N) streets
districts (1) ←→ (N) streets
```

#### Мастера
```
cities (1) ←→ (N) masters
masters (1) ←→ (N) master_districts ←→ (N) districts
masters (1) ←→ (N) master_skills ←→ (N) skills
masters (1) ←→ (N) referrals (реферер)
masters (1) ←→ (1) referrals (приглашенный)
masters (1) ←→ (N) master_invite_codes (использованные коды)
staff_users (1) ←→ (N) master_invite_codes (выданные коды)
masters (1) ←→ (N) attachments (загруженные файлы)
staff_users (1) ←→ (N) attachments (загруженные файлы)
```

#### Заказы
```
cities (1) ←→ (N) orders
districts (1) ←→ (N) orders
streets (1) ←→ (N) orders
masters (1) ←→ (N) orders (preferred_master_id)
masters (1) ←→ (N) orders (assigned_master_id)
staff_users (1) ←→ (N) orders (created_by_staff_id)
orders (1) ←→ (N) order_status_history
orders (1) ←→ (N) offers
orders (1) ←→ (1) commissions
orders (1) ←→ (N) orders (guarantee_source_order_id)
orders (1) ←→ (1) order_autoclose_queue
orders (1) ←→ (N) distribution_metrics
```

#### Офферы и комиссии
```
masters (1) ←→ (N) offers
orders (1) ←→ (N) offers
masters (1) ←→ (N) commissions
orders (1) ←→ (1) commissions
commissions (1) ←→ (N) commission_deadline_notifications
commissions (1) ←→ (N) referral_rewards
```

#### Реферальная система
```
masters (1) ←→ (N) referral_rewards (referrer)
masters (1) ←→ (N) referral_rewards (referred_master)
commissions (1) ←→ (N) referral_rewards
```

#### Персонал
```
staff_users (1) ←→ (N) staff_cities ←→ (N) cities
staff_users (1) ←→ (N) staff_access_codes (created_by)
staff_users (1) ←→ (N) staff_access_codes (used_by)
staff_access_codes (1) ←→ (N) staff_access_code_cities ←→ (N) cities
staff_users (1) ←→ (N) admin_audit_log
masters (1) ←→ (N) admin_audit_log
staff_users (1) ←→ (N) masters (verified_by)
```

#### Уведомления
```
masters (1) ←→ (N) notifications_outbox
```

---

## Индексы

### Критически важные индексы

#### Для распределения заказов
- `orders(status, city_id, timeslot_start_utc)` - основной индекс для планировщика
- `masters(verified, is_active, is_deleted, city_id)` - быстрый поиск активных мастеров
- `masters(is_on_shift, verified)` - фильтр мастеров на смене
- `master_districts(district_id)` - поиск мастеров по району
- `master_skills(skill_id)` - поиск мастеров по навыкам

#### Для работы с комиссиями
- `commissions(is_paid, deadline_at)` - просроченные комиссии
- `commissions(master_id, status)` - комиссии мастера
- `commissions(status, deadline_at)` - очередь обработки

#### Для офферов
- `offers(order_id, state)` - офферы по заказу
- `offers(master_id, state)` - офферы мастера
- `offers(expires_at)` - истекающие офферы
- Уникальный индекс: только один ACCEPTED оффер на заказ
- Уникальный индекс: только один активный оффер на пару (order, master)

#### Для истории
- `order_status_history(order_id, created_at)` - история заказа
- `distribution_metrics(assigned_at DESC)` - последние распределения

#### Для поиска
- `cities(name)` - поиск городов
- `districts(city_id, name)` - поиск районов
- `streets(city_id, district_id, name)` - поиск улиц
- `orders(client_phone)` - поиск заказов по телефону
- `masters(phone)` - поиск мастеров по телефону
- `masters(tg_user_id)` - поиск мастеров по Telegram ID

---

## Диаграмма связей

### Основные сущности

```
┌─────────────────┐
│     cities      │
│  id, name, tz   │
└────────┬────────┘
         │
         ├─────────────────┬─────────────────┬─────────────────┐
         │                 │                 │                 │
┌────────▼────────┐ ┌──────▼──────┐  ┌──────▼──────┐  ┌──────▼──────┐
│   districts     │ │   streets   │  │   masters   │  │   orders    │
│ id, name, city  │ │ id, name... │  │ id, name... │  │ id, addr... │
└────────┬────────┘ └──────┬──────┘  └──────┬──────┘  └──────┬──────┘
         │                 │                 │                 │
         └─────────┬───────┘                 │                 │
                   │                         │                 │
              ┌────▼────┐               ┌────▼────┐       ┌────▼────┐
              │ streets │               │ offers  │       │ history │
              │ (город+ │               │ (заказ+ │       │ (заказ+ │
              │ район)  │               │ мастер) │       │ статус) │
              └─────────┘               └─────────┘       └─────────┘
```

### Процесс выполнения заказа

```
  CREATED
     │
     ▼
 SEARCHING ◄──── планировщик ◄──── мастера (фильтры)
     │                                │
     ▼                                │
 ASSIGNED ────► оффер ────► мастер принял
     │
     ▼
 EN_ROUTE ────► мастер в пути
     │
     ▼
  WORKING ────► мастер работает
     │
     ▼
  PAYMENT ────► акт + сумма ────► комиссия
     │                               │
     ▼                               ▼
  CLOSED                      оплата комиссии
                                    │
                                    ▼
                            реферальные вознаграждения
```

### Модерация мастера

```
регистрация ────► онбординг ────► модерация
                     │                │
                     ▼                ▼
              документы:        PENDING
              - паспорт             │
              - селфи               ▼
              - реквизиты      APPROVED ────► работа
                                    │
                                    ▼
                              REJECTED
```

---

## Примечания

### Оптимистичная блокировка
Таблицы `masters` и `orders` используют поле `version` для оптимистичной блокировки при конкурентных обновлениях.

### Мягкое удаление
Мастера используют флаг `is_deleted` вместо физического удаления для сохранения истории.

### Часовые пояса
Все timestamp поля используют тип `timestamp with time zone` для корректной работы с разными часовыми поясами.

### JSONB поля
- `attachments.file_data` - не используется
- `masters.payout_data` - данные для выплат (карта/СБП/банк)
- `commissions.pay_to_snapshot` - снапшот реквизитов владельца
- `staff_users.commission_requisites` - реквизиты для приема комиссий
- `order_status_history.context` - контекст изменения статуса
- `distribution_metrics.metadata_json` - доп. данные распределения
- `admin_audit_log.payload_json` - данные действия админа
- `notifications_outbox.payload` - данные уведомления

### Уникальные ограничения
- Один мастер может иметь только один активный оффер на заказ
- Один заказ может иметь только один принятый оффер
- Один заказ может иметь только одну комиссию
- Один мастер может быть приглашен только одним реферером

---

**Конец документа**

_Этот документ автоматически сгенерирован из структуры базы данных PostgreSQL._
