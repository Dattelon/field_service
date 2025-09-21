from __future__ import annotations

from typing import Iterable, Optional

from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, Message, TelegramObject

from field_service.config import settings

from .dto import StaffRole, StaffUser
from .utils import get_service


def _extract_user_id(event: TelegramObject) -> Optional[int]:
    if isinstance(event, Message):
        if event.from_user:
            return event.from_user.id
        return None
    if isinstance(event, CallbackQuery):
        if event.from_user:
            return event.from_user.id
        return None
    return getattr(getattr(event, "from_user", None), "id", None)


class StaffRoleFilter(BaseFilter):
    """Attach StaffUser to handler if role matches."""

    def __init__(self, roles: Iterable[StaffRole] | None = None):
        self._roles = set(roles) if roles else None

    async def __call__(self, event: TelegramObject, bot, **kwargs):
        tg_id = _extract_user_id(event)
        if tg_id is None:
            return False

        if tg_id in settings.admin_bot_superusers:
            staff = StaffUser(
                id=0,
                tg_id=tg_id,
                role=StaffRole.GLOBAL_ADMIN,
                is_active=True,
                city_ids=frozenset(),
                full_name="Superuser",
                phone="",
            )
            return {"staff": staff}

        staff_service = get_service(bot, "staff_service", required=False)
        if staff_service is None:
            return False
        staff = await staff_service.get_by_tg_id(tg_id)
        if not staff or not staff.is_active:
            return False
        if self._roles and staff.role not in self._roles:
            return False
        return {"staff": staff}


__all__ = ["StaffRoleFilter"]
