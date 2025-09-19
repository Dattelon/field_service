# file: field_service/bots/admin_bot/handlers.py
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from datetime import datetime, date, time, timedelta, timezone
from typing import Optional, Sequence
try:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
except Exception:
    ZoneInfo = None
    class ZoneInfoNotFoundError(Exception):
        pass

from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    BufferedInputFile
)
from sqlalchemy import select, and_, text
from sqlalchemy.ext.asyncio import AsyncSession

from field_service.config import settings
from field_service.db import models as m
from field_service.db.session import SessionLocal
from field_service.db.pg_enums import commission_status_param as cs_param  # уже используется у вас

router = Router(name=__name__)

# ==== TZ / slots / kb ====

def _resolve_tz():
    if ZoneInfo is not None:
        try:
            return ZoneInfo(settings.timezone or "Europe/Moscow")
        except ZoneInfoNotFoundError:
            pass
        except Exception:
            pass
    return timezone.utc

TZ = _resolve_tz()
SLOTS = [("10–13", time(10, 0), time(13, 0)), ("13–16", time(13, 0), time(16, 0)), ("16–19", time(16, 0), time(19, 0))]
PAGE_SIZE = 10

def kb(rows: list[list[InlineKeyboardButton]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=rows)

# ==== guard staff (как у вас) ====

async def get_staff(session: AsyncSession, tg_user_id: int) -> Optional[m.staff_users]:
    q = await session.execute(
        select(m.staff_users).where(
            and_(m.staff_users.tg_user_id == tg_user_id, m.staff_users.is_active == True)
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

# ==== меню (как у вас) ====

def _main_menu() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="📋 Очередь", callback_data="adm:queue"),
         InlineKeyboardButton(text="➕ Новая заявка", callback_data="adm:new")],
        [InlineKeyboardButton(text="🧑‍🔧 Мастера/модерация", callback_data="adm:masters")],
        [InlineKeyboardButton(text="💳 Финансы", callback_data="adm:finance"),
         InlineKeyboardButton(text="📤 Отчёты", callback_data="adm:reports")],
        [InlineKeyboardButton(text="⚙️ Настройки", callback_data="adm:settings")],
        [InlineKeyboardButton(text="👥 Персонал", callback_data="adm:staff"),
         InlineKeyboardButton(text="🔑 Коды", callback_data="adm:codes")],
        [InlineKeyboardButton(text="📣 Логи", callback_data="adm:logs")],
    ]
    return kb(rows)

@router.message(CommandStart())
async def on_start(message: Message):
    try:
        _, _ = await guard_staff(message)
    except PermissionError:
        return
    await message.answer("<b>Админ‑бот: главное меню</b>", reply_markup=_main_menu())

@router.message(F.text == "/start")
async def on_start_text(message: Message):
    return await on_start(message)

@router.callback_query(F.data == "adm:start")
async def on_menu(cb: CallbackQuery):
    try:
        _, _ = await guard_staff(cb)
    except PermissionError:
        return
    await cb.message.edit_text("<b>Админ‑бот: главное меню</b>", reply_markup=_main_menu()); await cb.answer()

# ==== ... здесь остаются ваш готовый код очереди/карточек/назначения, новая заявка, мастера, финансы, настройки, реквизиты ====
# (ничего не ломаю; финансы уже используют cs_param для ENUM — это ваш свежий фикс ошибки с VARCHAR → ENUM)  # :contentReference[oaicite:6]{index=6}

# ==========================
#  ДОБАВЛЕНО: ОТЧЁТЫ — КОМИССИИ / РЕФЕРАЛКА
# ==========================

class AdmRepCommissions(StatesGroup):
    range = State()
    fmt = State()

class AdmRepReferrals(StatesGroup):
    range = State()
    fmt = State()

def _reports_menu() -> InlineKeyboardMarkup:
    return kb([
        [InlineKeyboardButton(text="Заказы (CSV)", callback_data="adm:rep:orders:csv"),
         InlineKeyboardButton(text="Заказы (XLSX)", callback_data="adm:rep:orders:xlsx")],
        [InlineKeyboardButton(text="Комиссии (CSV)", callback_data="adm:rep:comm:csv"),
         InlineKeyboardButton(text="Комиссии (XLSX)", callback_data="adm:rep:comm:xlsx")],
        [InlineKeyboardButton(text="Рефералка (CSV)", callback_data="adm:rep:ref:csv"),
         InlineKeyboardButton(text="Рефералка (XLSX)", callback_data="adm:rep:ref:xlsx")],
        [InlineKeyboardButton(text="Быстро: 7 дней", callback_data="adm:rep:preset:7"),
         InlineKeyboardButton(text="30 дней", callback_data="adm:rep:preset:30"),
         InlineKeyboardButton(text="Этот месяц", callback_data="adm:rep:preset:month")],
        [InlineKeyboardButton(text="‹ Меню", callback_data="adm:start")],
    ])

@router.callback_query(F.data == "adm:reports")
async def reports_root(cb: CallbackQuery):
    try:
        _, _ = await guard_staff(cb)
    except PermissionError:
        return
    await cb.message.edit_text("<b>Отчёты</b>\nВыберите тип и формат.", reply_markup=_reports_menu()); await cb.answer()

# ---- пресеты диапазонов

def _month_range_utcnow() -> tuple[date, date]:
    now = datetime.now(TZ).date()
    d1 = now.replace(day=1)
    return d1, now

async def _send_orders_export(cb: CallbackQuery, d1: date, d2: date, fmt: str):
    # reuse вашей реализации экспорта заказов (она у вас уже есть)
    # оставляю вызов вашего хендлера через message-flow, чтобы не дублировать код
    await cb.message.answer(f"Экспорт заказов {d1}..{d2} ({fmt}). Введите диапазон через уже имеющийся сценарий в боте.")
    await cb.answer()

@router.callback_query(F.data.startswith("adm:rep:preset:"))
async def rep_preset(cb: CallbackQuery):
    kind = cb.data.split(":")[-1]
    if kind == "7":
        d2 = datetime.now(TZ).date(); d1 = d2 - timedelta(days=7)
    elif kind == "30":
        d2 = datetime.now(TZ).date(); d1 = d2 - timedelta(days=30)
    else:
        d1, d2 = _month_range_utcnow()
    await cb.message.answer(f"Период: <b>{d1}</b>.. <b>{d2}</b>\n"
                            f"Для заказов используйте существующую форму диапазона. Для комиссий/рефералки — введите <code>{d1}..{d2}</code> после выбора формата.")
    await cb.answer()

# ---- Комиссии

@router.callback_query(F.data.startswith("adm:rep:comm:"))
async def rep_comm_start(cb: CallbackQuery, state: FSMContext):
    fmt = cb.data.split(":")[-1]  # csv|xlsx
    await state.set_state(AdmRepCommissions.range)
    await state.update_data(fmt=fmt)
    await cb.message.answer("Комиссии. Укажите диапазон дат в формате YYYY-MM-DD..YYYY-MM-DD (по created_at).")
    await cb.answer()

@router.message(AdmRepCommissions.range)
async def rep_comm_range(msg: Message, state: FSMContext):
    try:
        part = (msg.text or "").strip()
        d1s, d2s = part.split("..")
        d1 = date.fromisoformat(d1s); d2 = date.fromisoformat(d2s)
    except Exception:
        await msg.answer("Неверный формат. Пример: 2025-09-01..2025-09-17"); return
    data = await state.get_data(); fmt = data["fmt"]

    async with SessionLocal() as s:
        rows = await s.execute(text("""
            SELECT
              c.id, c.order_id, c.master_id, m.full_name AS master_name, m.phone AS master_phone,
              c.amount, c.rate, c.created_at AT TIME ZONE 'UTC' AS created_at_utc,
              c.due_at AT TIME ZONE 'UTC' AS deadline_at_utc,
              c.paid_reported_at AT TIME ZONE 'UTC' AS paid_reported_at_utc,
              c.paid_approved_at AT TIME ZONE 'UTC' AS paid_approved_at_utc,
              c.paid_amount, c.is_paid,
              CASE WHEN c.has_checks THEN 'yes' ELSE 'no' END AS has_checks,
              COALESCE( (c.pay_to_snapshot->>'methods'), '' ) AS snapshot_methods,
              COALESCE( (c.pay_to_snapshot->'card'->>'number_last4'), '' ) AS snapshot_card_number_last4,
              COALESCE( (c.pay_to_snapshot->'sbp'->>'phone_masked'), '' ) AS snapshot_sbp_phone_masked
            FROM commissions c
            JOIN masters m ON m.id=c.master_id
            WHERE c.created_at::date BETWEEN :d1 AND :d2
            ORDER BY c.created_at
        """).bindparams(d1=d1, d2=d2))
        items = rows.all()

    headers = [
      "commission_id","order_id","master_id","master_name","master_phone",
      "amount","rate","created_at_utc","deadline_at_utc",
      "paid_reported_at_utc","paid_approved_at_utc","paid_amount","is_paid",
      "has_checks","snapshot_methods","snapshot_card_number_last4","snapshot_sbp_phone_masked"
    ]
    if fmt == "csv":
        buff = io.StringIO()
        w = csv.writer(buff, delimiter=";")
        w.writerow(headers)
        for r in items: w.writerow(list(r))
        data_bytes = buff.getvalue().encode("utf-8")
        await msg.answer_document(BufferedInputFile(data_bytes, filename=f"comm_{d1}_{d2}.csv"))
    else:
        try:
            import xlsxwriter  # noqa
        except Exception:
            await msg.answer("XlsxWriter не установлен. Добавьте его в requirements."); return
        mem = io.BytesIO()
        import xlsxwriter
        wb = xlsxwriter.Workbook(mem)
        ws = wb.add_worksheet("commissions")
        for col, h in enumerate(headers): ws.write(0, col, h)
        for row_idx, row in enumerate(items, start=1):
            for col, val in enumerate(row):
                ws.write(row_idx, col, "" if val is None else str(val))
        wb.close(); mem.seek(0)
        await msg.answer_document(BufferedInputFile(mem.read(), filename=f"comm_{d1}_{d2}.xlsx"))
    await state.clear()

# ---- Рефералка (сводный отчёт по связке мастер→реферер)

@router.callback_query(F.data.startswith("adm:rep:ref:"))
async def rep_ref_start(cb: CallbackQuery, state: FSMContext):
    fmt = cb.data.split(":")[-1]  # csv|xlsx
    await state.set_state(AdmRepReferrals.range)
    await state.update_data(fmt=fmt)
    await cb.message.answer("Рефералка. Укажите диапазон по дате регистрации мастера: YYYY-MM-DD..YYYY-MM-DD.")
    await cb.answer()

@router.message(AdmRepReferrals.range)
async def rep_ref_range(msg: Message, state: FSMContext):
    try:
        part = (msg.text or "").strip()
        d1s, d2s = part.split("..")
        d1 = date.fromisoformat(d1s); d2 = date.fromisoformat(d2s)
    except Exception:
        await msg.answer("Неверный формат. Пример: 2025-09-01..2025-09-17"); return
    data = await state.get_data(); fmt = data["fmt"]

    async with SessionLocal() as s:
        rows = await s.execute(text("""
            SELECT m.id AS master_id,
                   m.referred_by_master_id AS referrer_id,
                   m.created_at::date AS joined_on
              FROM masters m
             WHERE m.created_at::date BETWEEN :d1 AND :d2
               AND m.referred_by_master_id IS NOT NULL
             ORDER BY joined_on
        """).bindparams(d1=d1, d2=d2))
        items = rows.all()

    headers = ["master_id","referrer_id","joined_on"]
    if fmt == "csv":
        buff = io.StringIO()
        w = csv.writer(buff, delimiter=";")
        w.writerow(headers)
        for r in items: w.writerow(list(r))
        data_bytes = buff.getvalue().encode("utf-8")
        await msg.answer_document(BufferedInputFile(data_bytes, filename=f"ref_{d1}_{d2}.csv"))
    else:
        try:
            import xlsxwriter  # noqa
        except Exception:
            await msg.answer("XlsxWriter не установлен. Добавьте его в requirements."); return
        mem = io.BytesIO()
        import xlsxwriter
        wb = xlsxwriter.Workbook(mem)
        ws = wb.add_worksheet("referrals")
        for col, h in enumerate(headers): ws.write(0, col, h)
        for row_idx, row in enumerate(items, start=1):
            for col, val in enumerate(row):
                ws.write(row_idx, col, "" if val is None else str(val))
        wb.close(); mem.seek(0)
        await msg.answer_document(BufferedInputFile(mem.read(), filename=f"ref_{d1}_{d2}.xlsx"))
    await state.clear()

# ==========================
#  ДОБАВЛЕНО: ЛОГИ (adm:l)
# ==========================

def _logs_menu() -> InlineKeyboardMarkup:
    return kb([
        [InlineKeyboardButton(text="Live: последние 50", callback_data="adm:logs:live")],
        [InlineKeyboardButton(text="‹ Меню", callback_data="adm:start")],
    ])

@router.callback_query(F.data == "adm:logs")
async def logs_root(cb: CallbackQuery):
    try:
        _, _ = await guard_staff(cb)
    except PermissionError:
        return
    await cb.message.edit_text("<b>Логи</b>", reply_markup=_logs_menu()); await cb.answer()

@router.callback_query(F.data == "adm:logs:live")
async def logs_live(cb: CallbackQuery):
    # берём историю статусов заказов как основу
    async with SessionLocal() as s:
        rows = await s.execute(text("""
            SELECT h.order_id, h.status, h.changed_at, h.source
              FROM order_status_history h
             ORDER BY h.changed_at DESC
             LIMIT 50
        """))
        items = rows.all()
    lines = [f"#{i.order_id} · {i.status} · {i.changed_at:%Y-%m-%d %H:%M} · {i.source}" for i in items]
    txt = "<b>Последние события</b>\n" + ("\n".join(lines) if lines else "—")
    await cb.message.edit_text(txt, reply_markup=_logs_menu()); await cb.answer()
