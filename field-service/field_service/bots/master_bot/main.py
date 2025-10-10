from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
import os

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from field_service.config import settings
from field_service.bots.common.error_middleware import setup_error_middleware
from field_service.bots.common.polling import poll_with_single_instance_guard
from field_service.bots.common.retry_handler import retry_router  # P1-13
from field_service.bots.common.retry_middleware import setup_retry_middleware  # P1-13
from field_service.infra.notify import send_alert, send_log
from field_service.services.heartbeat import run_heartbeat
from field_service.services.break_reminder_scheduler import run_break_reminder  # P1-16
from field_service.services.notifications_watcher import run_master_notifications  # Отправка уведомлений мастерам
from field_service.services.watchdogs import watchdog_expired_breaks  # Автоснятие со смены после перерыва

from .handlers import router as master_router


logger = logging.getLogger(__name__)


async def main() -> int:
    # Basic logging to console; allow override via LOG_LEVEL env
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=getattr(logging, log_level, logging.INFO),
            format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        )
    # Reduce aiohttp noise but keep aiogram useful
    logging.getLogger("aiogram").setLevel(getattr(logging, log_level, logging.INFO))
    logging.getLogger("aiohttp").setLevel(logging.WARNING)
    bot = Bot(
        settings.master_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp.include_router(master_router)
    
    # P1-13: Retry функциональность для повтора действий при ошибках
    dp.include_router(retry_router)

    alerts_chat_id = settings.alerts_channel_id
    logs_chat_id = settings.logs_channel_id

    setup_error_middleware(
        dp,
        bot=bot,
        bot_label="master_bot",
        logs_chat_id=logs_chat_id,
        alerts_chat_id=alerts_chat_id,
    )
    
    # P1-13: Подключаем retry middleware для автоматического предложения повтора при ошибках
    setup_retry_middleware(dp, enabled=True)

    heartbeat_task = asyncio.create_task(
        run_heartbeat(bot, name="master", chat_id=logs_chat_id),
        name="master_heartbeat",
    )

    # P1-16: Запуск планировщика напоминаний о перерывах
    break_reminder_task = asyncio.create_task(
        run_break_reminder(interval_seconds=60),
        name="break_reminder",
    )
    
    # Автоматическое снятие со смены после истечения перерыва
    expired_breaks_task = asyncio.create_task(
        watchdog_expired_breaks(interval_seconds=60),
        name="expired_breaks",
    )

    # Запуск worker для отправки уведомлений мастерам
    notifications_task = asyncio.create_task(
        run_master_notifications(bot, interval_seconds=5),
        name="master_notifications",
    )

    exit_code = 0
    try:
        logger.info("Starting master bot; allowed updates: %s", dp.resolve_used_update_types())
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
        logger.exception("Master bot polling failed: %s", exc)
        message = f"❗ Ошибка master_bot polling: {type(exc).__name__}: {exc}"
        await send_alert(bot, message, chat_id=alerts_chat_id, exc=exc)
        await send_log(bot, message, chat_id=logs_chat_id)
        exit_code = 1
    finally:
        if heartbeat_task:
            heartbeat_task.cancel()
            with suppress(asyncio.CancelledError):
                await heartbeat_task
        # P1-16: Отменяем задачу break_reminder
        if break_reminder_task:
            break_reminder_task.cancel()
            with suppress(asyncio.CancelledError):
                await break_reminder_task
        # Отменяем задачу expired_breaks
        if expired_breaks_task:
            expired_breaks_task.cancel()
            with suppress(asyncio.CancelledError):
                await expired_breaks_task
        # Отменяем задачу notifications
        if notifications_task:
            notifications_task.cancel()
            with suppress(asyncio.CancelledError):
                await notifications_task
        await bot.session.close()

    return exit_code


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
