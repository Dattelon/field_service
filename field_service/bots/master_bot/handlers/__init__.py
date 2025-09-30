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


# --- Auto-fix mojibake in outgoing texts (display-only) ---
import html as _py_html

def _ru_best_fix(text: str) -> str:
    if not isinstance(text, str) or not text:
        return text
    suspect_chars = "?N��?a?T?""\u0007-<>"
    if not any(ch in text for ch in suspect_chars) and "\u0014" not in text:
        return text
    def score(s: str) -> tuple[int, int]:
        vowels = set("аеёиоуыэюяАЕЁИОУЫЭЮЯ")
        return (sum(1 for ch in s if ch in vowels), sum(1 for ch in s if ch in suspect_chars))
    base = text
    best = base
    best_tuple = (0, 0)
    for enc, dec in (("cp1251","utf-8"),("utf-8","cp1251"),("latin1","utf-8"),("utf-8","latin1")):
        try:
            cand = text.encode(enc, errors='ignore').decode(dec, errors='ignore')
        except Exception:
            continue
        sc = score(cand)
        tup = (sc[0], -sc[1])
        if tup > best_tuple:
            best, best_tuple = cand, tup
    return best

try:
    from aiogram.types import Message as _AioMessage, CallbackQuery as _AioCallbackQuery
    from aiogram import Bot as _AioBot
    _orig_msg_answer = _AioMessage.answer
    _orig_msg_edit_text = _AioMessage.edit_text
    _orig_cq_answer = _AioCallbackQuery.answer
    _orig_bot_send_message = _AioBot.send_message
    async def _fx_msg_answer(self, text: str, *args, **kwargs):
        return await _orig_msg_answer(self, _ru_best_fix(text), *args, **kwargs)
    async def _fx_msg_edit_text(self, text: str, *args, **kwargs):
        return await _orig_msg_edit_text(self, _ru_best_fix(text), *args, **kwargs)
    async def _fx_cq_answer(self, text: str | None = None, *args, **kwargs):
        if isinstance(text, str):
            text = _ru_best_fix(text)
        return await _orig_cq_answer(self, text, *args, **kwargs)
    async def _fx_bot_send_message(self, chat_id, text: str, *args, **kwargs):
        return await _orig_bot_send_message(self, chat_id, _ru_best_fix(text), *args, **kwargs)
    _AioMessage.answer = _fx_msg_answer  # type: ignore
    _AioMessage.edit_text = _fx_msg_edit_text  # type: ignore
    _AioCallbackQuery.answer = _fx_cq_answer  # type: ignore
    _AioBot.send_message = _fx_bot_send_message  # type: ignore
except Exception:
    pass

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



