# Field Service v1.2 – Operations Notes

## Runtime Monitoring
- Heartbeat: both bots emit `<name> alive` every 60 seconds to the LOGS channel.
- Alerts: distribution escalations, overdue commissions and unexpected errors go to ALERTS.
- Single instance: if a bot receives HTTP 409 it writes a log entry and exits so only one worker stays active.

## Database & Migrations
- Source of truth: frozen TZ v1.2. All schema changes are Alembic migrations (async env) stored under `alembic/versions/`.
- Core tables: `orders`, `order_status_history`, `offers`, `attachments`, `commissions`, `referrals`, `referral_rewards`, `masters`, `staff_users`, geo dictionaries (`cities`, `districts`, `streets`), `settings`.
- Key indexes per TZ:
  - Distribution queue: `ix_orders__status_city_timeslot_start`, `offers(order_id, state)`.
  - Preferred master & guarantees: `orders(preferred_master_id)`, `orders(type)`.
  - Finance watchdogs: `commissions(status, deadline_at)`, `commissions(master_id, status)`.
  - Staff scope: `staff_cities(staff_id, city_id)`.
- Constraints:
  - `ck_orders__timeslot_range`: `(timeslot_start_utc < timeslot_end_utc)` unless both values are `NULL`.
  - `pk_orders`, `uq_offers__order_master`, partial index `uix_offers__order_accepted_once` ensures a single accepted offer.
- Latest migrations (PR‑10A/PR‑10B):
  - `2025_09_27_0002_orders_add_v12_fields` adds v1.2 columns (`type`, `timeslot_start_utc`, `timeslot_end_utc`, `total_sum`, `lat`, `lon`, `no_district`) and backfills from legacy data.
  - `2025_09_27_0003_orders_drop_legacy_fields` removes the remaining pre-v1.2 slot/price/coordinate columns, recreates the status ENUM and enforces the new check/index set.

## Order Schema (v1.2)
- Coordinates: `lat`, `lon` (float, nullable).
- Slots: `timeslot_start_utc`, `timeslot_end_utc` (TIMESTAMPTZ). UI formatting uses `field_service.services.time_service.format_timeslot_local` with city time zones.
  - Working window: business validation of 10:00–20:00 is enforced at the service layer with the city's local time zone (see `field_service.services.time_service`). At the DB level, integrity is ensured by `ck_orders__timeslot_range` (`timeslot_start_utc < timeslot_end_utc`).
- Money: `total_sum` (NUMERIC(10,2)), `company_payment` (NUMERIC(10,2)).
- Workflow flags: `type` (`NORMAL`/`GUARANTEE`), `no_district`, `late_visit`, escalation timestamps, optimistic lock `version`.
- Status ENUM `order_status`: `CREATED`, `SEARCHING`, `ASSIGNED`, `EN_ROUTE`, `WORKING`, `PAYMENT`, `CLOSED`, `DEFERRED`, `GUARANTEE`, `CANCELED`.
- Legacy aliases from the pre-v1.2 schema are removed from ORM and DB. Use UTC slots and `total_sum` directly.

## Bots & Services
- Admin bot (aiogram 3.x) handles queue management, manual offers, finance approvals, staff/RBAC operations.
- Master bot manages onboarding, active/closed orders, payments and referral balances.
- Distribution worker ticks every 30 s (SLA 120 s, two rounds); guarantee orders prioritiSe the original master and autoblock on refusal.
- Heartbeat service keeps LOGS/ALERTS in sync; watchdog escalates overdue commissions after 3 hours.

## Environment (.env)
See `.env.example` for runnable demo values. Key settings:
- PostgreSQL via asyncpg (`DATABASE_URL`).
- Bot tokens (`MASTER_BOT_TOKEN`, `ADMIN_BOT_TOKEN`), city time zone (`TIMEZONE`), heartbeat interval (`HEARTBEAT_SECONDS`).
- Distribution config (`DISTRIBUTION_SLA_SECONDS`, `DISTRIBUTION_ROUNDS`), finance deadlines (`COMMISSION_DEADLINE_HOURS`).

## Backups
- Linux/macOS: schedule `ops/backup_db.sh` via cron (e.g. `0 2 * * * /bin/bash /app/ops/backup_db.sh`).
- Windows: Task Scheduler with `powershell.exe -File ops/backup_db.ps1`.
- Dumps are written to `backups/` (override with `BACKUP_DIR`). Files older than 7 days are pruned automatically.
- Ensure `DATABASE_URL` is configured before running the helper scripts.

