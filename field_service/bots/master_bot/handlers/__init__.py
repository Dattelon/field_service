from __future__ import annotations

from aiogram import Router

from ..middlewares import DbSessionMiddleware, MasterContextMiddleware
from .finance import router as finance_router
from .onboarding import router as onboarding_router
from .orders import router as orders_router
from .referral import router as referral_router
from .shift import router as shift_router
from .start import router as start_router

router = Router(name='master_bot')
router.message.middleware(DbSessionMiddleware())
router.callback_query.middleware(DbSessionMiddleware())
router.message.middleware(MasterContextMiddleware())
router.callback_query.middleware(MasterContextMiddleware())

router.include_router(start_router)
router.include_router(onboarding_router)
router.include_router(shift_router)
router.include_router(orders_router)
router.include_router(referral_router)

router.include_router(finance_router)

