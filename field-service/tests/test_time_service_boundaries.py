from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

from field_service.services import time_service as ts


def test_normalize_asap_before_and_after_late_threshold() -> None:
    tz = ZoneInfo("Europe/Moscow")
    workday_start = time(10, 0)
    workday_end = time(20, 0)
    late_threshold = time(19, 30)

    # 19:29 -> ASAP
    now = datetime(2025, 9, 28, 16, 29, tzinfo=timezone.utc).astimezone(tz)
    choice = ts.normalize_asap_choice(
        now_local=now,
        workday_start=workday_start,
        workday_end=workday_end,
        late_threshold=late_threshold,
    )
    assert choice == "ASAP"

    # 19:31 -> DEFERRED_TOM_10_13
    now = datetime(2025, 9, 28, 16, 31, tzinfo=timezone.utc).astimezone(tz)
    choice = ts.normalize_asap_choice(
        now_local=now,
        workday_start=workday_start,
        workday_end=workday_end,
        late_threshold=late_threshold,
    )
    assert choice == "DEFERRED_TOM_10_13"


def test_compute_slot_deferred_tomorrow_10_13_uses_city_tz() -> None:
    tz = ZoneInfo("Europe/Moscow")
    workday_start = time(10, 0)
    workday_end = time(20, 0)
    # Force a fixed current time
    now_utc = datetime(2025, 9, 28, 12, 0, tzinfo=timezone.utc)

    slot = ts.compute_slot(
        city_tz=tz,
        choice="DEFERRED_TOM_10_13",
        workday_start=workday_start,
        workday_end=workday_end,
        now_utc=now_utc,
    )

    # Start is 10:00 next local day, end is 13:00
    assert slot.start_local == time(10, 0)
    assert slot.end_local == time(13, 0)
    # Check that start_utc equals the local time converted to UTC for the given zone
    expected_local = datetime.combine(slot.slot_date, time(10, 0), tzinfo=tz)
    assert slot.start_utc == expected_local.astimezone(timezone.utc)

