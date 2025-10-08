from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv


load_dotenv()


def _parse_int_or_none(value: str | None) -> int | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _parse_json_int_list(value: str) -> tuple[int, ...]:
    try:
        parsed = json.loads(value or "[]")
    except (TypeError, json.JSONDecodeError):
        return ()
    if not isinstance(parsed, (list, tuple)):
        return ()
    result: list[int] = []
    for item in parsed:
        try:
            number = int(item)
        except (TypeError, ValueError):
            continue
        result.append(number)
    unique: list[int] = []
    seen: set[int] = set()
    for number in result:
        if number in seen:
            continue
        seen.add(number)
        unique.append(number)
    return tuple(unique)


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://fs_user:fs_password@127.0.0.1:5439/field_service",
    )
    master_bot_token: str = os.getenv(
        "MASTER_BOT_TOKEN", "8423680284:AAHXBq-Lmtn5cVwUoxMwhJPOAoCMVGz4688"
    )
    admin_bot_token: str = os.getenv(
        "ADMIN_BOT_TOKEN", "7531617746:AAGvHQ0RySGtSSMAYenNdwyenZFkTZA6xbQ"
    )
    timezone: str = os.getenv("TIMEZONE", "Europe/Moscow")
    logs_channel_id: Optional[int] = _parse_int_or_none(os.getenv("LOGS_CHANNEL_ID"))
    alerts_channel_id: Optional[int] = _parse_int_or_none(os.getenv("ALERTS_CHANNEL_ID"))
    reports_channel_id: Optional[int] = _parse_int_or_none(os.getenv("REPORTS_CHANNEL_ID"))
    heartbeat_seconds: int = int(os.getenv("HEARTBEAT_SECONDS", "60"))

    distribution_sla_seconds: int = int(os.getenv("DISTRIBUTION_SLA_SECONDS", "120"))
    distribution_rounds: int = int(os.getenv("DISTRIBUTION_ROUNDS", "2"))
    commission_deadline_hours: int = int(os.getenv("COMMISSION_DEADLINE_HOURS", "3"))
    guarantee_company_payment: float = float(
        os.getenv("GUARANTEE_COMPANY_PAYMENT", "2500")
    )
    workday_start: str = os.getenv("WORKDAY_START") or os.getenv("WORKING_HOURS_START", "10:00")
    workday_end: str = os.getenv("WORKDAY_END") or os.getenv("WORKING_HOURS_END", "20:00")
    asap_late_threshold: str = os.getenv("ASAP_LATE_THRESHOLD", "19:30")
    admin_bot_superusers: tuple[int, ...] = tuple(
        int(item.strip())
        for item in os.getenv("ADMIN_BOT_SUPERUSERS", "").replace(";", ",").split(",")
        if item.strip().isdigit()
    )
    global_admins_tg_ids: tuple[int, ...] = _parse_json_int_list(
        os.getenv("GLOBAL_ADMINS_TG_IDS", "[]")
    )
    access_code_ttl_hours: int = int(os.getenv("ACCESS_CODE_TTL_HOURS", "24"))
    overdue_watchdog_min: int = int(os.getenv("OVERDUE_WATCHDOG_MIN", "10"))

    @property
    def working_hours_start(self) -> str:
        return self.workday_start

    @property
    def working_hours_end(self) -> str:
        return self.workday_end



settings = Settings()
