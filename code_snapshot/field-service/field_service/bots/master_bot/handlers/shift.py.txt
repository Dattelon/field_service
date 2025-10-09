from __future__ import annotations

from datetime import timedelta

from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from field_service.bots.common import safe_answer_callback
from field_service.db import models as m

from ..texts import SHIFT_MESSAGES
from ..utils import now_utc
from .start import _render_start

router = Router(name="master_shift")

BREAK_DURATION = timedelta(hours=2)


async def _answer(callback: CallbackQuery, message: str, *, alert: bool = True) -> None:
    await safe_answer_callback(callback, message, show_alert=alert)


@router.callback_query(F.data == "m:sh:on")
async def shift_on(callback: CallbackQuery, session: AsyncSession, master: m.masters) -> None:
    if master.is_blocked:
        await _answer(callback, SHIFT_MESSAGES["blocked"])
        return
    if getattr(master, "moderation_status", m.ModerationStatus.PENDING) != m.ModerationStatus.APPROVED:
        await _answer(callback, SHIFT_MESSAGES["pending"])
        return
    master.shift_status = m.ShiftStatus.SHIFT_ON
    master.is_on_shift = True
    master.break_until = None
    await session.commit()
    await _answer(callback, SHIFT_MESSAGES["started"])
    if callback.message:
        await _render_start(callback.message, master)


@router.callback_query(F.data == "m:sh:off")
async def shift_off(callback: CallbackQuery, session: AsyncSession, master: m.masters) -> None:
    master.shift_status = m.ShiftStatus.SHIFT_OFF
    master.is_on_shift = False
    master.break_until = None
    await session.commit()
    await _answer(callback, SHIFT_MESSAGES["finished"])
    if callback.message:
        await _render_start(callback.message, master)


@router.callback_query(F.data == "m:sh:brk")
async def shift_break_start(callback: CallbackQuery, session: AsyncSession, master: m.masters) -> None:
    if master.shift_status != m.ShiftStatus.SHIFT_ON:
        await _answer(callback, SHIFT_MESSAGES["inactive"])
        return
    master.shift_status = m.ShiftStatus.BREAK
    master.is_on_shift = False
    master.break_until = now_utc() + BREAK_DURATION
    await session.commit()
    await _answer(callback, SHIFT_MESSAGES["break_started"])
    if callback.message:
        await _render_start(callback.message, master)


@router.callback_query(F.data == "m:sh:brk:ok")
async def shift_break_end(callback: CallbackQuery, session: AsyncSession, master: m.masters) -> None:
    if master.shift_status != m.ShiftStatus.BREAK:
        await _answer(callback, SHIFT_MESSAGES["not_break"])
        return
    master.shift_status = m.ShiftStatus.SHIFT_ON
    master.is_on_shift = True
    master.break_until = None
    await session.commit()
    await _answer(callback, SHIFT_MESSAGES["break_finished"])
    if callback.message:
        await _render_start(callback.message, master)



# P1-16: Продление перерыва
@router.callback_query(F.data == "m:sh:brk:extend")
async def shift_break_extend(callback: CallbackQuery, session: AsyncSession, master: m.masters) -> None:
    """Продлевает текущий перерыв ещё на 2 часа."""
    if master.shift_status != m.ShiftStatus.BREAK:
        await _answer(callback, SHIFT_MESSAGES["not_break"])
        return
    
    # Продлеваем перерыв
    master.break_until = now_utc() + BREAK_DURATION
    await session.commit()
    
    await _answer(callback, SHIFT_MESSAGES["break_extended"])
    if callback.message:
        await _render_start(callback.message, master)
