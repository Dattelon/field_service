# CHANGE REQUESTS

## CR-2025-09-28 — Working Window Validation (10:00–20:00)

- Background: Frozen TZ v1.2 specified a strict DB-level CHECK constraint enforcing a 10:00–20:00 working window. In practice, working hours must respect each city's local time zone, which cannot be reliably expressed with a static UTC CHECK.
- Decision: Apply the 10:00–20:00 rule at the service layer using city time zones; retain DB-level integrity as `timeslot_start_utc < timeslot_end_utc`.
- Rationale: Prevent false rejections due to UTC offsets while maintaining data consistency. The time service (`field_service.services.time_service`) already computes/validates ASAP/DEFERRED slots and wake-up at 10:00 local time.
- Scope: Documentation only; schema stays with `ck_orders__timeslot_range`. README has been updated to reflect this.

