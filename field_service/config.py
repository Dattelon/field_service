from __future__ import annotations
import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


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

    distribution_sla_seconds: int = int(os.getenv("DISTRIBUTION_SLA_SECONDS", "120"))
    distribution_rounds: int = int(os.getenv("DISTRIBUTION_ROUNDS", "2"))
    commission_deadline_hours: int = int(os.getenv("COMMISSION_DEADLINE_HOURS", "3"))
    guarantee_company_payment: float = float(
        os.getenv("GUARANTEE_COMPANY_PAYMENT", "2500")
    )
    working_hours_start: str = os.getenv("WORKING_HOURS_START", "10:00")
    working_hours_end: str = os.getenv("WORKING_HOURS_END", "20:00")
    admin_bot_superusers: tuple[int, ...] = tuple(
        int(item.strip())
        for item in os.getenv('ADMIN_BOT_SUPERUSERS', '').replace(';', ',').split(',')
        if item.strip().isdigit()
    )


settings = Settings()
