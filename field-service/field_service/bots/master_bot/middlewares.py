from __future__ import annotations

import logging
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
            except Exception:
                # При ошибке - откатываем транзакцию
                if session.in_transaction():
                    await session.rollback()
                raise
            # При успехе - НЕ трогаем сессию, обработчик сам делает commit
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


class DebugLoggingMiddleware(BaseMiddleware):
    """Lightweight debug logger for incoming messages and callbacks.

    Prints concise info to the standard logger so operators can see
    what arrives and which handler chain processes it.
    """

    def __init__(self, *, logger: logging.Logger | None = None) -> None:
        self._log = logger or logging.getLogger("master_bot.debug")

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        try:
            if isinstance(event, Message):
                uid = getattr(getattr(event, "from_user", None), "id", None)
                cid = getattr(getattr(event, "chat", None), "id", None)
                text = getattr(event, "text", None) or getattr(event, "caption", None)
                self._log.info("Message uid=%s chat=%s type=%s text=%r", uid, cid, getattr(event, "content_type", None), text)
            elif isinstance(event, CallbackQuery):
                uid = getattr(getattr(event, "from_user", None), "id", None)
                cid = getattr(getattr(getattr(event, "message", None), "chat", None), "id", None)
                data_str = getattr(event, "data", None)
                self._log.info("Callback uid=%s chat=%s data=%r", uid, cid, data_str)
        except Exception:
            # Never allow logging failures to break the pipeline
            pass
        return await handler(event, data)
