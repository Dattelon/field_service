from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Literal, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from field_service.config import settings

_TIME_RE = re.compile(r"^(?P<hour>\d{1,2}):(?P<minute>\d{2})$")
# P1-03: Слоты загружаются из конфига или дефолтные
def _load_slot_buckets() -> dict[str, tuple[time, time]]:
    """Загрузить временные слоты из конфига или использовать дефолтные."""
    # Дефолтные слоты
    default = {
        "10-13": (time(10, 0), time(13, 0)),
        "13-16": (time(13, 0), time(16, 0)),
        "16-19": (time(16, 0), time(19, 0)),
    }
    
    # Если в конфиге есть кастомные слоты - используем их
    custom_slots = getattr(settings, 'timeslot_buckets', None)
    if custom_slots:
        try:
            import json
            if isinstance(custom_slots, str):
                slots_data = json.loads(custom_slots)
            else:
                slots_data = custom_slots
            
            result = {}
            for item in slots_data:
                key = item.get("key")
                start_str = item.get("start")
                end_str = item.get("end")
                
                if key and start_str and end_str:
                    start_time = parse_time_string(start_str)
                    end_time = parse_time_string(end_str)
                    result[key] = (start_time, end_time)
            
            return result if result else default
        except Exception:
            pass
    
    return default

_SLOT_BUCKETS: dict[str, tuple[time, time]] = _load_slot_buckets()

SlotChoice = Literal[
    "ASAP",
    "TODAY:10-13",
    "TODAY:13-16",
    "TODAY:16-19",
    "TOM:10-13",
    "TOM:13-16",
    "TOM:16-19",
    "DEFERRED_TOM_10_13",
]

NormalizedAsap = Literal["ASAP", "DEFERRED_TOM_10_13"]


@dataclass(frozen=True, slots=True)
class SlotComputation:
    label: str
    slot_date: date
    start_local: time
    end_local: time
    start_utc: datetime
    end_utc: datetime
    timezone: ZoneInfo

    def as_tuple(self) -> tuple[datetime, datetime]:
        return self.start_utc, self.end_utc


@dataclass(frozen=True, slots=True)
class TimeslotWindow:
    start_utc: Optional[datetime]
    end_utc: Optional[datetime]



def _coerce_zone(zone: Optional[str | ZoneInfo]) -> ZoneInfo:
    if isinstance(zone, ZoneInfo):
        return zone
    candidate = (zone or settings.timezone or "UTC").strip()
    try:
        return ZoneInfo(candidate)
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def resolve_timezone(zone: Optional[str | ZoneInfo] = None) -> ZoneInfo:
    """Return ZoneInfo for a city, falling back to global settings."""
    return _coerce_zone(zone)



def parse_time_string(value: str, *, default: Optional[time] = None) -> time:
    match = _TIME_RE.fullmatch((value or "").strip())
    if not match:
        if default is not None:
            return default
        raise ValueError(f"Invalid HH:MM value: {value!r}")
    hour = int(match.group("hour"))
    minute = int(match.group("minute"))
    if not (0 <= hour < 24 and 0 <= minute < 60):
        if default is not None:
            return default
        raise ValueError(f"Invalid time bounds for value: {value!r}")
    return time(hour=hour, minute=minute)


def normalize_asap_choice(
    *,
    now_local: datetime,
    workday_start: time,
    workday_end: time,
    late_threshold: time,
) -> NormalizedAsap:
    current = now_local.timetz()
    if current.tzinfo is not None:
        current = current.replace(tzinfo=None)
    if current >= workday_end or current >= late_threshold:
        return "DEFERRED_TOM_10_13"
    if current < workday_start:
        return "ASAP"
    return "ASAP"


def now_in_city(zone: Optional[str | ZoneInfo] = None) -> datetime:
    tz = _coerce_zone(zone)
    return datetime.now(timezone.utc).astimezone(tz)


def combine_local(zone: Optional[str | ZoneInfo], day: date, tm: time) -> datetime:
    tz = _coerce_zone(zone)
    return datetime.combine(day, tm, tzinfo=tz)


def local_range_to_utc(
    *,
    zone: Optional[str | ZoneInfo],
    day: date,
    start_time: time,
    end_time: time,
) -> tuple[datetime, datetime]:
    start_local = combine_local(zone, day, start_time)
    end_local = combine_local(zone, day, end_time)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def compute_slot(
    *,
    city_tz: Optional[str | ZoneInfo],
    choice: SlotChoice,
    workday_start: time,
    workday_end: time,
    now_utc: Optional[datetime] = None,
) -> SlotComputation:
    tz = _coerce_zone(city_tz)
    base_now = (now_utc or datetime.now(timezone.utc)).astimezone(tz)
    label = choice
    normalized_choice = choice.upper()
    if normalized_choice == "DEFERRED_TOM_10_13":
        normalized_choice = "TOM:10-13"
    if normalized_choice == "ASAP":
        current_time = base_now.timetz()
        if current_time.tzinfo is not None:
            current_time = current_time.replace(tzinfo=None)
        start_local = max(current_time, workday_start)
        if start_local >= workday_end:
            raise ValueError("ASAP slot cannot start after workday end")
        end_local = workday_end
        slot_date = base_now.date()
    else:
        if ":" not in normalized_choice:
            raise ValueError(f"Unsupported slot choice: {choice}")
        period, bucket = normalized_choice.split(":", 1)
        if bucket not in _SLOT_BUCKETS:
            raise ValueError(f"Unknown slot bucket: {bucket}")
        start_local, end_local = _SLOT_BUCKETS[bucket]
        if period == "TODAY":
            slot_date = base_now.date()
        elif period in {"TOM", "TOMORROW"}:
            slot_date = base_now.date() + timedelta(days=1)
        else:
            raise ValueError(f"Unsupported slot period: {period}")
        if period == "TODAY":
            current_time = base_now.timetz()
            if current_time.tzinfo is not None:
                current_time = current_time.replace(tzinfo=None)
            if current_time >= end_local:
                raise ValueError("Selected slot already passed for today")
    if start_local >= end_local:
        raise ValueError("Invalid slot interval")
    start_local_dt = datetime.combine(slot_date, start_local, tzinfo=tz)
    end_local_dt = datetime.combine(slot_date, end_local, tzinfo=tz)
    return SlotComputation(
        label=label,
        slot_date=slot_date,
        start_local=start_local,
        end_local=end_local,
        start_utc=start_local_dt.astimezone(timezone.utc),
        end_utc=end_local_dt.astimezone(timezone.utc),
        timezone=tz,
    )


def _day_prefix(target: date, today: date) -> Optional[str]:
    delta = (target - today).days
    if delta == 0:
        return "сегодня"
    if delta == 1:
        return "завтра"
    if delta == -1:
        return "вчера"
    return None


def format_timeslot_local(
    start_utc: Optional[datetime],
    end_utc: Optional[datetime],
    *,
    tz: Optional[str | ZoneInfo],
    fallback: Optional[str] = None,
    now_utc: Optional[datetime] = None,
) -> Optional[str]:
    if not start_utc and not end_utc:
        return fallback
    tzinfo = _coerce_zone(tz)
    reference = (now_utc or datetime.now(timezone.utc)).astimezone(tzinfo)
    start_local = start_utc.astimezone(tzinfo) if start_utc else None
    end_local = end_utc.astimezone(tzinfo) if end_utc else None

    def format_single(moment: datetime) -> str:
        prefix = _day_prefix(moment.date(), reference.date())
        if prefix:
            return f"{prefix} {moment:%H:%M}"
        return moment.strftime("%d.%m %H:%M")

    if start_local and end_local:
        if start_local.date() == end_local.date():
            prefix = _day_prefix(start_local.date(), reference.date())
            if prefix:
                return f"{prefix} {start_local:%H:%M}-{end_local:%H:%M}"
            return f"{start_local:%d.%m %H:%M}-{end_local:%H:%M}"
        start_text = format_single(start_local)
        end_text = format_single(end_local)
        return f"{start_text} ? {end_text}"
    if start_local:
        return format_single(start_local)
    if end_local:
        return format_single(end_local)
    return fallback



__all__ = [
    "SlotChoice",
    "NormalizedAsap",
    "SlotComputation",
    "TimeslotWindow",
    "compute_slot",
    "combine_local",
    "local_range_to_utc",
    "normalize_asap_choice",
    "format_timeslot_local",
    "now_in_city",
    "parse_time_string",
    "resolve_timezone",
]
