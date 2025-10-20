"""
P1-16:    

 10       
       .
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from field_service.db import models as m
from field_service.db.session import SessionLocal
from field_service.services import live_log

UTC = timezone.utc

#        
REMINDER_MINUTES_BEFORE = 10

# ID    (     )
#    ,   
_reminded_master_breaks: dict[int, datetime] = {}


async def _check_breaks_once() -> None:
    """       10   ."""
    async with SessionLocal() as session:
        now = datetime.now(UTC)
        reminder_threshold = now + timedelta(minutes=REMINDER_MINUTES_BEFORE)
        
        #     ,       10 
        result = await session.execute(
            select(m.masters.id, m.masters.tg_user_id, m.masters.break_until)
            .where(
                m.masters.shift_status == m.ShiftStatus.BREAK,
                m.masters.break_until.isnot(None),
                m.masters.break_until <= reminder_threshold,
                m.masters.break_until > now,
            )
        )
        
        masters = result.all()
        
        if not masters:
            return
        
        #    ,    
        for master_id, tg_user_id, break_until in masters:
            stored_break_until = _reminded_master_breaks.get(master_id)
            if stored_break_until is not None:
                if stored_break_until != break_until:
                    #   ,    
                    _reminded_master_breaks.pop(master_id, None)
                else:
                    continue  #       
            
            if not tg_user_id:
                continue  #  Telegram ID
            
            #    
            time_left = break_until - now
            minutes_left = int(time_left.total_seconds() / 60)
            
            #  
            message = (
                f" <b>   {minutes_left} </b>\n\n"
                "   ?\n\n"
                "        2 ."
            )
            
            #    
            await session.execute(
                insert(m.notifications_outbox).values(
                    master_id=master_id,
                    event="break_reminder",
                    payload={
                        "message": message,
                        "minutes_left": minutes_left,
                        "break_until": break_until.isoformat(),
                    }
                )
            )
            
            # ,       
            _reminded_master_breaks[master_id] = break_until
            
            live_log.push(
                "break_reminder",
                f"Sent break reminder to master#{master_id}, {minutes_left}min left",
                level="INFO"
            )
        
        await session.commit()


async def _cleanup_reminded_set(session: AsyncSession | None = None) -> None:
    """
        ,     .
        ,     .
    
    Args:
        session:    
    """
    if session is not None:
        #    ( )
        await _cleanup_impl(session)
    else:
        #   
        async with SessionLocal() as session:
            await _cleanup_impl(session)


async def _cleanup_impl(session: AsyncSession) -> None:
    """  ."""
    now = datetime.now(UTC)
    
    #     _reminded_master_breaks
    if not _reminded_master_breaks:
        return

    tracked_ids = list(_reminded_master_breaks)

    result = await session.execute(
        select(
            m.masters.id,
            m.masters.break_until,
            m.masters.shift_status,
        ).where(m.masters.id.in_(tracked_ids))
    )

    removed_count = 0

    for master_id, break_until, shift_status in result.all():
        stored_break_until = _reminded_master_breaks.get(master_id)

        should_remove = False

        if shift_status != m.ShiftStatus.BREAK:
            should_remove = True
        elif break_until is None or break_until <= now:
            should_remove = True
        elif stored_break_until is not None and break_until != stored_break_until:
            should_remove = True

        if should_remove and master_id in _reminded_master_breaks:
            _reminded_master_breaks.pop(master_id, None)
            removed_count += 1

    if removed_count:
        live_log.push(
            "break_reminder",
            f"Cleaned up {removed_count} entries from reminder cache",
            level="DEBUG"
        )


async def run_break_reminder(*, interval_seconds: int = 60) -> None:
    """
         .
    
    Args:
        interval_seconds:     (  60 )
    """
    sleep_for = max(10, int(interval_seconds))
    
    live_log.push(
        "break_reminder",
        f"Break reminder scheduler started (interval={sleep_for}s, reminder={REMINDER_MINUTES_BEFORE}min before)",
        level="INFO"
    )
    
    while True:
        try:
            await _check_breaks_once()
            await _cleanup_reminded_set()
        except Exception as exc:
            live_log.push(
                "break_reminder",
                f"Error in break reminder: {exc}",
                level="ERROR"
            )
        
        await asyncio.sleep(sleep_for)
