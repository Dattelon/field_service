from aiogram import Router

from .create import router as create_router
from .quick_create import router as quick_create_router  # P0-5: Быстрое создание
from .queue import queue_router
from .copy_data import copy_router  # P1-19: Быстрое копирование данных

router = Router(name="admin_orders")
router.include_router(create_router)
router.include_router(quick_create_router)  # P0-5: Быстрое создание
router.include_router(queue_router)
router.include_router(copy_router)  # P1-19: Быстрое копирование данных

__all__ = ["router"]
