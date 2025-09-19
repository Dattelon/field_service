from __future__ import annotations

import asyncio
import math
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from aiogram import Router, F, Bot
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ContentType,
)

from sqlalchemy import select, update, and_, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from field_service.config import settings
from field_service.db import models as m
from field_service.db.session import SessionLocal

router = Router(name=__name__)
TZ = timezone.utc

# ======================= FSM =======================
class Onboarding(StatesGroup):
    access_code = State()
    pdn = State()
    fio = State()
    phone = State()
    city = State()
    districts = State()          # выбор по страницам
    districts_search = State()   # ввод строки поиска
    vehicle = State()
    skills = State()
    passport = State()
    selfie = State()
    payout_method = State()
    payout_requisites = State()
    home_geo = State()
    confirm = State()

# ======================= UI helpers =======================
def kb_inline(rows: list[list[InlineKeyboardButton]]):
    return InlineKeyboardMarkup(inline_keyboard=rows)

def kb_yes_no(cb_yes: str, cb_no: str):
    return kb_inline([
        [InlineKeyboardButton(text="Да", callback_data=cb_yes)],
        [InlineKeyboardButton(text="Нет", callback_data=cb_no)],
    ])

async def delete_message_silent(bot: Bot, chat_id: int, message_id: int) -> None:
    try:
        await bot.delete_message(chat_id, message_id)
    except Exception:
        pass

async def push_step_from_message(msg: Message, state: FSMContext, text: str, reply_markup=None) -> Message:
    """Отправляет новый шаг, удаляет предыдущий шаг этого онбординга."""
    data = await state.get_data()
    prev_id = data.get("last_step_msg_id")
    sent = await msg.answer(text, reply_markup=reply_markup)
    if prev_id:
        await delete_message_silent(msg.bot, msg.chat.id, prev_id)
    # трекаем все шаги, чтобы можно было подчистить в конце
    all_ids = list(data.get("step_msg_ids", []))
    all_ids.append(sent.message_id)
    await state.update_data(last_step_msg_id=sent.message_id, step_msg_ids=all_ids)
    return sent

async def push_step_from_cb(cb: CallbackQuery, state: FSMContext, text: str, reply_markup=None) -> Message:
    return await push_step_from_message(cb.message, state, text, reply_markup)

async def clear_onboarding_ui(bot: Bot, state: FSMContext, chat_id: int) -> None:
    """Удаляет все сообщения этапов онбординга, если остались."""
    data = await state.get_data()
    for mid in data.get("step_msg_ids", []):
        await delete_message_silent(bot, chat_id, mid)
    await state.update_data(step_msg_ids=[], last_step_msg_id=None)

def now() -> datetime:
    return datetime.now(TZ)

async def get_master(session: AsyncSession, tg_user_id: int) -> Optional[m.masters]:
    q = await session.execute(select(m.masters).where(m.masters.tg_user_id == tg_user_id))
    return q.scalar_one_or_none()

async def ensure_master(session: AsyncSession, tg_user_id: int) -> m.masters:
    inst = await get_master(session, tg_user_id)
    if inst:
        return inst
    inst = m.masters(tg_user_id=tg_user_id, full_name="", is_active=False)
    session.add(inst)
    await session.commit()
    return inst

async def max_active_orders(session: AsyncSession) -> int:
    q = await session.execute(select(m.settings).where(m.settings.key == "max_active_orders"))
    s = q.scalar_one_or_none()
    try:
        return int(s.value) if s else 1
    except Exception:
        return 1

async def count_active_orders(session: AsyncSession, master_id: int) -> int:
    active_statuses = (m.OrderStatus.ASSIGNED, m.OrderStatus.SCHEDULED, m.OrderStatus.IN_PROGRESS, m.OrderStatus.DONE)
    q = await session.execute(
        select(func.count()).select_from(m.orders).where(
            and_(m.orders.assigned_master_id == master_id, m.orders.status.in_(active_statuses))
        )
    )
    return int(q.scalar_one())

def normalize_money(text_value: str) -> Optional[Decimal]:
    txt = (text_value or "").strip().replace(",", ".")
    if not re.fullmatch(r"^\d{1,9}(?:\.\d{1,2})?$", txt):
        return None
    val = Decimal(txt)
    return val if val > 0 else None

# ======================= Districts: pagination & search =======================
PAGE_SIZE = 10

async def _fetch_districts(city_id: int, query: Optional[str] = None) -> list[m.districts]:
    async with SessionLocal() as session:
        stmt = select(m.districts).where(m.districts.city_id == city_id)
        if query:
            stmt = stmt.where(m.districts.name.ilike(f"%{query.strip()}%"))
        stmt = stmt.order_by(m.districts.name)
        res = await session.execute(stmt)
        return list(res.scalars().all())

def _build_districts_keyboard(
    city_id: int,
    items: list[m.districts],
    selected_ids: set[int],
    page: int,
    pages: int,
    search_mode: bool,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []

    for d in items:
        mark = "✅" if d.id in selected_ids else "◻️"
        rows.append([InlineKeyboardButton(text=f"{mark} {d.name}", callback_data=f"m:onb:dist_tog:{d.id}:{city_id}:{'S' if search_mode else page}")])

    # Навигация
    nav: list[InlineKeyboardButton] = []
    if not search_mode and pages > 1:
        if page > 1:
            nav.append(InlineKeyboardButton(text="⟨ Назад", callback_data=f"m:onb:dist_page:{city_id}:{page-1}"))
        nav.append(InlineKeyboardButton(text=f"{page}/{pages}", callback_data="noop"))
        if page < pages:
            nav.append(InlineKeyboardButton(text="Вперёд ⟩", callback_data=f"m:onb:dist_page:{city_id}:{page+1}"))
        rows.append(nav)

    # Переключатели режима
    if search_mode:
        rows.append([InlineKeyboardButton(text="◀ Назад к списку", callback_data=f"m:onb:dist_back:{city_id}")])
    else:
        rows.append([InlineKeyboardButton(text="🔎 Поиск по названию", callback_data=f"m:onb:dist_search:{city_id}")])

    rows.append([InlineKeyboardButton(text="Готово", callback_data="m:onboarding:districts_done")])
    return kb_inline(rows)

async def _render_districts_page(
    carrier_msg: Message,
    state: FSMContext,
    city_id: int,
    page: int = 1,
) -> None:
    all_items = await _fetch_districts(city_id)
    total = len(all_items)
    pages = max(1, math.ceil(total / PAGE_SIZE))
    page = min(max(1, page), pages)
    start = (page - 1) * PAGE_SIZE
    slice_items = all_items[start : start + PAGE_SIZE]

    data = await state.get_data()
    selected = set(data.get("district_ids", []))

    kb = _build_districts_keyboard(city_id, slice_items, selected, page, pages, search_mode=False)
    text = "Выберите районы обслуживания (можно несколько):"

    try:
        await carrier_msg.edit_text(text, reply_markup=kb)
    except TelegramBadRequest:
        # если нечего редактировать — просто новый шаг
        await push_step_from_message(carrier_msg, state, text, kb)

async def _render_districts_search_result(
    carrier_msg: Message,
    state: FSMContext,
    city_id: int,
    query: str,
) -> None:
    items = await _fetch_districts(city_id, query=query)
    items = items[:50]  # ограничим для UX
    data = await state.get_data()
    selected = set(data.get("district_ids", []))
    kb = _build_districts_keyboard(city_id, items, selected, page=1, pages=1, search_mode=True)
    suffix = f" (найдено: {len(items)})" if items else " (ничего не найдено)"
    text = "Поиск районов по названию" + suffix
    try:
        await carrier_msg.edit_text(text, reply_markup=kb)
    except TelegramBadRequest:
        await push_step_from_message(carrier_msg, state, text, kb)

# ======================= /start =======================
@router.message(CommandStart())
async def start(message: Message, state: FSMContext):
    async with SessionLocal() as session:
        mst = await ensure_master(session, message.from_user.id)
        moderation = getattr(mst, "moderation_status", None)
        status_label = str(moderation) if moderation is not None else ("APPROVED" if mst.is_active else "PENDING")

        text = ["<b>Мастер‑бот Field Service</b>", f"Статус модерации: <b>{status_label}</b>"]
        kb = None

        if status_label != "APPROVED":
            kb = kb_inline([[InlineKeyboardButton(text="🚀 Начать онбординг", callback_data="m:onboarding:start")]])
        else:
            buttons = []
            if hasattr(m.masters, "shift_status"):
                cur = str(getattr(mst, "shift_status", "SHIFT_OFF"))
                if cur == "SHIFT_OFF":
                    buttons.append([InlineKeyboardButton(text="🟢 Включить смену", callback_data="m:shift:on")])
                elif cur == "SHIFT_ON":
                    buttons.append([InlineKeyboardButton(text="⏸ Перерыв 2 часа", callback_data="m:break:start")])
                    buttons.append([InlineKeyboardButton(text="🔴 Выключить смену", callback_data="m:shift:off")])
                elif cur == "BREAK":
                    buttons.append([InlineKeyboardButton(text="▶️ Вернуться со смены", callback_data="m:break:stop")])
                    buttons.append([InlineKeyboardButton(text="🔴 Выключить смену", callback_data="m:shift:off")])
            kb = kb_inline(buttons) if buttons else None

        await message.answer("\n".join(text), reply_markup=kb, parse_mode=ParseMode.HTML)

# ======================= Onboarding flow =======================
@router.callback_query(F.data == "m:onboarding:start")
async def onb_start(cb: CallbackQuery, state: FSMContext):
    await state.set_state(Onboarding.access_code)
    await push_step_from_cb(cb, state, "Введите код доступа (A–Z, 0–9, длина 6–12).")
    await cb.answer()

@router.message(Onboarding.access_code)
async def onb_access_code(msg: Message, state: FSMContext):
    if not re.fullmatch(r"^[A-Z0-9]{6,12}$", msg.text or ""):
        await msg.answer("Неверный код. 6–12 символов (A–Z, 0–9).")
        return
    await state.update_data(access_code=msg.text)
    await state.set_state(Onboarding.pdn)
    kb = kb_inline([
        [InlineKeyboardButton(text="✅ Принимаю", callback_data="m:onboarding:pdn_accept")],
        [InlineKeyboardButton(text="❌ Не принимаю", callback_data="m:onboarding:pdn_decline")],
    ])
    await push_step_from_message(msg, state, "Примите согласие на обработку ПДн.", kb)

@router.callback_query(Onboarding.pdn, F.data == "m:onboarding:pdn_accept")
async def onb_pdn_accept(cb: CallbackQuery, state: FSMContext):
    await state.set_state(Onboarding.fio)
    await push_step_from_cb(cb, state, "Введите ФИО (пример: Иванов Иван Иванович).")
    await cb.answer()

@router.callback_query(Onboarding.pdn, F.data == "m:onboarding:pdn_decline")
async def onb_pdn_decline(cb: CallbackQuery, state: FSMContext):
    await clear_onboarding_ui(cb.message.bot, state, cb.message.chat.id)
    await state.clear()
    await cb.message.answer("Без согласия на ПДн продолжить нельзя. Напишите /start, если передумаете.")
    await cb.answer()

@router.message(Onboarding.fio)
async def onb_fio(msg: Message, state: FSMContext):
    if not re.fullmatch(r"^[А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+){1,2}$", msg.text or ""):
        await msg.answer("Введите ФИО полностью, напр.: Иванов Иван Иванович.")
        return
    await state.update_data(full_name=msg.text)
    await state.set_state(Onboarding.phone)
    await push_step_from_message(msg, state, "Телефон в формате +71234567890.")

@router.message(Onboarding.phone)
async def onb_phone(msg: Message, state: FSMContext):
    if not re.fullmatch(r"^\+\d{10,15}$", msg.text or ""):
        await msg.answer("Телефон в формате +71234567890.")
        return
    await state.update_data(phone=msg.text)

    # Город
    async with SessionLocal() as session:
        q = await session.execute(select(m.cities).where(m.cities.is_active == True).order_by(m.cities.name))
        cities = q.scalars().all()
    rows = [[InlineKeyboardButton(text=c.name, callback_data=f"m:onboarding:city:{c.id}")] for c in cities][:100]
    kb = kb_inline(rows or [[InlineKeyboardButton(text="Нет городов", callback_data="noop")]])
    await state.set_state(Onboarding.city)
    await push_step_from_message(msg, state, "Выберите город:", kb)

@router.callback_query(Onboarding.city, F.data.startswith("m:onboarding:city:"))
async def onb_city(cb: CallbackQuery, state: FSMContext):
    city_id = int(cb.data.split(":")[-1])
    await state.update_data(city_id=city_id, district_ids=[])
    # Переходим к выбору районов (пагинация/поиск)
    await state.set_state(Onboarding.districts)
    # Отрисуем страницу 1
    await _render_districts_page(cb.message, state, city_id, page=1)
    await cb.answer()

# --- пагинация районов ---
@router.callback_query(Onboarding.districts, F.data.startswith("m:onb:dist_page:"))
async def onb_districts_page(cb: CallbackQuery, state: FSMContext):
    _, _, _, city_id, page = cb.data.split(":")
    await _render_districts_page(cb.message, state, int(city_id), int(page))
    await cb.answer()

# --- старт поиска районов ---
@router.callback_query(Onboarding.districts, F.data.startswith("m:onb:dist_search:"))
async def onb_districts_search_start(cb: CallbackQuery, state: FSMContext):
    city_id = int(cb.data.split(":")[-1])
    await state.update_data(dist_city_id=city_id, dist_search_q=None)
    await state.set_state(Onboarding.districts_search)
    await push_step_from_cb(cb, state, "Введите часть названия района (минимум 2 символа).")
    await cb.answer()

# --- обработка текста поиска ---
@router.message(Onboarding.districts_search)
async def onb_districts_search_text(msg: Message, state: FSMContext):
    q = (msg.text or "").strip()
    if len(q) < 2:
        await msg.answer("Слишком короткий запрос. Введите минимум 2 символа.")
        return
    data = await state.get_data()
    city_id = int(data["dist_city_id"])
    await state.update_data(dist_search_q=q)
    # Рендер результатов поиска в том же «слоте» (сообщении этапа)
    await _render_districts_search_result(msg, state, city_id, q)

# --- назад из поиска к страницам ---
@router.callback_query(Onboarding.districts_search, F.data.startswith("m:onb:dist_back:"))
async def onb_districts_search_back(cb: CallbackQuery, state: FSMContext):
    city_id = int(cb.data.split(":")[-1])
    await state.set_state(Onboarding.districts)
    await _render_districts_page(cb.message, state, city_id, page=1)
    await cb.answer()

# --- toggles (и в поиске, и в страницах) ---
@router.callback_query(StateFilter(Onboarding.districts, Onboarding.districts_search), F.data.startswith("m:onb:dist_tog:"))
async def onb_district_toggle(cb: CallbackQuery, state: FSMContext):
    _, _, _, did, city_id, tail = cb.data.split(":")
    d_id = int(did)
    data = await state.get_data()
    selected = set(data.get("district_ids", []))
    if d_id in selected:
        selected.remove(d_id)
    else:
        selected.add(d_id)
    await state.update_data(district_ids=list(sorted(selected)))
    # Перерендер
    if tail == "S":
        q = (await state.get_data()).get("dist_search_q", "") or ""
        await _render_districts_search_result(cb.message, state, int(city_id), q)
    else:
        await _render_districts_page(cb.message, state, int(city_id), int(tail))
    await cb.answer("✓" if d_id in selected else "✗")

@router.callback_query(StateFilter(Onboarding.districts, Onboarding.districts_search), F.data == "m:onboarding:districts_done")
async def onb_districts_done(cb: CallbackQuery, state: FSMContext):
    await state.set_state(Onboarding.vehicle)
    await push_step_from_cb(cb, state, "Есть автомобиль?", kb_yes_no("m:onboarding:vehicle_yes", "m:onboarding:vehicle_no"))
    await cb.answer()

# === Автомобиль (без госномера, по вашему комментарию) ===
@router.callback_query(Onboarding.vehicle, F.data == "m:onboarding:vehicle_yes")
async def onb_vehicle_yes(cb: CallbackQuery, state: FSMContext):
    await state.update_data(has_vehicle=True)
    await state.set_state(Onboarding.skills)
    await ask_skills(cb.message, state)
    await cb.answer()

@router.callback_query(Onboarding.vehicle, F.data == "m:onboarding:vehicle_no")
async def onb_vehicle_no(cb: CallbackQuery, state: FSMContext):
    await state.update_data(has_vehicle=False)
    await state.set_state(Onboarding.skills)
    await ask_skills(cb.message, state)
    await cb.answer()

# ======================= Skills (галочки + перерендер) =======================
async def ask_skills(target_msg: Message, state: FSMContext):
    async with SessionLocal() as session:
        q = await session.execute(select(m.skills).where(m.skills.is_active == True).order_by(m.skills.name))
        slist = q.scalars().all()

    data = await state.get_data()
    selected = set(data.get("skill_ids", []))

    rows = [[InlineKeyboardButton(text=("✅ " if s.id in selected else "◻️ ") + s.name,
                                  callback_data=f"m:onboarding:skill:{s.id}")]
            for s in slist][:100]
    rows.append([InlineKeyboardButton(text="Готово", callback_data="m:onboarding:skills_done")])
    kb = kb_inline(rows)

    # это новый шаг — удалим прошлый
    await push_step_from_message(target_msg, state, "Выберите навыки (можно несколько):", kb)

@router.callback_query(Onboarding.skills, F.data.startswith("m:onboarding:skill:"))
async def onb_skill_toggle(cb: CallbackQuery, state: FSMContext):
    s_id = int(cb.data.split(":")[-1])
    data = await state.get_data()
    selected = set(data.get("skill_ids", []))
    if s_id in selected:
        selected.remove(s_id)
    else:
        selected.add(s_id)
    await state.update_data(skill_ids=list(sorted(selected)))

    # Перерендерим клавиатуру навыков с галочками
    async with SessionLocal() as session:
        q = await session.execute(select(m.skills).where(m.skills.is_active == True).order_by(m.skills.name))
        slist = q.scalars().all()

    rows = [[InlineKeyboardButton(text=("✅ " if s.id in selected else "◻️ ") + s.name,
                                  callback_data=f"m:onboarding:skill:{s.id}")]
            for s in slist][:100]
    rows.append([InlineKeyboardButton(text="Готово", callback_data="m:onboarding:skills_done")])
    try:
        await cb.message.edit_reply_markup(reply_markup=kb_inline(rows))
    except TelegramBadRequest:
        pass
    await cb.answer("✓" if s_id in selected else "✗")

@router.callback_query(Onboarding.skills, F.data == "m:onboarding:skills_done")
async def onb_skills_done(cb: CallbackQuery, state: FSMContext):
    await state.set_state(Onboarding.passport)
    await push_step_from_cb(cb, state, "Пришлите фото/скан паспорта.")
    await cb.answer()

@router.message(Onboarding.passport, F.content_type.in_({ContentType.PHOTO, ContentType.DOCUMENT}))
async def onb_passport(msg: Message, state: FSMContext):
    file_id = (msg.photo[-1].file_id if msg.photo else msg.document.file_id)
    await state.update_data(passport_file_id=file_id)
    await state.set_state(Onboarding.selfie)
    await push_step_from_message(msg, state, "Пришлите селфи с паспортом (фото).")

@router.message(Onboarding.selfie, F.content_type == ContentType.PHOTO)
async def onb_selfie(msg: Message, state: FSMContext):
    await state.update_data(selfie_file_id=msg.photo[-1].file_id)
    await state.set_state(Onboarding.payout_method)
    kb = kb_inline([
        [InlineKeyboardButton(text="Карта", callback_data="m:onboarding:payout:CARD")],
        [InlineKeyboardButton(text="СБП", callback_data="m:onboarding:payout:SBP")],
        [InlineKeyboardButton(text="ЮMoney", callback_data="m:onboarding:payout:YOOMONEY")],
        [InlineKeyboardButton(text="Банк (ИП/ООО)", callback_data="m:onboarding:payout:BANK_ACCOUNT")],
    ])
    await push_step_from_message(msg, state, "Выберите способ выплат:", kb)

@router.callback_query(Onboarding.payout_method, F.data.startswith("m:onboarding:payout:"))
async def onb_payout_method(cb: CallbackQuery, state: FSMContext):
    method = cb.data.split(":")[-1]
    await state.update_data(payout_method=method)
    await state.set_state(Onboarding.payout_requisites)
    prompt = {
        "CARD": "Укажите номер карты (16–19 цифр).",
        "SBP": "Укажите телефон для СБП (+7...).",
        "YOOMONEY": "Укажите email ЮMoney или номер кошелька (11–20 цифр).",
        "BANK_ACCOUNT": "Укажите ИНН (10/12), БИК (9), счёт (20). Через пробел.",
    }[method]
    await push_step_from_cb(cb, state, prompt)
    await cb.answer()

@router.message(Onboarding.payout_requisites)
async def onb_requisites(msg: Message, state: FSMContext):
    data = await state.get_data()
    method = data["payout_method"]
    ok = False
    if method == "CARD":
        ok = bool(re.fullmatch(r"^\d{16,19}$", msg.text or ""))
    elif method == "SBP":
        ok = bool(re.fullmatch(r"^\+\d{10,15}$", msg.text or ""))
    elif method == "YOOMONEY":
        ok = bool(re.fullmatch(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", msg.text or "")) or bool(re.fullmatch(r"^\d{11,20}$", msg.text or ""))
    elif method == "BANK_ACCOUNT":
        parts = (msg.text or "").split()
        if len(parts) == 3:
            inn, bik, acc = parts
            ok = bool(re.fullmatch(r"^(\d{10}|\d{12})$", inn)) and bool(re.fullmatch(r"^\d{9}$", bik)) and bool(re.fullmatch(r"^\d{20}$", acc))
    if not ok:
        await msg.answer("Реквизиты не распознаны. Проверьте формат.")
        return
    await state.update_data(payout_requisites=msg.text)
    await state.set_state(Onboarding.home_geo)
    kb = kb_inline([
        [InlineKeyboardButton(text="📍 Отправить геопозицию", callback_data="m:onboarding:home_geo_share")],
        [InlineKeyboardButton(text="Пропустить", callback_data="m:onboarding:home_geo_skip")],
    ])
    await push_step_from_message(msg, state, "Добавить домашнюю геолокацию? (опционально)", kb)

@router.callback_query(Onboarding.home_geo, F.data == "m:onboarding:home_geo_share")
async def onb_geo_share(cb: CallbackQuery, state: FSMContext):
    await push_step_from_cb(cb, state, "Пришлите координаты в формате «55.75580, 37.61730» или отправьте геолокацию.")
    await cb.answer()

@router.message(Onboarding.home_geo)
async def onb_home_geo_text(msg: Message, state: FSMContext):
    txt = (msg.text or "").strip()
    if not re.fullmatch(r"^-?\d{1,2}\.\d{5,8},\s*-?\d{1,3}\.\d{5,8}$", txt):
        await msg.answer("Формат: 55.75580, 37.61730. Или нажмите «Пропустить».")
        return
    lat_str, lon_str = [p.strip() for p in txt.split(",")]
    await state.update_data(home_lat=float(lat_str), home_lon=float(lon_str))
    await onb_summary(msg, state)

@router.callback_query(Onboarding.home_geo, F.data == "m:onboarding:home_geo_skip")
async def onb_home_geo_skip(cb: CallbackQuery, state: FSMContext):
    await onb_summary(cb.message, state)
    await cb.answer()

async def onb_summary(msg: Message, state: FSMContext):
    data = await state.get_data()
    lines = [
        "<b>Проверьте данные:</b>",
        f"ФИО: {data.get('full_name')}",
        f"Телефон: {data.get('phone')}",
        f"Город ID: {data.get('city_id')}",
        f"Районы: {', '.join(map(str, data.get('district_ids', []))) or '—'}",
        f"Автомобиль: {'да' if data.get('has_vehicle') else 'нет'}",
        f"Навыки: {', '.join(map(str, data.get('skill_ids', []))) or '—'}",
        f"Способ выплат: {data.get('payout_method')}",
        f"Реквизиты: {data.get('payout_requisites')}",
        f"Дом.гео: {data.get('home_lat')}, {data.get('home_lon')}" if data.get('home_lat') else "Дом.гео: —",
    ]
    kb = kb_inline([[InlineKeyboardButton(text="📨 Отправить на модерацию", callback_data="m:onboarding:confirm")]])
    await state.set_state(Onboarding.confirm)
    await push_step_from_message(msg, state, "\n".join(lines), kb)

@router.callback_query(Onboarding.confirm, F.data == "m:onboarding:confirm")
async def onb_submit(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    async with SessionLocal() as session:
        mst = await ensure_master(session, cb.from_user.id)
        mst.full_name = data.get("full_name") or mst.full_name
        mst.phone = data.get("phone")
        mst.city_id = data.get("city_id")
        if hasattr(mst, "pdn_accepted_at"):
            mst.pdn_accepted_at = now()
        if data.get("has_vehicle") is not None:
            mst.has_vehicle = bool(data.get("has_vehicle"))
            mst.vehicle_plate = None  # больше не собираем
        if hasattr(mst, "payout_method"):
            mst.payout_method = data.get("payout_method")
            mst.payout_data = {"raw": data.get("payout_requisites")}
        if data.get("home_lat") is not None:
            mst.home_latitude = data["home_lat"]
            mst.home_longitude = data["home_lon"]

        # master_districts
        await session.execute(text("DELETE FROM master_districts WHERE master_id = :mid").bindparams(mid=mst.id))
        for did in set(data.get("district_ids", [])):
            await session.execute(text("INSERT INTO master_districts(master_id, district_id) VALUES (:mid, :did) ON CONFLICT DO NOTHING").bindparams(mid=mst.id, did=did))

        # master_skills
        await session.execute(text("DELETE FROM master_skills WHERE master_id = :mid").bindparams(mid=mst.id))
        for sid in set(data.get("skill_ids", [])):
            await session.execute(text("INSERT INTO master_skills(master_id, skill_id) VALUES (:mid, :sid) ON CONFLICT DO NOTHING").bindparams(mid=mst.id, sid=sid))

        # attachments: паспорт/селфи
        if data.get("passport_file_id"):
            session.add(m.attachments(
                entity_type=m.AttachmentEntity.MASTER, entity_id=mst.id,
                file_type=m.AttachmentFileType.PHOTO, file_id=data["passport_file_id"],
                uploaded_by_master_id=mst.id,
            ))
        if data.get("selfie_file_id"):
            session.add(m.attachments(
                entity_type=m.AttachmentEntity.MASTER, entity_id=mst.id,
                file_type=m.AttachmentFileType.PHOTO, file_id=data["selfie_file_id"],
                uploaded_by_master_id=mst.id,
            ))

        if hasattr(mst, "moderation_status"):
            mst.moderation_status = "PENDING"
        mst.is_active = False
        await session.commit()

    # Удаляем все сообщения онбординга и чистим состояние
    await clear_onboarding_ui(cb.message.bot, state, cb.message.chat.id)
    await state.clear()
    await cb.message.answer("Профиль отправлен на модерацию. Уведомим о результате.")
    await cb.answer()

# ======================= Shift/Break (без изменений логики) =======================
@router.callback_query(F.data == "m:shift:on")
async def shift_on(cb: CallbackQuery):
    async with SessionLocal() as session:
        mst = await ensure_master(session, cb.from_user.id)
        if mst.is_blocked:
            await cb.answer("Профиль заблокирован из‑за просроченных комиссий.", show_alert=True)
            return
        if hasattr(mst, "moderation_status") and str(mst.moderation_status) != "APPROVED":
            await cb.answer("Профиль не одобрен модерацией.", show_alert=True)
            return
        if hasattr(mst, "shift_status"):
            mst.shift_status = "SHIFT_ON"
            await session.commit()
            await cb.message.answer("Смена включена. Вы участвуете в распределении.")
        else:
            await cb.message.answer("Смена недоступна до применения миграции 0002.")
    await cb.answer()

@router.callback_query(F.data == "m:shift:off")
async def shift_off(cb: CallbackQuery):
    async with SessionLocal() as session:
        mst = await ensure_master(session, cb.from_user.id)
        if hasattr(mst, "shift_status"):
            mst.shift_status = "SHIFT_OFF"
            await session.commit()
            await cb.message.answer("Смена выключена.")
        else:
            await cb.message.answer("Смена недоступна до применения миграции 0002.")
    await cb.answer()

@router.callback_query(F.data == "m:break:start")
async def break_start(cb: CallbackQuery):
    async with SessionLocal() as session:
        mst = await ensure_master(session, cb.from_user.id)
        if not hasattr(mst, "shift_status") or str(mst.shift_status) != "SHIFT_ON":
            await cb.answer("Перерыв доступен только при включённой смене.", show_alert=True)
            return
        mst.shift_status = "BREAK"
        if hasattr(mst, "break_until"):
            mst.break_until = now() + timedelta(hours=2)
        await session.commit()
        await cb.message.answer("Перерыв 2 часа начат. Вы исключены из распределения.")
    await cb.answer()

@router.callback_query(F.data == "m:break:stop")
async def break_stop(cb: CallbackQuery):
    async with SessionLocal() as session:
        mst = await ensure_master(session, cb.from_user.id)
        if hasattr(mst, "shift_status") and str(mst.shift_status) == "BREAK":
            mst.shift_status = "SHIFT_ON"
            mst.break_until = None
            await session.commit()
            await cb.message.answer("Перерыв завершён. Вы вернулись на смену.")
        else:
            await cb.message.answer("Смена недоступна до применения миграции 0002.")
    await cb.answer()

# ======================= Offers / Assign (без изменений) =======================
@router.callback_query(F.data.startswith("m:offer:accept:"))
async def offer_accept(cb: CallbackQuery):
    order_id = int(cb.data.split(":")[-1])
    async with SessionLocal() as session:
        mst = await ensure_master(session, cb.from_user.id)
        if mst.is_blocked:
            await cb.answer("Нельзя принять: профиль заблокирован.", show_alert=True)
            return
        limit = await max_active_orders(session)
        active = await count_active_orders(session, mst.id)
        if active >= limit:
            await cb.answer("Достигнут лимит активных заказов.", show_alert=True)
            return
        upd = await session.execute(
            update(m.orders)
            .where(
                and_(
                    m.orders.id == order_id,
                    m.orders.assigned_master_id.is_(None),
                    m.orders.status.in_((m.OrderStatus.CREATED, m.OrderStatus.DISTRIBUTION))
                )
            )
            .values(assigned_master_id=mst.id, status=m.OrderStatus.ASSIGNED, updated_at=func.now(), version=m.orders.version + 1)
            .execution_options(synchronize_session=False)
            .returning(m.orders.id)
        )
        row = upd.first()
        if not row:
            await cb.answer("Увы, заказ уже забрали.", show_alert=True)
            return
        await session.execute(
            update(m.offers)
            .where(and_(m.offers.order_id == order_id, m.offers.master_id == mst.id, m.offers.state == m.OfferState.SENT))
            .values(state=m.OfferState.ACCEPTED, responded_at=func.now())
        )
        await session.commit()
    await cb.message.answer(
        f"Заказ #{order_id} закреплён за вами. Нажмите «Я на месте» по прибытии.",
        reply_markup=kb_inline([[InlineKeyboardButton(text="📍 Я на месте", callback_data=f"m:order:arrived:{order_id}")]])
    )
    await cb.answer()

@router.callback_query(F.data.startswith("m:offer:decline:"))
async def offer_decline(cb: CallbackQuery):
    order_id = int(cb.data.split(":")[-1])
    async with SessionLocal() as session:
        mst = await ensure_master(session, cb.from_user.id)
        await session.execute(
            update(m.offers)
            .where(and_(m.offers.order_id == order_id, m.offers.master_id == mst.id))
            .values(state=m.OfferState.DECLINED, responded_at=func.now())
        )
        await session.commit()
    await cb.message.answer("Вы отказались от оффера.")
    await cb.answer()

# ======================= Order flow (без изменений) =======================
@router.callback_query(F.data.startswith("m:order:arrived:"))
async def order_arrived(cb: CallbackQuery):
    order_id = int(cb.data.split(":")[-1])
    async with SessionLocal() as session:
        await session.execute(
            update(m.orders)
            .where(m.orders.id == order_id)
            .values(status=m.OrderStatus.IN_PROGRESS, updated_at=func.now(), version=m.orders.version + 1)
        )
        await session.commit()
    await cb.message.answer(
        f"Заказ #{order_id}: статус IN_PROGRESS.\nНажмите «Завершить», когда работа выполнена.",
        reply_markup=kb_inline([[InlineKeyboardButton(text="✅ Завершить", callback_data=f"m:order:finish:{order_id}")]])
    )
    await cb.answer()

@router.callback_query(F.data.startswith("m:order:finish:"))
async def order_finish(cb: CallbackQuery, state: FSMContext):
    order_id = int(cb.data.split(":")[-1])
    await state.update_data(order_id=order_id)
    await cb.message.answer("Укажите сумму к получению (пример: 2490.00).")
    await state.set_state(State("closure_sum"))
    await cb.answer()

@router.message(State("closure_sum"))
async def closure_sum(msg: Message, state: FSMContext):
    amount = normalize_money(msg.text or "")
    if amount is None:
        await msg.answer("Сумма должна быть больше нуля (например, 2490.00).")
        return
    await state.update_data(sum=str(amount))
    await msg.answer("Приложите акт (фото или PDF).")
    await state.set_state(State("closure_act"))

@router.message(State("closure_act"), F.content_type.in_({ContentType.PHOTO, ContentType.DOCUMENT}))
async def closure_act(msg: Message, state: FSMContext):
    data = await state.get_data()
    order_id = int(data["order_id"])
    amount = Decimal(data["sum"])
    file_id = (msg.photo[-1].file_id if msg.photo else msg.document.file_id)

    async with SessionLocal() as session:
        q = await session.execute(select(m.orders.status, m.orders.assigned_master_id).where(m.orders.id == order_id))
        ord_status, master_id = q.one()
        is_warranty = (str(ord_status) == "GUARANTEE")

        session.add(m.attachments(
            entity_type=m.AttachmentEntity.ORDER, entity_id=order_id,
            file_type=m.AttachmentFileType.PHOTO if msg.photo else m.AttachmentFileType.DOCUMENT,
            file_id=file_id,
        ))
        await session.execute(
            update(m.orders)
            .where(m.orders.id == order_id)
            .values(status=m.OrderStatus.PAYMENT, total_price=amount, updated_at=func.now(), version=m.orders.version + 1)
        )
        if is_warranty:
            # как было
            from field_service.services.commission_service import create_commission_for_order\n        order = await session.get(m.orders, order_id)\n        master = await session.get(m.masters, master_id)\n        await create_commission_for_order(session, order, master)\n)
            changed = False
            for mst in q.scalars():
                mst.shift_status = "SHIFT_ON"; mst.break_until = None; changed = True
            if changed:
                await session.commit()
        await asyncio.sleep(30)

async def watchdog_commissions_block(bot: Bot):
    while True:
        async with SessionLocal() as session:
            q = await session.execute(
                select(m.commissions.master_id).where(
                    and_(m.commissions.status == m.CommissionStatus.WAIT_PAY, m.commissions.due_at < func.now(), m.commissions.blocked_applied == False)
                )
            )
            mids = [row[0] for row in q.all()]
            if mids:
                await session.execute(
                    update(m.masters)
                    .where(m.masters.id.in_(mids))
                    .values(is_blocked=True, blocked_at=func.now(), blocked_reason="Просрочка оплаты комиссии > 3 часа")
                )
                await session.execute(
                    update(m.commissions)
                    .where(and_(m.commissions.master_id.in_(mids), m.commissions.status == m.CommissionStatus.WAIT_PAY))
                    .values(status=m.CommissionStatus.OVERDUE, blocked_applied=True, blocked_at=func.now())
                )
                await session.commit()
        await asyncio.sleep(60)

@router.startup()
async def on_startup(bot: Bot):
    asyncio.create_task(watchdog_breaks(bot))
    asyncio.create_task(watchdog_commissions_block(bot))


