# field_service/bots/admin_bot/handlers_staff.py
from __future__ import annotations

import random
import string
from typing import Optional

from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, Message
from sqlalchemy import select, and_, text
from sqlalchemy.ext.asyncio import AsyncSession

from field_service.db import models as m
from field_service.db.session import SessionLocal

router = Router(name=__name__)

# ==== helpers ====

def kb(rows: list[list[InlineKeyboardButton]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=rows)

async def get_staff(session: AsyncSession, tg_user_id: int) -> Optional[m.staff_users]:
    q = await session.execute(
        select(m.staff_users).where(
            and_(
                m.staff_users.tg_user_id == tg_user_id,
                m.staff_users.is_active == True,
            )
        )
    )
    return q.scalar_one_or_none()

async def guard_staff(evt: Message | CallbackQuery) -> tuple[AsyncSession, m.staff_users]:
    session = SessionLocal()
    async with session as s:
        tg_id = evt.from_user.id if hasattr(evt, "from_user") else (evt.message.from_user.id if hasattr(evt, "message") else None)
        staff = await get_staff(s, tg_id)
        if not staff:
            text_err = "Доступ запрещён. Вас нет в staff_users или профиль неактивен."
            if isinstance(evt, Message):
                await evt.answer(text_err)
            else:
                await evt.message.answer(text_err)
                await evt.answer()
            raise PermissionError("staff required")
        return s, staff

def _codes_menu() -> InlineKeyboardMarkup:
    return kb([
        [InlineKeyboardButton(text="Новый код — Админ", callback_data="adm:codes:new:ADMIN")],
        [InlineKeyboardButton(text="Новый код — Логист", callback_data="adm:codes:new:LOGIST")],
        [
            InlineKeyboardButton(text="Активные", callback_data="adm:codes:list:active:1"),
            InlineKeyboardButton(text="Использованные", callback_data="adm:codes:list:used:1"),
        ],
        [InlineKeyboardButton(text="Отозванные", callback_data="adm:codes:list:revoked:1")],
        [InlineKeyboardButton(text="‹ Меню", callback_data="adm:start")],
    ])

def _staff_menu() -> InlineKeyboardMarkup:
    return kb([
        [InlineKeyboardButton(text="Список персонала", callback_data="adm:staff:list:1")],
        [InlineKeyboardButton(text="‹ Меню", callback_data="adm:start")],
    ])

# ==== root ====

@router.callback_query(F.data == "adm:codes")
async def codes_root(cb: CallbackQuery):
    try:
        _, _ = await guard_staff(cb)
    except PermissionError:
        return
    await cb.message.edit_text("<b>Доступ / Коды</b>", reply_markup=_codes_menu())
    await cb.answer()

@router.callback_query(F.data == "adm:staff")
async def staff_root(cb: CallbackQuery):
    try:
        _, _ = await guard_staff(cb)
    except PermissionError:
        return
    await cb.message.edit_text("<b>Персонал</b>", reply_markup=_staff_menu())
    await cb.answer()

# ==== генерация кода ====

def _gen_code(n: int = 8) -> str:
    base = string.ascii_uppercase + string.digits
    return "".join(random.choice(base) for _ in range(n))

@router.callback_query(F.data.startswith("adm:codes:new:"))
async def code_new_make(cb: CallbackQuery):
    _, _, _, role = cb.data.split(":")  # ADMIN | LOGIST
    try:
        s, staff = await guard_staff(cb)
    except PermissionError:
        return

    code = _gen_code()
    async with s.begin():
        await s.execute(text("""
            INSERT INTO staff_access_codes (code, role, issued_by_staff_id, comment)
            VALUES (:c, :r, (SELECT id FROM staff_users WHERE tg_user_id=:tg LIMIT 1), NULL)
        """).bindparams(c=code, r=role, tg=cb.from_user.id))
    await cb.message.edit_text(f"Код: <code>{code}</code>\nРоль: <b>{role}</b>", reply_markup=_codes_menu())
    await cb.answer("Сгенерирован")

# ==== списки кодов ====

PAGE = 15

async def _render_codes_list(cb: CallbackQuery, kind: str, page: int):
    where = {
        "active": "used_at IS NULL AND is_revoked=FALSE",
        "used": "used_at IS NOT NULL",
        "revoked": "is_revoked=TRUE",
    }[kind]
    offset = (page - 1) * PAGE
    async with SessionLocal() as s:
        rows = await s.execute(text(f"""
            SELECT id, code, role, created_at, used_at, is_revoked
              FROM staff_access_codes
             WHERE {where}
             ORDER BY created_at DESC
             LIMIT :limit OFFSET :offset
        """).bindparams(limit=PAGE, offset=offset))
        items = rows.all()

    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton(text="⇦", callback_data=f"adm:codes:list:{kind}:{page-1}"))
    nav.append(InlineKeyboardButton(text=f"{page}", callback_data="adm:noop"))
    if len(items) == PAGE:
        nav.append(InlineKeyboardButton(text="⇨", callback_data=f"adm:codes:list:{kind}:{page+1}"))

    buttons = [[InlineKeyboardButton(
        text=(f"{i.id}: {i.code} — {i.role} — " + ("Отозван" if i.is_revoked else ("Использован" if i.used_at else "Активен"))),
        callback_data=f"adm:codes:card:{i.id}"
    )] for i in items]
    buttons += [nav] if nav else []
    buttons += [[InlineKeyboardButton(text="‹ Меню", callback_data="adm:codes")]]
    await cb.message.edit_text(f"<b>Коды / {kind}</b>", reply_markup=kb(buttons))
    await cb.answer()

@router.callback_query(F.data.startswith("adm:codes:list:"))
async def codes_list(cb: CallbackQuery):
    _, _, _, kind, page = cb.data.split(":")
    await _render_codes_list(cb, kind, int(page))

@router.callback_query(F.data.startswith("adm:codes:card:"))
async def code_card(cb: CallbackQuery):
    cid = int(cb.data.split(":")[-1])
    async with SessionLocal() as s:
        row = await s.execute(text("""
            SELECT id, code, role, created_at, used_at, is_revoked
              FROM staff_access_codes WHERE id=:i
        """).bindparams(i=cid))
        r = row.first()
    if not r:
        await cb.answer("Код не найден.", show_alert=True); return

    _id, code, role, created_at, used_at, revoked = r
    rows = []
    if not revoked and not used_at:
        rows.append([InlineKeyboardButton(text="🚫 Отозвать", callback_data=f"adm:codes:revoke:{_id}")])
    rows.append([InlineKeyboardButton(text="‹ К списку", callback_data="adm:codes:list:active:1")])
    txt = (f"<b>Код</b>: <code>{code}</code>\nРоль: <b>{role}</b>\nСоздан: {created_at:%Y-%m-%d %H:%M}\n"
           f"Статус: {'Отозван' if revoked else ('Использован' if used_at else 'Активен')}")
    await cb.message.edit_text(txt, reply_markup=kb(rows)); await cb.answer()

@router.callback_query(F.data.startswith("adm:codes:revoke:"))
async def code_revoke(cb: CallbackQuery):
    cid = int(cb.data.split(":")[-1])
    async with SessionLocal() as s:
        upd = await s.execute(text("""
            UPDATE staff_access_codes
               SET is_revoked=TRUE
             WHERE id=:i AND used_at IS NULL AND is_revoked=FALSE
             RETURNING id
        """).bindparams(i=cid))
        ok = upd.first()
        if ok: await s.commit()
    await cb.answer("Готово" if ok else "Нельзя отозвать (уже использован/отозван).", show_alert=not ok)
    await _render_codes_list(cb, "active", 1)

# ==== персонал (краткий каркас) ====

@router.callback_query(F.data.startswith("adm:staff:list:"))
async def staff_list(cb: CallbackQuery):
    _, _, _, page = cb.data.split(":")
    page = int(page); PAGE = 15; offset = (page-1)*PAGE
    async with SessionLocal() as s:
        rows = await s.execute(text("""
            SELECT id, tg_user_id, role, is_active, created_at
              FROM staff_users
             ORDER BY created_at DESC
             LIMIT :lim OFFSET :off
        """).bindparams(lim=PAGE, off=offset))
        items = rows.all()

    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton(text="⇦", callback_data=f"adm:staff:list:{page-1}"))
    if len(items) == PAGE:
        nav.append(InlineKeyboardButton(text="⇨", callback_data=f"adm:staff:list:{page+1}"))

    btns = [[InlineKeyboardButton(
        text=f"{i.id} · {i.role} · {'ON' if i.is_active else 'OFF'}",
        callback_data=f"adm:staff:card:{i.id}"
    )] for i in items]
    if nav: btns.append(nav)
    btns.append([InlineKeyboardButton(text="‹ Меню", callback_data="adm:staff")])
    await cb.message.edit_text("<b>Персонал</b>", reply_markup=kb(btns)); await cb.answer()

@router.callback_query(F.data.startswith("adm:staff:card:"))
async def staff_card(cb: CallbackQuery):
    sid = int(cb.data.split(":")[-1])
    async with SessionLocal() as s:
        row = await s.execute(text("""
            SELECT id, tg_user_id, role, is_active, created_at
              FROM staff_users WHERE id=:i
        """).bindparams(i=sid))
        r = row.first()
    if not r:
        await cb.answer("Не найдено.", show_alert=True); return
    _id, tgid, role, active, created = r
    rows = [
        [InlineKeyboardButton(text=("🔓 Активировать" if not active else "🚫 Деактивировать"), callback_data=f"adm:staff:toggle:{_id}")],
        [InlineKeyboardButton(text="‹ К списку", callback_data="adm:staff:list:1")],
    ]
    await cb.message.edit_text(
        f"<b>Сотрудник</b> #{_id}\nTG: <code>{tgid}</code>\nРоль: <b>{role}</b>\nСтатус: {'ON' if active else 'OFF'}\nСоздан: {created:%Y-%m-%d %H:%M}",
        reply_markup=kb(rows)
    )
    await cb.answer()

@router.callback_query(F.data.startswith("adm:staff:toggle:"))
async def staff_toggle(cb: CallbackQuery):
    sid = int(cb.data.split(":")[-1])
    async with SessionLocal() as s:
        upd = await s.execute(text("""
            UPDATE staff_users SET is_active = NOT is_active
             WHERE id=:i
             RETURNING is_active
        """).bindparams(i=sid))
        row = upd.first()
        if row: await s.commit()
    await cb.answer("Готово"); await staff_card(cb)
