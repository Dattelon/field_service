from __future__ import annotations

from datetime import timedelta

from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from field_service.db import models as m

from ..utils import now_utc

router = Router(name="master_shift")

BREAK_DURATION = timedelta(hours=2)


@router.callback_query(F.data == "m:sh:on")
async def shift_on(callback: CallbackQuery, session: AsyncSession, master: m.masters) -> None:
    if master.is_blocked:
        await callback.answer("Вы заблокированы. Свяжитесь с поддержкой.", show_alert=True)
        return
    if getattr(master, "moderation_status", m.ModerationStatus.PENDING) != m.ModerationStatus.APPROVED:
        await callback.answer("Your profile is pending moderation.", show_alert=True)
        return

    master.shift_status = m.ShiftStatus.SHIFT_ON
    master.is_on_shift = True
    master.break_until = None
    await session.commit()
    await callback.answer("Смена включена.", show_alert=True)


@router.callback_query(F.data == "m:sh:off")
async def shift_off(callback: CallbackQuery, session: AsyncSession, master: m.masters) -> None:
    master.shift_status = m.ShiftStatus.SHIFT_OFF
    master.is_on_shift = False
    master.break_until = None
    await session.commit()
    await callback.answer("Смена выключена.", show_alert=True)


@router.callback_query(F.data == "m:sh:brk")
async def shift_break_start(callback: CallbackQuery, session: AsyncSession, master: m.masters) -> None:
    if master.shift_status != m.ShiftStatus.SHIFT_ON:
        await callback.answer("Включите смену перед тем как брать перерыв.", show_alert=True)
        return

    master.shift_status = m.ShiftStatus.BREAK
    master.is_on_shift = False
    master.break_until = now_utc() + BREAK_DURATION
    await session.commit()
    await callback.answer("Перерыв на 2 часа начат.", show_alert=True)


@router.callback_query(F.data == "m:sh:brk:ok")
async def shift_break_end(callback: CallbackQuery, session: AsyncSession, master: m.masters) -> None:
    if master.shift_status != m.ShiftStatus.BREAK:
        await callback.answer("Перерыв не активен.", show_alert=True)
        return

    master.shift_status = m.ShiftStatus.SHIFT_ON
    master.is_on_shift = True
    master.break_until = None
    await session.commit()
    await callback.answer("Возвращаемся к смене.", show_alert=True)
