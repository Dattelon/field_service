from __future__ import annotations

from datetime import timedelta

from aiogram import Router
from aiogram.fsm.context import FSMContext

from field_service.bots.common import FSMTimeoutConfig, FSMTimeoutMiddleware, safe_send_message

from ..texts import FSM_TIMEOUT_MESSAGE
from ..middlewares import (
    DbSessionMiddleware,
    MasterContextMiddleware,
    DebugLoggingMiddleware,
)
from .finance import router as finance_router
from .history import router as history_router  # P1-9
from .onboarding import router as onboarding_router
from .orders import router as orders_router
from .referral import router as referral_router
from .shift import router as shift_router
from .start import router as start_router
from .statistics import router as statistics_router  # P1-17

router = Router(name="master_bot")


async def _notify_timeout(state: FSMContext) -> None:
    chat_id = state.key.chat_id
    if chat_id is None:
        return
    try:
        await safe_send_message(state.bot, chat_id, FSM_TIMEOUT_MESSAGE)
    except Exception:
        pass


_fsm_timeout = FSMTimeoutMiddleware(
    FSMTimeoutConfig(timeout=timedelta(minutes=7), callback=_notify_timeout)
)

router.message.middleware(DebugLoggingMiddleware())
router.callback_query.middleware(DebugLoggingMiddleware())
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
router.include_router(history_router)  # P1-9
router.include_router(referral_router)
router.include_router(finance_router)
router.include_router(statistics_router)  # P1-17
