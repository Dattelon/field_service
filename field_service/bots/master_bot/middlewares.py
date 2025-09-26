from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from field_service.db.session import SessionLocal
from field_service.services import onboarding_service


class DbSessionMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        async with SessionLocal() as session:
            data["session"] = session
            try:
                result = await handler(event, data)
            finally:
                if session.in_transaction():
                    await session.rollback()
            return result


class MasterContextMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        session = data.get("session")
        if session is None:
            return await handler(event, data)
        tg_user_id = _extract_tg_id(event)
        if tg_user_id is not None:
            master = await onboarding_service.ensure_master(session, tg_user_id)
            data["master"] = master
        return await handler(event, data)


def _extract_tg_id(event: TelegramObject) -> int | None:
    if isinstance(event, Message):
        return event.from_user.id if event.from_user else None
    if isinstance(event, CallbackQuery):
        return event.from_user.id if event.from_user else None
    user = getattr(event, "from_user", None)
    return user.id if user else None
