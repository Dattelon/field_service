from __future__ import annotations

import logging
from typing import Any, Iterable, Optional

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from .dto import StaffRole, StaffUser
from field_service.bots.admin_bot.services import DBStaffService

logger = logging.getLogger(__name__)

ACCESS_PROMPT = "  ."
INACTIVE_PROMPT = " ,   ."


def _extract_user_id(event: TelegramObject) -> Optional[int]:
    if isinstance(event, Message):
        return event.from_user.id if event.from_user else None
    if isinstance(event, CallbackQuery):
        return event.from_user.id if event.from_user else None
    user = getattr(event, "from_user", None)
    return user.id if user else None


def _extract_username(event: TelegramObject) -> Optional[str]:
    """Извлечь username пользователя из события."""
    if isinstance(event, Message):
        return getattr(event.from_user, "username", None) if event.from_user else None
    if isinstance(event, CallbackQuery):
        return getattr(event.from_user, "username", None) if event.from_user else None
    user = getattr(event, "from_user", None)
    return getattr(user, "username", None) if user else None


def _extract_full_name(event: TelegramObject) -> Optional[str]:
    """Извлечь полное имя пользователя из события."""
    if isinstance(event, Message) and event.from_user:
        return event.from_user.full_name
    if isinstance(event, CallbackQuery) and event.from_user:
        return event.from_user.full_name
    user = getattr(event, "from_user", None)
    if user and hasattr(user, "full_name"):
        return user.full_name
    return None


def _is_callback(event: TelegramObject) -> bool:
    return isinstance(event, CallbackQuery) or (
        hasattr(event, "message") and hasattr(event, "answer") and not isinstance(event, Message)
    )


async def _notify_access_required(event: TelegramObject, text: str) -> None:
    if isinstance(event, CallbackQuery):
        try:
            await event.answer(text, show_alert=True)
        except Exception:
            pass
        if event.message:
            await event.message.answer(text)
        return
    if isinstance(event, Message):
        await event.answer(text)
        return
    answer = getattr(event, "answer", None)
    if callable(answer):
        await answer(text)


class StaffAccessMiddleware(BaseMiddleware):
    def __init__(self, staff_service: DBStaffService, superusers: Iterable[int] = ()) -> None:
        self._staff_service = staff_service
        self._superusers = {int(tg) for tg in superusers if tg is not None}

    async def __call__(self, handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        tg_id = _extract_user_id(event)
        if tg_id is None:
            return await handler(event, data)

        logger.info(f"[STAFF MIDDLEWARE] Processing event from user {tg_id}")

        # CR-2025-10-04: Универсальный поиск по tg_id ИЛИ username
        username = _extract_username(event)
        staff = await self._staff_service.get_by_tg_id_or_username(
            tg_id=tg_id,
            username=username,
            update_tg_id=True  # Автоматически обновлять tg_id если нашли по username
        )
        
        if not staff:
            logger.warning(f"[STAFF MIDDLEWARE] Staff not found for user {tg_id} (username: {username})")
            # Для суперюзеров не в БД - отказ
            if tg_id in self._superusers:
                await _notify_access_required(event, "⛔ Суперпользователь не зарегистрирован в системе. Обратитесь к администратору.")
                return None
            # Для обычных пользователей - пусть обработчик решает
            if _is_callback(event):
                await _notify_access_required(event, ACCESS_PROMPT)
                return None
            data["staff"] = None
            return await handler(event, data)

        if not staff.is_active:
            logger.warning(f"[STAFF MIDDLEWARE] Staff {tg_id} is inactive")
            await _notify_access_required(event, INACTIVE_PROMPT)
            return None

        logger.info(f"[STAFF MIDDLEWARE] Staff found: {staff.full_name} (role: {staff.role})")
        # Всегда устанавливаем свежезагруженные данные staff
        data["staff"] = staff
        return await handler(event, data)
