from __future__ import annotations

from typing import Iterable, Optional

from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, Message, TelegramObject

from field_service.config import settings

SUPERUSER_IDS = frozenset(set(settings.admin_bot_superusers) | set(settings.global_admins_tg_ids))

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
        preloaded = kwargs.get("staff")
        if isinstance(preloaded, StaffUser):
            if not preloaded.is_active:
                return False
            if self._roles and preloaded.role not in self._roles:
                return False
            return {"staff": preloaded}

        tg_id = _extract_user_id(event)
        if tg_id is None:
            return False

        # CR-2025-10-03-FIX: ALWAYS load staff from DB, even for superusers
        # Never create virtual StaffUser with id=0 - it breaks FK constraints
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
