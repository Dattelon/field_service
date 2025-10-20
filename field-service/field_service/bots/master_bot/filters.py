from __future__ import annotations

from typing import Any

from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, Message

from field_service.db import models as m


class VerifiedMasterFilter(BaseFilter):
    def __init__(self, require_active: bool = True) -> None:
        self._require_active = require_active

    async def __call__(self, event: Message | CallbackQuery, data: dict[str, Any]) -> bool:
        master: m.masters | None = data.get("master")
        if master is None:
            return False
        if not getattr(master, "verified", False):
            return False
        if self._require_active and not getattr(master, "is_active", False):
            return False
        if getattr(master, "is_blocked", False):
            return False
        return True


class PendingModerationFilter(BaseFilter):
    async def __call__(self, event: Message | CallbackQuery, data: dict[str, Any]) -> bool:
        master: m.masters | None = data.get("master")
        if master is None:
            return False
        status = getattr(master, "moderation_status", m.ModerationStatus.PENDING)
        return status == m.ModerationStatus.PENDING
