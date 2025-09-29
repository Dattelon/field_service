from __future__ import annotations

from datetime import timedelta

from aiogram import Router
from aiogram.fsm.context import FSMContext

from field_service.bots.common import FSMTimeoutConfig, FSMTimeoutMiddleware

from ..middlewares import DbSessionMiddleware, MasterContextMiddleware
from .finance import router as finance_router
from .onboarding import router as onboarding_router
from .orders import router as orders_router
from .referral import router as referral_router
from .shift import router as shift_router
from .start import router as start_router

router = Router(name="master_bot")


async def _notify_timeout(state: FSMContext) -> None:
    chat_id = state.key.chat_id
    if chat_id is None:
        return
    try:
        await state.bot.send_message(
            chat_id,
            "Session timed out. Send /start to continue.",
        )
    except Exception:
        # Notification is optional; ignore delivery failures (e.g., bot was blocked).
        pass


_fsm_timeout = FSMTimeoutMiddleware(
    FSMTimeoutConfig(timeout=timedelta(minutes=7), callback=_notify_timeout)
)

router.message.middleware(DbSessionMiddleware())
router.callback_query.middleware(DbSessionMiddleware())
router.message.middleware(MasterContextMiddleware())
router.callback_query.middleware(MasterContextMiddleware())
router.message.middleware(_fsm_timeout)
router.callback_query.middleware(_fsm_timeout)

router.include_router(start_router)
router.include_router(onboarding_router)
router.include_router(shift_router)
router.include_router(orders_router)
router.include_router(referral_router)

router.include_router(finance_router)
