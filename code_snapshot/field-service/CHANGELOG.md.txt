# Changelog

## v1.2.2 — 2025-10-10
### Исправления
- **P0-BUGFIX-EXPIRED-OFFERS**: Добавлен dedicated watchdog для автоматической обработки истёкших офферов. Исправлена критическая проблема когда мастера пропадали из списков ручного назначения из-за "зависших" офферов в состоянии `SENT` после истечения `expires_at`. Watchdog `watchdog_expired_offers()` работает каждые 60 секунд, помечает все истёкшие офферы как `EXPIRED` и логирует в `live_log`. Ранее офферы обрабатывались только внутри `distribution_scheduler` для заказов в очереди, что приводило к задержкам до 15+ минут.
- **IMPORT-FIX-MASTERS**: Исправлен `NameError: name 'select_candidates' is not defined` в `field_service/bots/admin_bot/services/masters.py`. Добавлен недостающий импорт `from field_service.services.candidates import select_candidates`.

### Добавлено
- Watchdog `watchdog_expired_offers()` в `field_service/services/watchdogs.py` с интервалом 60 секунд
- Автоматический запуск watchdog вместе с админ-ботом
- Тесты `tests/test_watchdog_expired_offers.py` (6 test cases)
- Документация `docs/BUGFIX_EXPIRED_OFFERS_WATCHDOG.md`
- Quickstart `docs/BUGFIX_EXPIRED_OFFERS_QUICKSTART.md`

## v1.2.1 — 2025-10-03
### Исправления
- **CR-2025-10-03-FIX**: Исправлена валидация `staff.id` для GLOBAL_ADMIN в финансовых обработчиках. GLOBAL_ADMIN с `staff.id=0` теперь может подтверждать и отклонять комиссии. Изменена проверка с `staff.id <= 0` на `staff.id < 0` в трёх обработчиках (`cb_finance_approve_instant`, `finance_reject_reason`, `finance_approve_amount`).
- **CR-2025-10-03-FK-FIX**: Решена проблема FK-constraint при записи в `order_status_history`. GLOBAL_ADMIN теперь создаётся в таблице `staff_users` через SQL-скрипт `scripts/update_global_admin.sql`. Middleware обновлён для **безусловной** загрузки superuser из БД (убрана проверка `if not isinstance(staff, StaffUser)` для superuser), что гарантирует получение реального `staff.id` вместо виртуального объекта. Добавлена проверка: если superuser не найден в БД, доступ запрещается.
- **CR-2025-10-03-010**: Удалён legacy `distribution_worker.py` (800+ строк устаревшего кода). Production уже использовал современный `distribution_scheduler.py` с advisory locks, автопробуждением DEFERRED заказов и push-уведомлениями. Тесты мигрированы на использование публичного API (`tick_once`). Legacy файл сохранён как `.deprecated` для возможного отката.
- **HOTFIX-2025-10-03-IMPORT**: Исправлен ImportError в `candidates.py` - обновлён импорт с `distribution_worker` на `distribution_scheduler`. Добавлена функция `_max_active_limit_for()` в scheduler для полной совместимости.

## v1.2.0 — 2025-09-27
- Orders schema migrated to v1.2: added `type`, `timeslot_start_utc`, `timeslot_end_utc`, `total_sum`, `lat`, `lon`, `no_district`; legacy slot/price/coordinate fields removed by Alembic revision 2025_09_27_0003 with ENUM recreation and new `ck_orders__timeslot_range` + `ix_orders__status_city_timeslot_start`.
- ORM consolidated: SQLAlchemy models expose only v1.2 fields; services, bots and exports now read UTC slots and `total_sum` directly, shared helper `format_timeslot_local` renders windows per city time zone.
- Bots & distribution updated to final rules (SLA 120 s, two rounds, guarantee autoblock, no-district skip); finance flow enforces 3 h deadline, referral rewards (10%/5%) issued on approval, heartbeat/alerts unified.
- Exports produce CSV (UTF-8 BOM, `;`, ISO UTC) and XLSX (orders/commissions/ref_rewards) using the new columns; docs and .env refreshed with v1.2 guidance and smoke/UAT procedures.
- UAT freeze completed: slots/timeouts, guarantee loop, RBAC, finance watchdog, referrals, exports and ops monitoring verified per checklist; changelog frozen for release.

