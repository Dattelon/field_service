from __future__ import annotations

import asyncio
import logging
from contextlib import suppress

from aiogram import Bot, Dispatcher, exceptions
from aiogram.client.default import DefaultBotProperties
from aiogram.types import ErrorEvent

from field_service.config import settings
from field_service.infra.logging_utils import send_alert, send_log, start_heartbeat

from .handlers import router as master_router


logger = logging.getLogger(__name__)


async def main() -> int:
    bot = Bot(
        settings.master_bot_token,
        default=DefaultBotProperties(parse_mode="HTML"),
    )
    dp = Dispatcher()
    dp.include_router(master_router)

    alerts_chat_id = settings.alerts_channel_id
    logs_chat_id = settings.logs_channel_id

    heartbeat_task = start_heartbeat(
        bot,
        bot_name="MASTER_BOT",
        interval_seconds=settings.heartbeat_seconds,
        chat_id=logs_chat_id,
    )

    async def on_error(event: ErrorEvent, exception: Exception) -> bool:
        logger.exception("Unhandled master bot error: %s", exception)
        message = f"❗ Ошибка master_bot: {type(exception).__name__}: {exception}"
        await send_log(bot, message, chat_id=logs_chat_id)
        await send_alert(bot, message, chat_id=alerts_chat_id)
        return True

    dp.errors.register(on_error)

    exit_code = 0
    try:
        await dp.start_polling(bot)
    except exceptions.TelegramConflictError:
        message = "[master_bot] Conflict 409: another instance detected — exiting"
        logger.warning(message)
        await send_log(bot, message, chat_id=logs_chat_id)
    except (KeyboardInterrupt, SystemExit, asyncio.CancelledError):
        pass
    except Exception as exc:
        logger.exception("Master bot polling failed: %s", exc)
        message = f"❗ Ошибка master_bot: {type(exc).__name__}: {exc}"
        await send_alert(bot, message, chat_id=alerts_chat_id)
        await send_log(bot, message, chat_id=logs_chat_id)
        exit_code = 1
    finally:
        if heartbeat_task:
            heartbeat_task.cancel()
            with suppress(asyncio.CancelledError):
                await heartbeat_task
        await bot.session.close()

    return exit_code


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
