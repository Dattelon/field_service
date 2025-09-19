from __future__ import annotations

import asyncio
from sqlalchemy import text

from field_service.db.session import SessionLocal


async def watchdog_commissions_overdue(bot, alerts_chat_id: int | None, interval_seconds: int = 60):
    """Periodically check overdue commissions and optionally notify admin chat."""
    while True:
        try:
            async with SessionLocal() as s:
                q = await s.execute(text(
                    """
                    SELECT count(*) FROM commissions
                    WHERE status='WAIT_PAY' AND due_at < NOW()
                    """
                ))
                cnt = int(q.scalar_one())
                if alerts_chat_id and cnt > 0:
                    try:
                        await bot.send_message(alerts_chat_id, f"Просроченных комиссий: {cnt}")
                    except Exception:
                        pass
        except Exception:
            # swallow errors to keep watchdog alive
            pass
        await asyncio.sleep(interval_seconds)

