from __future__ import annotations

from typing import Any, Iterable, Optional

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from field_service.bots.admin_bot.dto import StaffRole, StaffUser
from field_service.bots.admin_bot.services_db import DBStaffService

ACCESS_PROMPT = "  ."
INACTIVE_PROMPT = " ,   ."


def _extract_user_id(event: TelegramObject) -> Optional[int]:
    if isinstance(event, Message):
        return event.from_user.id if event.from_user else None
    if isinstance(event, CallbackQuery):
        return event.from_user.id if event.from_user else None
    user = getattr(event, "from_user", None)
    return user.id if user else None


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

        staff: Optional[StaffUser] = data.get("staff")
        if tg_id in self._superusers:
            if not isinstance(staff, StaffUser):
                staff = StaffUser(
                    id=0,
                    tg_id=tg_id,
                    role=StaffRole.GLOBAL_ADMIN,
                    is_active=True,
                    city_ids=frozenset(),
                    full_name="Superuser",
                    phone="",
                )
            data["staff"] = staff
            return await handler(event, data)

        if not isinstance(staff, StaffUser):
            staff = await self._staff_service.get_by_tg_id(tg_id)
            if not staff:
                if _is_callback(event):
                    await _notify_access_required(event, ACCESS_PROMPT)
                    return None
                data["staff"] = None
                return await handler(event, data)
            data["staff"] = staff

        if not staff.is_active:
            await _notify_access_required(event, INACTIVE_PROMPT)
            return None

        return await handler(event, data)
