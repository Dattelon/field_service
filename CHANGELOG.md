# Changelog

## v1.2.0 — 2025-09-27
- Orders schema migrated to v1.2: added `type`, `timeslot_start_utc`, `timeslot_end_utc`, `total_sum`, `lat`, `lon`, `no_district`; legacy slot/price/coordinate fields removed by Alembic revision 2025_09_27_0003 with ENUM recreation and new `ck_orders__timeslot_range` + `ix_orders__status_city_timeslot_start`.
- ORM consolidated: SQLAlchemy models expose only v1.2 fields; services, bots and exports now read UTC slots and `total_sum` directly, shared helper `format_timeslot_local` renders windows per city time zone.
- Bots & distribution updated to final rules (SLA 120 s, two rounds, guarantee autoblock, no-district skip); finance flow enforces 3 h deadline, referral rewards (10%/5%) issued on approval, heartbeat/alerts unified.
- Exports produce CSV (UTF-8 BOM, `;`, ISO UTC) and XLSX (orders/commissions/ref_rewards) using the new columns; docs and .env refreshed with v1.2 guidance and smoke/UAT procedures.
- UAT freeze completed: slots/timeouts, guarantee loop, RBAC, finance watchdog, referrals, exports and ops monitoring verified per checklist; changelog frozen for release.

