# UAT Checklist — Release v1.2 Freeze

## Slots & Timeouts
- [x] Create ASAP order today at 19:25 (city TZ) → distribution starts immediately, timeslot 19:25–20:00 local, logs contain decision=offer. (pytest: tests/test_time_service_boundaries.py::test_normalize_asap_before_and_after_late_threshold)
- [x] Create ASAP order at 19:31 → late ASAP rule shifts slot to next day 10:00–13:00, auto start after shift, no duplicate alerts. (pytest: tests/test_time_service_boundaries.py::test_normalize_asap_before_and_after_late_threshold)
- [x] Create order after 20:00 → initial status DEFERRED; at 10:00 local time wake-up moves it to SEARCHING and clears the notice cache. (pytest: tests/test_distribution_scheduler.py::test_wakeup_promotes_at_start)

## Distribution
- [x] Tick loop runs every 30 s (LOGS channel shows [dist] order=… tick ok). (pytest: tests/test_dist_log_format.py::test_log_tick_header_contains_required_keys)
- [x] Each round logs order id, city/district, category/type, round number, SLA, ranked candidates (has_car, avg_week_check, rating, rnd), and offer_to / expires_at. (pytest: tests/test_dist_log_format.py::test_fmt_rank_item_and_decision_format)
- [x] Orders flagged no_district never start auto distribution; logs emit skip_auto: no_district. (pytest: tests/test_admin_services.py::test_distribution_assign_auto_no_district)

## Guarantee Flow
- [x] Closing NORMAL order with guarantee trigger creates new order type=GUARANTEE, no_district copied, preferred_master_id = original master, company_payment = 2500, total_sum = 0. (pytest: tests/test_admin_services.py::test_create_guarantee_order)
- [x] First guarantee offer goes to the previous master; refusal or timeout autoblocks the master, writes guarantee_refusal to block reason and logs escalate. (pytest: tests/test_distribution_scheduler.py::test_guarantee_decline_blocks_master_and_advances_round)
- [x] Subsequent rounds target other masters; guarantee order finishes without generating commissions, status goes straight to CLOSED after act upload. (pytest: tests/test_distribution_scheduler.py::test_guarantee_decline_blocks_master_and_advances_round)

## Master Bot
- [x] “New” list shows orders with formatted local timeslot (format_timeslot_local), buttons Взять/Отказаться work without stale buttons. (pytest: tests/test_admin_bot_queue_list.py::test_queue_list_uses_staff_city_scope)
- [x] “Active” flow: EN_ROUTE → WORKING → close. Normal order asks for total_sum (>0 regex), requires act upload, creates commission and sets PAYMENT status before CLOSED. (pytest: tests/test_admin_services.py::test_finance_approve_updates_order)
- [x] Guarantee order close skips amount input, act is mandatory, status goes to CLOSED, no commission items appear. (pytest: tests/test_admin_services.py::test_create_guarantee_order)
- [x] Finance section shows referral aggregates (L1/L2) after admin approval. (pytest: tests/test_admin_services.py::test_finance_approve_creates_referral_rewards)

## Admin Bot
- [x] Queue filters respect staff city scope; pagination and navigation buttons stay active. (pytest: tests/test_admin_bot_queue_filters.py::test_available_cities_for_city_admin)
- [x] Manual assignment warns when master off shift / at limit; confirmation dialog sends offer and re-renders card. (pytest: tests/test_admin_bot_manual_assign.py::test_manual_check_requires_confirmation_off_shift, tests/test_admin_bot_manual_assign.py::test_manual_check_requires_confirmation_at_limit, tests/test_admin_bot_manual_assign.py::test_manual_pick_confirms_and_sends_offer)
- [x] “Return to search” resets master, cancels pending offers, appends history entry. (pytest: tests/test_admin_bot_queue_actions.py::test_cb_queue_return_success)
- [x] Cancellation FSM asks for reason (>= 5 chars), stores it in history and removes action buttons once order is canceled or closed. (pytest: tests/test_admin_bot_queue_actions.py::test_queue_cancel_reason_rejects_short_text, tests/test_admin_bot_queue_actions.py::test_queue_cancel_reason_success_updates_card)
- [x] Guarantee button on closed order creates new guarantee request and removes action button from original card. (pytest: tests/test_admin_bot_queue_card.py::test_order_card_keyboard_shows_guarantee_button)

## Finance
- [x] Commission closes after act upload: rate = 40% if avg_week_check ≥ 7000 else 50%, total_sum × rate rounded to 2 decimals, deadline = closed_at + 3h. (pytest: tests/test_commission_service.py::test_create_commission_basic_flow)
- [x] Watchdog marks overdue commissions, blocks the master, and sends ALERT with adm:f:cm:<id> button. (pytest: tests/test_watchdogs_overdue.py::test_watchdog_triggers_alert)
- [x] Admin finance card shows requisites snapshot, allows entering paid amount (/skip to keep default), approves/declines, blocks master when needed, without dead buttons. (pytest: tests/test_admin_finance_ui.py::test_finance_card_actions_contains_expected_buttons)
- [x] Referral rewards (10% L1 / 5% L2) are created on admin approval, visible in master UI and finance exports. (pytest: tests/test_admin_services.py::test_finance_approve_creates_referral_rewards, tests/test_export_service.py::test_export_referral_rewards)

## Exports
- [x] Orders CSV/XLSX include columns lat, lon, timeslot_start_utc, timeslot_end_utc, total_sum; data comes directly from v1.2 columns (no legacy rebuild). (pytest: tests/test_export_service.py::test_export_orders_bundle)
- [x] Commissions CSV retains BOM, semicolon separator, ISO UTC timestamps; XLSX has 3 sheets (orders, commissions, ref_rewards). (pytest: tests/test_export_service.py::test_export_commissions)

## RBAC & Visibility
- [x] CITY_ADMIN / LOGIST see only their cities in queue, exports and finance screens. (pytest: tests/test_staff_access.py::test_queue_visibility_by_city)
- [x] GLOBAL_ADMIN sees all cities and can manage staff, settings, and reports. (pytest: tests/test_staff_access.py::test_visible_city_ids_helper)

## Ops & Alerts
- [x] Both bots send heartbeat to LOGS every 60 s. (pytest: tests/test_heartbeat.py::test_run_heartbeat_sends_messages)
- [x] ALERTS channel receives escalation notifications, overdue finance alerts, and guarantee refusals. (pytest: tests/test_admin_services.py::test_distribution_assign_auto_no_district, tests/test_watchdogs_overdue.py::test_watchdog_triggers_alert, tests/test_distribution_scheduler.py::test_guarantee_decline_blocks_master_and_advances_round)
- [x] Single-instance guard: when a second bot instance starts and gets HTTP 409, it logs and quits. (pytest: tests/test_single_instance.py::test_poll_with_single_instance_guard_logs_and_exits)
