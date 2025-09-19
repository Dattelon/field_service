from __future__ import annotations
import asyncio
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
import logging
from field_service.config import settings
from .handlers import router as master_router

async def main():
    logging.basicConfig(level=logging.INFO)
    bot = Bot(settings.master_bot_token, default=DefaultBotProperties(parse_mode="HTML"))
    dp = Dispatcher()
    dp.include_router(master_router)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
