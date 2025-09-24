# field_service/bots/admin_bot/main.py
from __future__ import annotations

import asyncio
import logging
from contextlib import suppress

from aiogram import Bot, Dispatcher, exceptions
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import ErrorEvent

from field_service.config import settings
from field_service.infra.logging_utils import send_alert, send_log, start_heartbeat
from field_service.services.distribution_scheduler import run_scheduler
from field_service.services.watchdogs import watchdog_commissions_overdue

from .handlers import router as admin_router
from .handlers_staff import router as admin_staff_router
from .middlewares import StaffAccessMiddleware
from .service_registry import register_services
from .services_db import (
    DBDistributionService,
    DBFinanceService,
    DBMastersService,
    DBOrdersService,
    DBSettingsService,
    DBStaffService,
)


logger = logging.getLogger(__name__)


async def main() -> int:
    bot = Bot(
        settings.admin_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
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

    staff_service: DBStaffService = services["staff_service"]
    seeded = await staff_service.seed_global_admins(settings.global_admins_tg_ids)
    if seeded:
        logger.info("Seeded %d GLOBAL_ADMIN from GLOBAL_ADMINS_TG_IDS", seeded)

    superuser_ids = set(settings.admin_bot_superusers) | set(settings.global_admins_tg_ids)
    dp.update.middleware(StaffAccessMiddleware(staff_service, superuser_ids))

    channel_settings = await services["settings_service"].get_channel_settings()
    alerts_chat_id = channel_settings.get("alerts_channel_id") or settings.alerts_channel_id
    logs_chat_id = channel_settings.get("logs_channel_id") or settings.logs_channel_id

    heartbeat_task = start_heartbeat(
        bot,
        bot_name="ADMIN_BOT",
        interval_seconds=settings.heartbeat_seconds,
        chat_id=logs_chat_id,
    )

    scheduler_task = asyncio.create_task(
        run_scheduler(bot, alerts_chat_id=alerts_chat_id),
        name="admin_scheduler",
    )

    watchdog_interval = max(60, settings.overdue_watchdog_min * 60)
    watchdog_task = asyncio.create_task(
        watchdog_commissions_overdue(
            bot,
            alerts_chat_id,
            interval_seconds=watchdog_interval,
        ),
        name="commissions_watchdog",
    )

    async def on_error(event: ErrorEvent, exception: Exception) -> bool:
        logger.exception("Unhandled admin bot error: %s", exception)
        message = f"❗ Ошибка admin_bot: {type(exception).__name__}: {exception}"
        await send_log(bot, message, chat_id=logs_chat_id)
        await send_alert(bot, message, chat_id=alerts_chat_id)
        return True

    dp.errors.register(on_error)

    exit_code = 0
    try:
        await dp.start_polling(bot)
    except exceptions.TelegramConflictError:
        message = "[admin_bot] Conflict 409: another instance detected — exiting"
        logger.warning(message)
        await send_log(bot, message, chat_id=logs_chat_id)
        exit_code = 0
    except (KeyboardInterrupt, SystemExit, asyncio.CancelledError):
        pass
    except Exception as exc:
        logger.exception("Admin bot polling failed: %s", exc)
        message = f"❗ Ошибка admin_bot: {type(exc).__name__}: {exc}"
        await send_alert(bot, message, chat_id=alerts_chat_id)
        await send_log(bot, message, chat_id=logs_chat_id)
        exit_code = 1
    finally:
        for task in (heartbeat_task, scheduler_task, watchdog_task):
            if task:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
        await bot.session.close()

    return exit_code


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
