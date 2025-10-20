# field_service/bots/admin_bot/main.py
from __future__ import annotations

import asyncio
import logging
import os
from contextlib import suppress

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import Update

from field_service.config import settings
from field_service.bots.common.error_middleware import setup_error_middleware
from field_service.bots.common.polling import poll_with_single_instance_guard
from field_service.bots.common.retry_handler import retry_router
from field_service.bots.common.retry_middleware import setup_retry_middleware
from field_service.infra.notify import send_alert, send_log
from field_service.infra.enhanced_logging import setup_enhanced_logging  # ENHANCED LOGGING
from field_service.services.distribution_scheduler import run_scheduler
from field_service.services.heartbeat import run_heartbeat
from field_service.services.watchdogs import (
    watchdog_commissions_overdue,
    watchdog_commission_deadline_reminders,  # P1-21
    watchdog_expired_offers,  # Watchdog для истёкших офферов
    watchdog_expired_breaks,  # BUGFIX 2025-10-10: Авто-завершение перерывов
)
from field_service.services.autoclose_scheduler import autoclose_scheduler  # P1-01
from field_service.services.unassigned_monitor import monitor_unassigned_orders

from .handlers import create_combined_router
from .handlers.finance.main import router as finance_router  # CR-2025-10-03-007: Финансы
from .handlers.masters.main import router as admin_masters_router
from .handlers.masters.moderation import router as admin_moderation_router
from .core.middlewares import StaffAccessMiddleware
from .infrastructure.registry import register_services
from .services import (
    DBDistributionService,
    DBFinanceService,
    DBMastersService,
    DBOrdersService,
    DBSettingsService,
    DBStaffService,
)


logger = logging.getLogger(__name__)


async def log_all_callbacks_middleware(handler, event, data):
    """Глобальное логирование всех callback перед обработкой."""
    if isinstance(event, Update) and event.callback_query:
        cq = event.callback_query
        logger.info(f"[GLOBAL] Callback received: {cq.data} from user {cq.from_user.id}")
    return await handler(event, data)


async def main() -> int:
    # Setup enhanced logging FIRST
    log_level = os.getenv("LOG_LEVEL", "DEBUG").upper()  # Default to DEBUG for troubleshooting
    setup_enhanced_logging(log_level)
    
    logger.info("=" * 80)
    logger.info("ADMIN BOT STARTING - ENHANCED LOGGING ENABLED")
    logger.info(f"Log level: {log_level}")
    logger.info("=" * 80)
    
    bot = Bot(
        settings.admin_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    
    # Глобальное логирование всех callback (для отладки)
    dp.update.outer_middleware(log_all_callbacks_middleware)
    
    # CRITICAL: Сначала создаём сервисы и регистрируем middleware
    logger.info("[INIT] Creating services...")
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
    logger.info("[INIT] Services registered")

    staff_service: DBStaffService = services["staff_service"]
    seeded = await staff_service.seed_global_admins(settings.global_admins_tg_ids)
    if seeded:
        logger.info("Seeded %d GLOBAL_ADMIN from GLOBAL_ADMINS_TG_IDS", seeded)

    # CRITICAL: Middleware ДОЛЖЕН быть зарегистрирован ДО include_router()
    superuser_ids = set(settings.admin_bot_superusers) | set(settings.global_admins_tg_ids)
    logger.info(f"[INIT] Registering middleware with {len(superuser_ids)} superusers")
    dp.update.middleware(StaffAccessMiddleware(staff_service, superuser_ids))
    
    # P2-08: Используем только модульные роутеры из handlers/
    logger.info("[INIT] Including routers...")
    dp.include_router(create_combined_router())
    
    # CR-2025-10-03-007: Финансы
    dp.include_router(finance_router)
    
    # Модерация и управление мастерами (moderation ПЕРЕД masters, т.к. masters имеет catch-all)
    dp.include_router(admin_moderation_router)
    dp.include_router(admin_masters_router)
    
    # P1-13: Retry функциональность для повтора действий при ошибках
    dp.include_router(retry_router)

    channel_settings = await services["settings_service"].get_channel_settings()
    alerts_chat_id = channel_settings.get("alerts_channel_id") or settings.alerts_channel_id
    logs_chat_id = channel_settings.get("logs_channel_id") or settings.logs_channel_id

    setup_error_middleware(
        dp,
        bot=bot,
        bot_label="admin_bot",
        logs_chat_id=logs_chat_id,
        alerts_chat_id=alerts_chat_id,
    )
    
    # P1-13: Подключаем retry middleware для автоматического предложения повтора при ошибках
    setup_retry_middleware(dp, enabled=True)

    heartbeat_task = asyncio.create_task(
        run_heartbeat(bot, name="admin", chat_id=logs_chat_id),
        name="admin_heartbeat",
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

    unassigned_task: asyncio.Task | None = None
    if alerts_chat_id:
        unassigned_task = asyncio.create_task(
            monitor_unassigned_orders(
                bot,
                alerts_chat_id,
                interval_seconds=600,
            ),
            name="unassigned_monitor",
        )

    # P1-01: Автозакрытие заказов через 24ч
    autoclose_task = asyncio.create_task(
        autoclose_scheduler(
            interval_seconds=3600,  # Проверка каждый час
        ),
        name="autoclose_scheduler",
    )

    # P1-21: Напоминания о дедлайне комиссии (24ч, 6ч, 1ч)
    # Передаём master_bot_token чтобы уведомления шли мастерам в их бот!
    deadline_reminders_task = asyncio.create_task(
        watchdog_commission_deadline_reminders(
            master_bot_token=settings.master_bot_token,  # ← master_bot для мастеров!
            interval_seconds=1800,  # Проверка каждые 30 минут
        ),
        name="commission_deadline_reminders",
    )

    # Watchdog для истёкших офферов
    expired_offers_task = asyncio.create_task(
        watchdog_expired_offers(
            interval_seconds=60,  # Проверка каждую минуту
        ),
        name="expired_offers_watchdog",
    )

    # BUGFIX 2025-10-10: Watchdog для автоматического завершения просроченных перерывов
    expired_breaks_task = asyncio.create_task(
        watchdog_expired_breaks(
            interval_seconds=60,  # Проверка каждую минуту
        ),
        name="expired_breaks_watchdog",
    )

    exit_code = 0
    try:
        await poll_with_single_instance_guard(
            dp,
            bot,
            logs_chat_id=logs_chat_id,
        )
    except SystemExit as conflict_exit:
        exit_code = int(conflict_exit.code or 0)
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    except Exception as exc:
        logger.exception("Admin bot polling failed: %s", exc)
        message = f"❗ Ошибка admin_bot polling: {type(exc).__name__}: {exc}"
        await send_alert(bot, message, chat_id=alerts_chat_id, exc=exc)
        await send_log(bot, message, chat_id=logs_chat_id)
        exit_code = 1
    finally:
        for task in (
            heartbeat_task,
            scheduler_task,
            watchdog_task,
            autoclose_task,
            deadline_reminders_task,  # P1-21
            expired_offers_task,  # Watchdog истёкших офферов
            expired_breaks_task,  # BUGFIX 2025-10-10: Watchdog просроченных перерывов
            unassigned_task,
        ):
            if task:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
        await bot.session.close()

    return exit_code


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
