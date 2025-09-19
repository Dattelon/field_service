# field_service/bots/admin_bot/main.py
from __future__ import annotations

import asyncio
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from field_service.services.distribution_scheduler import run_scheduler
from field_service.services.watchdogs import watchdog_commissions_overdue

from field_service.config import settings
from .handlers import router as admin_router
from .handlers_staff import router as admin_staff_router  # UI доступа/кодов

async def main():
    bot = Bot(settings.admin_bot_token, default=DefaultBotProperties(parse_mode="HTML"))
    dp = Dispatcher()
    dp.include_router(admin_router)
    dp.include_router(admin_staff_router)


    asyncio.create_task(run_scheduler())

    
    try:
        # фоновые сервисы
        asyncio.create_task(run_scheduler())
        # алерты о просроченных комиссиях (чат можно вынести в settings)
        alerts_chat_id = None
        asyncio.create_task(watchdog_commissions_overdue(bot, alerts_chat_id))
        await dp.start_polling(bot)
    except (KeyboardInterrupt, SystemExit, asyncio.CancelledError):
        # тихое завершение без stacktrace в консоли
        pass
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
