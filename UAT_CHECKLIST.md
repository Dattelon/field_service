# UAT Checklist — Release v1.2 Freeze

## Slots & Timeouts
- [ ] Create ASAP order today at 19:25 (city TZ) → distribution starts immediately, timeslot 19:25–20:00 local, logs contain decision=offer.
- [ ] Create ASAP order at 19:31 → late ASAP rule shifts slot to next day 10:00–13:00, auto start after shift, no duplicate alerts.
- [ ] Create order after 20:00 → initial status DEFERRED; at 10:00 local time wake-up moves it to SEARCHING and clears the notice cache.

## Distribution
- [ ] Tick loop runs every 30 s (LOGS channel shows [dist] order=… tick ok).
- [ ] Each round logs order id, city/district, category/type, round number, SLA, ranked candidates (has_car, avg_week_check, rating, rnd), and offer_to / expires_at.
- [ ] Orders flagged no_district never start auto distribution; logs emit skip_auto: no_district.

## Guarantee Flow
- [ ] Closing NORMAL order with guarantee trigger creates new order type=GUARANTEE, no_district copied, preferred_master_id = original master, company_payment = 2500, total_sum = 0.
- [ ] First guarantee offer goes to the previous master; refusal or timeout autoblocks the master, writes guarantee_refusal to block reason and logs escalate.
- [ ] Subsequent rounds target other masters; guarantee order finishes without generating commissions, status goes straight to CLOSED after act upload.

## Master Bot
- [ ] “New” list shows orders with formatted local timeslot (format_timeslot_local), buttons Взять/Отказаться work without stale buttons.
- [ ] “Active” flow: EN_ROUTE → WORKING → close. Normal order asks for total_sum (>0 regex), requires act upload, creates commission and sets PAYMENT status before CLOSED.
- [ ] Guarantee order close skips amount input, act is mandatory, status goes to CLOSED, no commission items appear.
- [ ] Finance section shows referral aggregates (L1/L2) after admin approval.

## Admin Bot
- [ ] Queue filters respect staff city scope; pagination and navigation buttons stay active.
- [ ] Manual assignment warns when master off shift / at limit; confirmation dialog sends offer and re-renders card.
- [ ] “Return to search” resets master, cancels pending offers, appends history entry.
- [ ] Cancellation FSM asks for reason (>= 5 chars), stores it in history and removes action buttons once order is canceled or closed.
- [ ] Guarantee button on closed order creates new guarantee request and removes action button from original card.

## Finance
- [ ] Commission closes after act upload: rate = 40% if avg_week_check ≥ 7000 else 50%, total_sum × rate rounded to 2 decimals, deadline = closed_at + 3h.
- [ ] Watchdog marks overdue commissions, blocks the master, and sends ALERT with adm:f:cm:<id> button.
- [ ] Admin finance card shows requisites snapshot, allows entering paid amount (/skip to keep default), approves/declines, blocks master when needed, without dead buttons.
- [ ] Referral rewards (10% L1 / 5% L2) are created on admin approval, visible in master UI and finance exports.

## Exports
- [ ] Orders CSV/XLSX include columns lat, lon, timeslot_start_utc, timeslot_end_utc, total_sum; data comes directly from v1.2 columns (no legacy rebuild).
- [ ] Commissions CSV retains BOM, semicolon separator, ISO UTC timestamps; XLSX has 3 sheets (orders, commissions, ref_rewards).

## RBAC & Visibility
- [ ] CITY_ADMIN / LOGIST see only their cities in queue, exports and finance screens.
- [ ] GLOBAL_ADMIN sees all cities and can manage staff, settings, and reports.

## Ops & Alerts
- [ ] Both bots send heartbeat to LOGS every 60 s.
- [ ] ALERTS channel receives escalation notifications, overdue finance alerts, and guarantee refusals.
- [ ] Single-instance guard: when a second bot instance starts and gets HTTP 409, it logs and quits.
