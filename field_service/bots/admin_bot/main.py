# field_service/bots/admin_bot/main.py
from __future__ import annotations

import asyncio
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties

from field_service.services.distribution_scheduler import run_scheduler
from field_service.services.watchdogs import watchdog_commissions_overdue
from field_service.config import settings

from .service_registry import register_services
from .services_db import (
    DBDistributionService,
    DBFinanceService,
    DBMastersService,
    DBOrdersService,
    DBSettingsService,
    DBStaffService,
)
from .handlers import router as admin_router
from .handlers_staff import router as admin_staff_router


async def main() -> None:
    bot = Bot(
        settings.admin_bot_token,
        default=DefaultBotProperties(parse_mode="HTML"),
    )
    dp = Dispatcher()
    dp.include_router(admin_router)
    dp.include_router(admin_staff_router)

    services = {
        "staff_service": DBStaffService(),
        "orders_service": DBOrdersService(),
        "distribution_service": DBDistributionService(),
        "finance_service": DBFinanceService(),
        "settings_service": DBSettingsService(),
        "masters_service": DBMastersService(),
    }
    bot._services = services  # type: ignore[attr-defined]
    register_services(services)

    asyncio.create_task(run_scheduler())

    channel_settings = await services["settings_service"].get_channel_settings()
    alerts_chat_id = channel_settings.get("alerts_channel_id")

    try:
        asyncio.create_task(watchdog_commissions_overdue(bot, alerts_chat_id))
        await dp.start_polling(bot)
    except (KeyboardInterrupt, SystemExit, asyncio.CancelledError):
        pass
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
