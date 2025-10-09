from aiogram import Router

from .create import router as create_router
from .quick_create import router as quick_create_router  # P0-5: Быстрое создание
from .queue import queue_router

router = Router(name="admin_orders")
router.include_router(create_router)
router.include_router(quick_create_router)  # P0-5: Быстрое создание
router.include_router(queue_router)

__all__ = ["router"]
