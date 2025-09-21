# Field Service v1.2 — БД и миграции

Источник истины: ТЗ Field Service v1.2 (frozen). Схема покрывает таблицы:
`masters`, `orders`, `order_status_history`, `offers`, `attachments`, `commissions`,
`referrals`, `referral_rewards`, `cities`, `districts`, `streets`, `settings`,
`staff_users`, `staff_cities`. Индексы соответствуют типовым запросам из ТЗ:
- автораспределение: `orders(status, city_id, scheduled_date)`, `offers(order_id, state)`;
- просроченные комиссии: `commissions(status, deadline_at)`, `commissions(master_id, status)`;
- приоритет предыдущего мастера: `orders(preferred_master_id)`;
- фильтрация по статусу/городу: `orders(city_id, status)`;
- уникальность офферов: `uq_offers__order_master`;
- защита от гонок при назначении: частичный уникальный индекс `uix_offers__order_accepted_once`.

## Локальный запуск Postgres (Docker)
```bash
docker run --name fs-pg -e POSTGRES_PASSWORD=fs_password -e POSTGRES_USER=fs_user \
  -e POSTGRES_DB=field_service -p 5433:5432 -d postgres:15



---

## 13) Что уже закрыто по требованиям ТЗ

- **Order statuses**: `CREATED->SEARCHING->ASSIGNED->EN_ROUTE->WORKING->PAYMENT->CLOSED` + `DEFERRED`, `GUARANTEE`, `CANCELED` (ENUM `order_status`).  
- **Уникальность офферов**: `uq_offers__order_master` + частичный уникальный индекс «только один ACCEPTED».  
- **Фильтрация по статусу/городу**: индексы `ix_orders__status_city_date`, `ix_orders__city_status`.  
- **Слоты 10:00–20:00**: `CHECK ck_orders__slot_in_working_window`.  
- **Распределение (SLA 120с, 2 раунда)**: подготовлены поля `offers.round_number`, индексы под выборки.  
- **Финансы/комиссии (дедлайн 3 часа, автоблокировка)**: поля `deadline_at`, `status`, `blocked_applied`, ключевые индексы.  
- **Гарантия/приоритет предыдущего мастера**: `orders.preferred_master_id` (+ индекс), статус `GUARANTEE`.  
- **Рефералка 10%/5%**: `referrals` (L1), `referral_rewards` (фиксация начислений по уровням L1/L2).  
- **Мониторинги/heartbeat**: поле `masters.last_heartbeat_at` (+ индекс).  
- **409‑конфликт/идемпотентность назначений**: `orders.version` (optimistic lock), частичный уникальный индекс на ACCEPTED; все DDL с явными именами и в Alembic‑миграции.

---

## Чек‑лист проверки (Шаг 1 — скелет)

- [x] Структура репозитория создана; два entrypoint’а ботов (aiogram 3.x).  
- [x] SQLAlchemy 2.x (async, asyncpg), единый Base и naming_convention.  
- [x] Таблицы из задачи: `masters`, `orders`, `order_status_history`, `offers`, `attachments`, `commissions`, `referrals`, `referral_rewards`, `cities`, `districts`, `streets`, `settings`, `staff_users`, `staff_cities`.  
- [x] Индексы/уникальные/чек‑ограничения — по типовым запросам ТЗ.  
- [x] Alembic настроен (async env), добавлена первичная миграция `init_schema`.  
- [x] `.env.example` — демо-значения, без плейсхолдеров.  
- [x] README — раздел «БД и миграции», сценарии запуска/отката.  

---


