from __future__ import annotations

from typing import Any
from sqlalchemy import insert, text
from sqlalchemy.ext.asyncio import AsyncSession

from field_service.db import models as m


async def enqueue_master_notification(
    session: AsyncSession,
    *,
    master_id: int,
    message: str,
    event: str = "MASTER_MESSAGE",
) -> None:
    # Debounce: не дублируем одинаковые непрочитанные уведомления
    try:
        exists = await session.execute(
            text(
                """
                SELECT 1
                  FROM notifications_outbox
                 WHERE master_id = :mid
                   AND event = :evt
                   AND payload->>'message' = :msg
                   AND created_at >= NOW() - make_interval(secs => :window)
                 LIMIT 1
                """
            ).bindparams(mid=master_id, evt=event, msg=message, window=3600)
        )
        if exists.first() is not None:
            return
    except Exception:
        # Если БД не поддерживает JSON‑операторы — продолжаем без дебаунса
        pass

    payload: dict[str, Any] = {"message": message}
    await session.execute(
        insert(m.notifications_outbox).values(
            master_id=master_id,
            event=event,
            payload=payload,
        )
    )
