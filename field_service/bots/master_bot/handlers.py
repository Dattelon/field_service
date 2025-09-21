from __future__ import annotations
import asyncio
import math
import re
import html
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
from sqlalchemy import select, update, insert, and_, func, text
from sqlalchemy.ext.asyncio import AsyncSession
from field_service.config import settings
from field_service.db import models as m
from field_service.db.session import SessionLocal
from field_service.services.commission_service import create_commission_for_order
from field_service.services import settings_service

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

class FinanceUpload(StatesGroup):
    check = State()

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
    active_statuses = (m.OrderStatus.ASSIGNED, m.OrderStatus.EN_ROUTE, m.OrderStatus.WORKING, m.OrderStatus.PAYMENT)
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
OFFERS_PAGE_SIZE = 5
def extract_target_message(event: Message | CallbackQuery) -> Message:
    return event if isinstance(event, Message) else event.message
def format_timeslot_values(slot_label, start, end) -> str:
    if slot_label:
        return slot_label
    if start and end:
        return f"{start.strftime('%H:%M')} - {end.strftime('%H:%M')}"
    return "Без слота"
def format_address(city: str | None, district: str | None) -> str:
    if city and district:
        return f"{city} / {district}"
    return city or district or ""
def escape(text: str | None) -> str:
    return html.escape(text or "")
async def load_master_offers(session: AsyncSession, master_id: int):
    stmt = (
        select(
            m.offers.order_id,
            m.offers.sent_at,
            m.offers.state,
            m.orders.description,
            m.orders.category,
            m.orders.scheduled_date,
            m.orders.time_slot_start,
            m.orders.time_slot_end,
            m.orders.slot_label,
            m.cities.name.label("city_name"),
            m.districts.name.label("district_name"),
        )
        .join(m.orders, m.orders.id == m.offers.order_id)
        .join(m.cities, m.cities.id == m.orders.city_id)
        .outerjoin(m.districts, m.districts.id == m.orders.district_id)
        .where(
            (m.offers.master_id == master_id)
            & (m.offers.state.in_((m.OfferState.SENT, m.OfferState.VIEWED)))
        )
        .order_by(m.offers.sent_at.desc(), m.offers.order_id.desc())
    )
    rows = await session.execute(stmt)
    return rows.all()
async def load_offer_detail(session: AsyncSession, master_id: int, order_id: int):
    stmt = (
        select(
            m.orders,
            m.cities.name.label("city_name"),
            m.districts.name.label("district_name"),
        )
        .join(m.cities, m.cities.id == m.orders.city_id)
        .outerjoin(m.districts, m.districts.id == m.orders.district_id)
        .join(m.offers, (m.offers.order_id == m.orders.id) & (m.offers.master_id == master_id))
        .where(m.orders.id == order_id)
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.first()
async def render_new_offers(event: Message | CallbackQuery, master: m.masters, page: int = 1) -> None:
    async with SessionLocal() as session:
        rows = await load_master_offers(session, master.id)
    total = len(rows)
    per_page = OFFERS_PAGE_SIZE
    pages = max(1, math.ceil(total / per_page))
    page = min(max(1, page), pages)
    start = (page - 1) * per_page
    current = rows[start : start + per_page]
    if total == 0:
        text_out = "Новых заявок нет."
        markup = kb_inline([[InlineKeyboardButton(text="⬅️ Меню", callback_data="m:menu")]])
    else:
        lines: list[str] = ["<b>Новые заявки</b>"]
        buttons: list[list[InlineKeyboardButton]] = []
        for row in current:
            order_id = row.order_id
            addr = format_address(row.city_name, row.district_name)
            cat = row.category or "—"
            slot = format_timeslot_values(row.slot_label, row.time_slot_start, row.time_slot_end)
            summary = f"#{order_id}"
            if addr:
                summary += f" • {escape(addr)}"
            summary += f" • {escape(cat)}"
            lines.append(summary)
            if slot:
                lines.append(f"Слот: {escape(slot)}")
            lines.append("")
            buttons.append([
                InlineKeyboardButton(
                    text=f"Открыть #{order_id}",
                    callback_data=f"m:new:card:{order_id}:{page}",
                )
            ])
        nav: list[InlineKeyboardButton] = []
        if page > 1:
            nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"m:new:{page-1}"))
        nav.append(InlineKeyboardButton(text=f"{page}/{pages}", callback_data="noop"))
        if page < pages:
            nav.append(InlineKeyboardButton(text="➡️", callback_data=f"m:new:{page+1}"))
        if nav:
            buttons.append(nav)
        buttons.append([InlineKeyboardButton(text="⬅️ Меню", callback_data="m:menu")])
    text_out = "\n".join(line for line in lines if line)
    markup = kb_inline(buttons)
    target = extract_target_message(event)
    try:
        if isinstance(event, CallbackQuery):
            await event.message.edit_text(text_out, reply_markup=markup, parse_mode=ParseMode.HTML)
        else:
            await target.answer(text_out, reply_markup=markup, parse_mode=ParseMode.HTML)
    except TelegramBadRequest:
        await target.answer(text_out, reply_markup=markup, parse_mode=ParseMode.HTML)

async def render_offer_card(cb: CallbackQuery, master: m.masters, order_id: int, page: int) -> None:
    async with SessionLocal() as session:
        detail = await load_offer_detail(session, master.id, order_id)
    if not detail:
        await cb.answer("Оффер не найден", show_alert=True)
        await render_new_offers(cb, master, page=page)
        return
    order, city_name, district_name = detail
    slot = format_timeslot_values(order.slot_label, order.time_slot_start, order.time_slot_end)
    lines = [
        f"<b>Заявка #{order.id}</b>",
    ]
    addr = format_address(city_name, district_name)
    if addr:
        lines.append(escape(addr))
    lines.append(f"Категория: {escape(order.category)}" if order.category else "Категория: —")
    if slot:
        if order.scheduled_date:
            lines.append(f"Слот: {order.scheduled_date.strftime('%d.%m')} {escape(slot)}")
        else:
            lines.append(f"Слот: {escape(slot)}")
    if order.description:
        lines.append("")
        lines.append(escape(order.description))
    buttons = [
        [InlineKeyboardButton(text="✅ Взять", callback_data=f"m:new:acc:{order.id}:{page}")],
        [InlineKeyboardButton(text="❌ Отказаться", callback_data=f"m:new:dec:{order.id}:{page}")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"m:new:{page}")],
    ]
    text_out = "\n".join(line for line in lines if line)
    try:
        await cb.message.edit_text(text_out, reply_markup=kb_inline(buttons), parse_mode=ParseMode.HTML)
    except TelegramBadRequest:
        await cb.message.answer(text_out, reply_markup=kb_inline(buttons), parse_mode=ParseMode.HTML)

ACTIVE_ORDER_STATUSES = (
    m.OrderStatus.ASSIGNED,
    m.OrderStatus.EN_ROUTE,
    m.OrderStatus.WORKING,
    m.OrderStatus.PAYMENT,
)
def format_phone(phone: Optional[str]) -> str:
    if not phone:
        return "—"
    raw = phone.strip()
    if raw.startswith('+7') and len(raw) == 12:
        return f"+7 {raw[2:5]} {raw[5:8]} {raw[8:10]} {raw[10:12]}"
    return raw
async def load_active_order(
    session: AsyncSession, master_id: int, order_id: Optional[int] = None
):
    stmt = (
        select(
            m.orders,
            m.cities.name.label("city_name"),
            m.districts.name.label("district_name"),
            m.streets.name.label("street_name"),
        )
        .join(m.cities, m.cities.id == m.orders.city_id)
        .outerjoin(m.districts, m.districts.id == m.orders.district_id)
        .outerjoin(m.streets, m.streets.id == m.orders.street_id)
        .where(
            (m.orders.assigned_master_id == master_id)
            & (m.orders.status.in_(ACTIVE_ORDER_STATUSES))
        )
        .order_by(m.orders.updated_at.desc(), m.orders.id.desc())
    )
    if order_id is not None:
        stmt = stmt.where(m.orders.id == order_id)
    stmt = stmt.limit(1)
    result = await session.execute(stmt)
    return result.first()
async def render_active_order(
    event: Message | CallbackQuery, master_id: int, *, order_id: Optional[int] = None
) -> None:
    async with SessionLocal() as session:
        row = await load_active_order(session, master_id, order_id)
    target = extract_target_message(event)
    if not row:
        markup = kb_inline([[InlineKeyboardButton(text="⬅️ Меню", callback_data="m:menu")]])
        await target.answer("Активных заказов нет.", reply_markup=markup)
        return
    order, city_name, district_name, street_name = row
    lines: list[str] = [f"<b>Заказ #{order.id}</b>"]
    lines.append(f"Статус: <b>{order.status.value}</b>")
    address_parts: list[str] = []
    if city_name:
        address_parts.append(city_name)
    if district_name:
        address_parts.append(district_name)
    street_parts: list[str] = []
    if street_name:
        street_parts.append(street_name)
    if order.house:
        street_parts.append(order.house)
    if order.apartment:
        street_parts.append(f"кв. {order.apartment}")
    if street_parts:
        address_parts.append(', '.join(street_parts))
    if address_parts:
        lines.append(f"Адрес: {escape(' / '.join(address_parts))}")
    slot = format_timeslot_values(order.slot_label, order.time_slot_start, order.time_slot_end)
    if slot:
        if order.scheduled_date:
            lines.append(
                f"Слот: {order.scheduled_date.strftime('%d.%m')} {escape(slot)}"
            )
        else:
            lines.append(f"Слот: {escape(slot)}")
    if order.client_name:
        lines.append(f"Клиент: {escape(order.client_name)}")
    if order.client_phone:
        lines.append(f"Телефон: {escape(format_phone(order.client_phone))}")
    if order.description:
        lines.append("")
        lines.append(escape(order.description))
    buttons: list[list[InlineKeyboardButton]] = []
    if order.status == m.OrderStatus.ASSIGNED:
        buttons.append([
            InlineKeyboardButton(text="🚗 В пути", callback_data=f"m:act:enr:{order.id}"),
        ])
    elif order.status == m.OrderStatus.EN_ROUTE:
        buttons.append([
            InlineKeyboardButton(text="🛠 Работаю", callback_data=f"m:act:wrk:{order.id}"),
        ])
    elif order.status == m.OrderStatus.WORKING:
        buttons.append([
            InlineKeyboardButton(text="✅ Закрыть", callback_data=f"m:act:cls:{order.id}"),
        ])
    buttons.append([InlineKeyboardButton(text="⬅️ Меню", callback_data="m:menu")])
    text_out = "\n".join(line for line in lines if line)
    markup = kb_inline(buttons)
    try:
        if isinstance(event, CallbackQuery):
            await event.message.edit_text(text_out, reply_markup=markup, parse_mode=ParseMode.HTML)
        else:
            await target.answer(text_out, reply_markup=markup, parse_mode=ParseMode.HTML)
    except TelegramBadRequest:
        await target.answer(text_out, reply_markup=markup, parse_mode=ParseMode.HTML)

COMMISSIONS_PAGE_SIZE = 5

FIN_MODES = {
    "aw": ("Ожидают оплаты", (m.CommissionStatus.WAIT_PAY, m.CommissionStatus.REPORTED)),
    "pd": ("Оплаченные", (m.CommissionStatus.APPROVED,)),
    "ov": ("Просроченные", (m.CommissionStatus.OVERDUE,)),
}

FINANCE_MODE_ORDER = ("aw", "pd", "ov")

def format_pay_snapshot(snapshot: Optional[dict]) -> str:
    if not snapshot:
        return "Реквизиты отсутствуют."
    lines: list[str] = []
    methods = snapshot.get("methods") if isinstance(snapshot, dict) else None
    if isinstance(methods, (list, tuple)):
        lines.append("Способы: " + ", ".join(methods))
    for key, value in snapshot.items():
        if key == "methods":
            continue
        if isinstance(value, dict):
            for sub_key, sub_value in value.items():
                lines.append(f"{key}.{sub_key}: {sub_value}")
        else:
            lines.append(f"{key}: {value}")
    return "\n".join(lines) if lines else "Реквизиты отсутствуют."


async def load_commissions(
    session: AsyncSession, master_id: int, statuses: tuple[m.CommissionStatus, ...]
):
    stmt = (
        select(m.commissions)
        .where(
            (m.commissions.master_id == master_id)
            & (m.commissions.status.in_(statuses))
        )
        .order_by(m.commissions.deadline_at.asc(), m.commissions.id.desc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def render_commission_list(
    event: Message | CallbackQuery,
    master_id: int,
    *,
    mode: str,
    page: int,
    state: FSMContext,
) -> None:
    title, statuses = FIN_MODES.get(mode, FIN_MODES["aw"])
    async with SessionLocal() as session:
        rows = await load_commissions(session, master_id, statuses)
    await state.update_data(fin_ctx={"mode": mode, "page": page})
    total = len(rows)
    per_page = COMMISSIONS_PAGE_SIZE
    pages = max(1, math.ceil(total / per_page))
    page = min(max(1, page), pages)
    start = (page - 1) * per_page
    current = rows[start : start + per_page]

    mode_row: list[InlineKeyboardButton] = []
    for code in FINANCE_MODE_ORDER:
        caption, _ = FIN_MODES[code]
        label = f"• {caption}" if code == mode else caption
        mode_row.append(
            InlineKeyboardButton(text=label, callback_data=f"m:fin:{code}:1")
        )

    buttons: list[list[InlineKeyboardButton]] = [mode_row]

    if total == 0:
        text_out = f"<b>{escape(title)}</b>\nЗаписей нет."
        buttons.append([InlineKeyboardButton(text="⬅️ Меню", callback_data="m:menu")])
    else:
        lines = [f"<b>{escape(title)}</b>"]
        for commission in current:
            summary = f"#{commission.id} • {commission.amount:.2f} ₽"
            if commission.deadline_at:
                summary += f" • до {commission.deadline_at.strftime('%d.%m %H:%M')}"
            lines.append(summary)
            lines.append(f"Статус: {commission.status.value}")
            lines.append("")
            buttons.append([
                InlineKeyboardButton(
                    text=f"Открыть #{commission.id}",
                    callback_data=f"m:fin:cm:{commission.id}",
                )
            ])
        nav: list[InlineKeyboardButton] = []
        if page > 1:
            nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"m:fin:{mode}:{page-1}"))
        nav.append(InlineKeyboardButton(text=f"{page}/{pages}", callback_data="noop"))
        if page < pages:
            nav.append(InlineKeyboardButton(text="➡️", callback_data=f"m:fin:{mode}:{page+1}"))
        if nav:
            buttons.append(nav)
        buttons.append([InlineKeyboardButton(text="⬅️ Меню", callback_data="m:menu")])
        text_out = "\n".join(line for line in lines if line)

    target = extract_target_message(event)
    markup = kb_inline(buttons)
    try:
        if isinstance(event, CallbackQuery):
            await event.message.edit_text(text_out, reply_markup=markup, parse_mode=ParseMode.HTML)
        else:
            await target.answer(text_out, reply_markup=markup, parse_mode=ParseMode.HTML)
    except TelegramBadRequest:
        await target.answer(text_out, reply_markup=markup, parse_mode=ParseMode.HTML)


async def render_commission_card(
    event: Message | CallbackQuery,
    master_id: int,
    commission_id: int,
    state: FSMContext,
) -> None:
    async with SessionLocal() as session:
        stmt = (
            select(
                m.commissions,
                m.orders.order_type,
                m.orders.id,
                m.orders.total_price,
            )
            .join(m.orders, m.orders.id == m.commissions.order_id)
            .where(
                (m.commissions.master_id == master_id)
                & (m.commissions.id == commission_id)
            )
            .limit(1)
        )
        row = await session.execute(stmt)
    result = row.first()
    target = extract_target_message(event)
    if not result:
        await target.answer("Комиссия не найдена.")
        return
    commission, order_type, order_id, order_total = result
    lines: list[str] = [f"<b>Комиссия #{commission.id}</b>"]
    order_type_value = order_type.value if order_type else ""
    if order_type_value:
        lines.append(f"Заказ #{order_id} • {order_type_value}")
    else:
        lines.append(f"Заказ #{order_id}")
    lines.append(f"Сумма комиссии: {commission.amount:.2f} ₽")
    rate_raw = commission.rate or getattr(commission, "percent", None)
    if rate_raw is not None:
        rate_dec = Decimal(rate_raw)
        rate_percent = rate_dec * 100 if rate_dec <= 1 else rate_dec
        rate_str = f"{rate_percent:.2f}".rstrip('0').rstrip('.')
        lines.append(f"Ставка: {rate_str}%")
    if commission.deadline_at:
        lines.append(f"Дедлайн: {commission.deadline_at.strftime('%d.%m %H:%M')}")
    lines.append(f"Статус: {commission.status.value}")
    if commission.paid_reported_at:
        lines.append(f"Отчёт об оплате: {commission.paid_reported_at.strftime('%d.%m %H:%M')}")
    if commission.paid_approved_at:
        lines.append(f"Подтверждено: {commission.paid_approved_at.strftime('%d.%m %H:%M')}")
    if order_total:
        lines.append(f"Сумма заказа: {order_total:.2f} ₽")
    ctx = (await state.get_data()).get("fin_ctx", {"mode": "aw", "page": 1})
    buttons: list[list[InlineKeyboardButton]] = []
    snapshot = commission.pay_to_snapshot or {}
    if snapshot:
        buttons.append([
            InlineKeyboardButton(text="💳 Реквизиты", callback_data=f"m:fin:cm:pt:{commission.id}")
        ])
    buttons.append([
        InlineKeyboardButton(text="📎 Отправить чек", callback_data=f"m:fin:cm:chk:{commission.id}")
    ])
    if commission.status in {m.CommissionStatus.WAIT_PAY, m.CommissionStatus.REPORTED}:
        buttons.append([
            InlineKeyboardButton(text="✅ Я оплатил", callback_data=f"m:fin:cm:ip:{commission.id}")
        ])
    buttons.append([
        InlineKeyboardButton(text="⬅️ Назад", callback_data=f"m:fin:{ctx.get('mode', 'aw')}:{ctx.get('page', 1)}")
    ])
    markup = kb_inline(buttons)
    text_out = "\n".join(lines)
    try:
        if isinstance(event, CallbackQuery):
            await event.message.edit_text(text_out, reply_markup=markup, parse_mode=ParseMode.HTML)
        else:
            await target.answer(text_out, reply_markup=markup, parse_mode=ParseMode.HTML)
    except TelegramBadRequest:
        await target.answer(text_out, reply_markup=markup, parse_mode=ParseMode.HTML)

# ======================= Districts: pagination & search =======================
PAGE_SIZE = 10


async def render_referral_dashboard(
    event: Message | CallbackQuery,
    *,
    tg_user_id: int,
) -> None:
    async with SessionLocal() as session:
        master = await ensure_master(session, tg_user_id)
        master_id = master.id
        referral_code = (master.referral_code or "").strip()
        result = await session.execute(
            select(
                m.referral_rewards.level,
                func.count(),
                func.sum(m.referral_rewards.amount),
            )
            .where(
                m.referral_rewards.referrer_id == master_id,
                m.referral_rewards.status != m.ReferralRewardStatus.CANCELED,
            )
            .group_by(m.referral_rewards.level)
        )
        rows = result.all()

    stats = {
        1: {"count": 0, "amount": Decimal("0")},
        2: {"count": 0, "amount": Decimal("0")},
    }
    for level, cnt, total in rows:
        try:
            level_idx = int(level or 0)
        except (TypeError, ValueError):
            continue
        bucket = stats.get(level_idx)
        if not bucket:
            continue
        bucket["count"] = int(cnt or 0)
        bucket["amount"] = Decimal(total) if total is not None else Decimal("0")

    total_amount = stats[1]["amount"] + stats[2]["amount"]
    lines: list[str] = ["<b>🤝 Реферальная программа</b>"]
    if referral_code:
        lines.append(f"Ваш код: <code>{escape(referral_code)}</code>")
    else:
        lines.append("Реферальный код пока не выдан.")
    lines.append("")
    for level in (1, 2):
        bucket = stats[level]
        lines.append(
            f"L{level}: {bucket['count']} начислений • {bucket['amount']:.2f} ₽"
        )
    lines.append("")
    lines.append(f"Всего начислено: <b>{total_amount:.2f} ₽</b>")

    text_out = "\n".join(lines)
    markup = kb_inline([[InlineKeyboardButton(text="⬅️ Меню", callback_data="m:menu")]])
    target = extract_target_message(event)
    try:
        if isinstance(event, CallbackQuery):
            await event.message.edit_text(text_out, reply_markup=markup, parse_mode=ParseMode.HTML)
        else:
            await target.answer(text_out, reply_markup=markup, parse_mode=ParseMode.HTML)
    except TelegramBadRequest:
        await target.answer(text_out, reply_markup=markup, parse_mode=ParseMode.HTML)


async def render_support_info(
    event: Message | CallbackQuery,
    *,
    tg_user_id: int,
) -> None:
    async with SessionLocal() as session:
        await ensure_master(session, tg_user_id)

    raw_values = await settings_service.get_values(["support_contact", "support_faq_url"])
    contact = (raw_values.get("support_contact", (None, None))[0] or "").strip()
    faq_url = (raw_values.get("support_faq_url", (None, None))[0] or "").strip()

    lines: list[str] = ["<b>📚 База знаний</b>", ""]
    if contact:
        lines.append(f"Поддержка: {escape(contact)}")
    else:
        lines.append("Поддержка: не указана.")

    if faq_url and faq_url != "-":
        if faq_url.lower().startswith(("http://", "https://", "tg://")):
            safe_url = html.escape(faq_url, quote=True)
            lines.append(f"FAQ: <a href=\"{safe_url}\">открыть</a>")
        else:
            lines.append(f"FAQ: {escape(faq_url)}")
    else:
        lines.append("FAQ: не указан.")

    text_out = "\n".join(lines)
    markup = kb_inline([[InlineKeyboardButton(text="⬅️ Меню", callback_data="m:menu")]])
    target = extract_target_message(event)
    try:
        if isinstance(event, CallbackQuery):
            await event.message.edit_text(text_out, reply_markup=markup, parse_mode=ParseMode.HTML)
        else:
            await target.answer(text_out, reply_markup=markup, parse_mode=ParseMode.HTML)
    except TelegramBadRequest:
        await target.answer(text_out, reply_markup=markup, parse_mode=ParseMode.HTML)


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
@router.callback_query(F.data == "m:act")
async def active_order_entry(cb: CallbackQuery) -> None:
    async with SessionLocal() as session:
        master = await ensure_master(session, cb.from_user.id)
        master_id = master.id
    await render_active_order(cb, master_id)
    await cb.answer()
@router.callback_query(F.data.startswith("m:act:card:"))
async def active_order_card(cb: CallbackQuery) -> None:
    parts = cb.data.split(":")
    try:
        order_id = int(parts[2])
    except (IndexError, ValueError):
        await cb.answer("Некорректный идентификатор", show_alert=True)
        return
    async with SessionLocal() as session:
        master = await ensure_master(session, cb.from_user.id)
        master_id = master.id
    await render_active_order(cb, master_id, order_id=order_id)
    await cb.answer()
@router.callback_query(F.data.startswith("m:act:enr:"))
async def active_set_enroute(cb: CallbackQuery) -> None:
    order_id = int(cb.data.split(":")[-1])
    master_id: int
    async with SessionLocal() as session:
        master = await ensure_master(session, cb.from_user.id)
        master_id = master.id
        result = await session.execute(
            update(m.orders)
            .where(
                and_(
                    m.orders.id == order_id,
                    m.orders.assigned_master_id == master_id,
                    m.orders.status == m.OrderStatus.ASSIGNED,
                )
            )
            .values(status=m.OrderStatus.EN_ROUTE, updated_at=func.now(), version=m.orders.version + 1)
            .returning(m.orders.id)
        )
        if not result.first():
            await cb.answer("Не удалось обновить статус.", show_alert=True)
            return
        await session.execute(
            insert(m.order_status_history).values(
                order_id=order_id,
                from_status=m.OrderStatus.ASSIGNED,
                to_status=m.OrderStatus.EN_ROUTE,
                changed_by_master_id=master_id,
                reason="master_en_route",
            )
        )
        await session.commit()
    await cb.answer("Статус обновлён на EN_ROUTE")
    await render_active_order(cb, master_id, order_id=order_id)
@router.callback_query(F.data.startswith("m:act:wrk:"))
async def active_set_working(cb: CallbackQuery) -> None:
    order_id = int(cb.data.split(":")[-1])
    master_id: int
    async with SessionLocal() as session:
        master = await ensure_master(session, cb.from_user.id)
        master_id = master.id
        result = await session.execute(
            update(m.orders)
            .where(
                and_(
                    m.orders.id == order_id,
                    m.orders.assigned_master_id == master_id,
                    m.orders.status == m.OrderStatus.EN_ROUTE,
                )
            )
            .values(status=m.OrderStatus.WORKING, updated_at=func.now(), version=m.orders.version + 1)
            .returning(m.orders.id)
        )
        if not result.first():
            await cb.answer("Не удалось обновить статус.", show_alert=True)
            return
        await session.execute(
            insert(m.order_status_history).values(
                order_id=order_id,
                from_status=m.OrderStatus.EN_ROUTE,
                to_status=m.OrderStatus.WORKING,
                changed_by_master_id=master_id,
                reason="master_working",
            )
        )
        await session.commit()
    await cb.answer("Статус обновлён на WORKING")
    await render_active_order(cb, master_id, order_id=order_id)
@router.callback_query(F.data == "m:fin")
async def finances_root(cb: CallbackQuery, state: FSMContext) -> None:
    async with SessionLocal() as session:
        master = await ensure_master(session, cb.from_user.id)
        master_id = master.id
    await render_commission_list(cb, master_id, mode="aw", page=1, state=state)
    await cb.answer()


@router.callback_query(F.data.startswith("m:fin:aw:"))
async def finances_awaiting(cb: CallbackQuery, state: FSMContext) -> None:
    page_str = cb.data.split(":")[-1]
    page = int(page_str) if page_str.isdigit() else 1
    async with SessionLocal() as session:
        master = await ensure_master(session, cb.from_user.id)
        master_id = master.id
    await render_commission_list(cb, master_id, mode="aw", page=page, state=state)
    await cb.answer()


@router.callback_query(F.data.startswith("m:fin:pd:"))
async def finances_paid(cb: CallbackQuery, state: FSMContext) -> None:
    page_str = cb.data.split(":")[-1]
    page = int(page_str) if page_str.isdigit() else 1
    async with SessionLocal() as session:
        master = await ensure_master(session, cb.from_user.id)
        master_id = master.id
    await render_commission_list(cb, master_id, mode="pd", page=page, state=state)
    await cb.answer()


@router.callback_query(F.data.startswith("m:fin:ov:"))
async def finances_overdue(cb: CallbackQuery, state: FSMContext) -> None:
    page_str = cb.data.split(":")[-1]
    page = int(page_str) if page_str.isdigit() else 1
    async with SessionLocal() as session:
        master = await ensure_master(session, cb.from_user.id)
        master_id = master.id
    await render_commission_list(cb, master_id, mode="ov", page=page, state=state)
    await cb.answer()


@router.callback_query(F.data.startswith("m:fin:cm:pt:"))
async def finances_show_payto(cb: CallbackQuery) -> None:
    commission_id = int(cb.data.split(":")[-1])
    async with SessionLocal() as session:
        commission = await session.get(m.commissions, commission_id)
    if not commission or commission.master is None or commission.master.tg_user_id != cb.from_user.id:
        await cb.answer("Комиссия не найдена.", show_alert=True)
        return
    snapshot_text = format_pay_snapshot(commission.pay_to_snapshot or {})
    await cb.message.answer(snapshot_text or "Реквизиты отсутствуют.")
    await cb.answer()


@router.callback_query(F.data.startswith("m:fin:cm:chk:"))
async def finances_request_check(cb: CallbackQuery, state: FSMContext) -> None:
    commission_id = int(cb.data.split(":")[-1])
    data = await state.get_data()
    ctx = data.get("fin_ctx")
    await state.update_data(fin_upload={"commission_id": commission_id}, fin_ctx=ctx)
    await state.set_state(FinanceUpload.check)
    await cb.message.answer("Пришлите фото или PDF чека об оплате.")
    await cb.answer()


@router.callback_query(F.data.startswith("m:fin:cm:ip:"))
async def finances_mark_paid(cb: CallbackQuery, state: FSMContext) -> None:
    commission_id = int(cb.data.split(":")[-1])
    async with SessionLocal() as session:
        master = await ensure_master(session, cb.from_user.id)
        master_id = master.id
        commission = await session.get(m.commissions, commission_id)
        if not commission or commission.master_id != master_id:
            await cb.answer("Комиссия не найдена.", show_alert=True)
            return
        commission.paid_reported_at = now()
        if commission.status == m.CommissionStatus.WAIT_PAY:
            commission.status = m.CommissionStatus.REPORTED
        await session.commit()
    await cb.answer("Отметили оплату.")
    await render_commission_card(cb, master_id, commission_id, state)


@router.callback_query(F.data.startswith("m:fin:cm:"))
async def finances_card(cb: CallbackQuery, state: FSMContext) -> None:
    parts = cb.data.split(":")
    try:
        commission_id = int(parts[3])
    except (IndexError, ValueError):
        await cb.answer("Некорректный идентификатор", show_alert=True)
        return
    async with SessionLocal() as session:
        master = await ensure_master(session, cb.from_user.id)
        master_id = master.id
    await render_commission_card(cb, master_id, commission_id, state)
    await cb.answer()


@router.message(FinanceUpload.check, F.content_type.in_({ContentType.PHOTO, ContentType.DOCUMENT}))
async def finance_upload_check(msg: Message, state: FSMContext) -> None:
    data = await state.get_data()
    fin_ctx = data.get("fin_ctx", {"mode": "aw", "page": 1})
    upload = data.get("fin_upload", {})
    commission_id = upload.get("commission_id")
    if commission_id is None:
        await msg.answer("Не удалось определить комиссию.")
        await state.clear()
        return
    file_id = msg.photo[-1].file_id if msg.photo else msg.document.file_id
    async with SessionLocal() as session:
        commission = await session.get(m.commissions, commission_id)
        master = await ensure_master(session, msg.from_user.id)
        if not commission or commission.master_id != master.id:
            await msg.answer("Комиссия не найдена.")
            await state.clear()
            return
        master_id = master.id
        session.add(
            m.attachments(
                entity_type=m.AttachmentEntity.COMMISSION,
                entity_id=commission_id,
                file_type=m.AttachmentFileType.PHOTO if msg.photo else m.AttachmentFileType.DOCUMENT,
                file_id=file_id,
            )
        )
        commission.has_checks = True
        await session.commit()
    await state.set_state(None)
    await state.update_data(fin_ctx=fin_ctx, fin_upload=None)
    await msg.answer("Чек сохранён.")
    await render_commission_card(msg, master_id, commission_id, state)


@router.message(FinanceUpload.check)
async def finance_upload_invalid(msg: Message) -> None:
    await msg.answer("Пришлите фото или PDF чека.")


@router.callback_query(F.data == "m:rf")
async def referrals_root(cb: CallbackQuery) -> None:
    await render_referral_dashboard(cb, tg_user_id=cb.from_user.id)
    await cb.answer()


@router.callback_query(F.data == "m:kb")
async def knowledge_base_root(cb: CallbackQuery) -> None:
    await render_support_info(cb, tg_user_id=cb.from_user.id)
    await cb.answer()


@router.callback_query(F.data == "m:new")
async def offers_root(cb: CallbackQuery) -> None:
    async with SessionLocal() as session:
        master = await ensure_master(session, cb.from_user.id)
    await render_new_offers(cb, master, page=1)
    await cb.answer()
@router.callback_query(F.data.startswith("m:new:card:"))
async def offers_card(cb: CallbackQuery) -> None:
    parts = cb.data.split(":")
    try:
        order_id = int(parts[2])
    except (IndexError, ValueError):
        await cb.answer("Некорректный идентификатор", show_alert=True)
        return
    try:
        page = int(parts[3]) if len(parts) > 3 else 1
    except ValueError:
        page = 1
    async with SessionLocal() as session:
        master = await ensure_master(session, cb.from_user.id)
    await render_offer_card(cb, master, order_id, page)
    await cb.answer()
@router.callback_query(F.data.startswith("m:new:"))
async def offers_page(cb: CallbackQuery) -> None:
    parts = cb.data.split(":")
    if len(parts) != 3 or not parts[2].isdigit():
        return
    page = int(parts[2])
    async with SessionLocal() as session:
        master = await ensure_master(session, cb.from_user.id)
    await render_new_offers(cb, master, page=page)
    await cb.answer()
@router.callback_query(F.data.startswith("m:new:acc:"))
async def offer_accept(cb: CallbackQuery) -> None:
    parts = cb.data.split(":")
    try:
        order_id = int(parts[2])
    except (IndexError, ValueError):
        await cb.answer("Некорректный идентификатор", show_alert=True)
        return
    try:
        page = int(parts[3]) if len(parts) > 3 else 1
    except ValueError:
        page = 1
    async with SessionLocal() as session:
        master = await ensure_master(session, cb.from_user.id)
        if master.is_blocked:
            await cb.answer("Нельзя принять: профиль заблокирован.", show_alert=True)
            return
        limit = await max_active_orders(session)
        active = await count_active_orders(session, master.id)
        if active >= limit:
            await cb.answer("Достигнут лимит активных заказов.", show_alert=True)
            return
        upd = await session.execute(
            update(m.orders)
            .where(
                and_(
                    m.orders.id == order_id,
                    m.orders.assigned_master_id.is_(None),
                    m.orders.status.in_((m.OrderStatus.CREATED, m.OrderStatus.SEARCHING)),
                )
            )
            .values(
                assigned_master_id=master.id,
                status=m.OrderStatus.ASSIGNED,
                updated_at=func.now(),
                version=m.orders.version + 1,
            )
            .returning(m.orders.id)
        )
        if not upd.first():
            await cb.answer("Увы, заказ уже забрали.", show_alert=True)
            return
        await session.execute(
            update(m.offers)
            .where((m.offers.order_id == order_id) & (m.offers.master_id == master.id))
            .values(state=m.OfferState.ACCEPTED, responded_at=func.now())
        )
        await session.execute(
            insert(m.order_status_history).values(
                order_id=order_id,
                from_status=m.OrderStatus.SEARCHING,
                to_status=m.OrderStatus.ASSIGNED,
                changed_by_master_id=master.id,
                reason='accepted_by_master',
            )
        )
        await session.commit()
    await cb.answer("Заказ закреплён за вами")
    async with SessionLocal() as session:
        master = await ensure_master(session, cb.from_user.id)
    await render_new_offers(cb, master, page=page)
@router.callback_query(F.data.startswith("m:new:dec:"))
async def offer_decline(cb: CallbackQuery) -> None:
    parts = cb.data.split(":")
    try:
        order_id = int(parts[2])
    except (IndexError, ValueError):
        await cb.answer("Некорректный идентификатор", show_alert=True)
        return
    try:
        page = int(parts[3]) if len(parts) > 3 else 1
    except ValueError:
        page = 1
    async with SessionLocal() as session:
        master = await ensure_master(session, cb.from_user.id)
        await session.execute(
            update(m.offers)
            .where((m.offers.order_id == order_id) & (m.offers.master_id == master.id))
            .values(state=m.OfferState.DECLINED, responded_at=func.now())
        )
        await session.commit()
    await cb.answer("Вы отказались от оффера")
    async with SessionLocal() as session:
        master = await ensure_master(session, cb.from_user.id)
    await render_new_offers(cb, master, page=page)
@router.callback_query(F.data.startswith("m:act:cls:"))
async def order_finish(cb: CallbackQuery, state: FSMContext) -> None:
    order_id = int(cb.data.split(":")[-1])
    async with SessionLocal() as session:
        master = await ensure_master(session, cb.from_user.id)
        order = await session.get(m.orders, order_id)
        if order is None or order.assigned_master_id != master.id:
            await cb.answer("Заказ не найден.", show_alert=True)
            return
        if order.status != m.OrderStatus.WORKING:
            await cb.answer("Закрыть можно только заказ в статусе WORKING.", show_alert=True)
            return
        master_id = master.id
    await state.update_data(order_id=order_id, master_id=master_id)
    await cb.message.answer("Укажите сумму к получению (пример: 2490.00).")
    await state.set_state(State("m:act:sum"))
    await cb.answer()
@router.message(State("m:act:sum"))
async def close_order_sum(msg: Message, state: FSMContext) -> None:
    amount = normalize_money(msg.text or "")
    if amount is None:
        await msg.answer("Сумма должна быть больше нуля (например, 2490.00).")
        return
    await state.update_data(sum=str(amount))
    await msg.answer("Приложите акт (фото или PDF).")
    await state.set_state(State("m:act:act"))
@router.message(State("m:act:act"), F.content_type.in_({ContentType.PHOTO, ContentType.DOCUMENT}))
async def close_order_act(msg: Message, state: FSMContext) -> None:
    data = await state.get_data()
    order_id = int(data["order_id"])
    amount = Decimal(data["sum"])
    master_id = data.get("master_id")
    if master_id is None:
        async with SessionLocal() as session:
            master = await ensure_master(session, msg.from_user.id)
            master_id = master.id
        await state.update_data(master_id=master_id)
    file_id = msg.photo[-1].file_id if msg.photo else msg.document.file_id
    async with SessionLocal() as session:
        order = await session.get(m.orders, order_id)
        master = await session.get(m.masters, master_id)
        if (
            order is None
            or master is None
            or order.assigned_master_id != master.id
        ):
            await msg.answer("Заказ не найден или недоступен.")
            await state.clear()
            return
        if order.status != m.OrderStatus.WORKING:
            await msg.answer("Текущий статус не позволяет закрыть заказ.")
            await state.clear()
            return
        session.add(
            m.attachments(
                entity_type=m.AttachmentEntity.ORDER,
                entity_id=order_id,
                file_type=m.AttachmentFileType.PHOTO if msg.photo else m.AttachmentFileType.DOCUMENT,
                file_id=file_id,
            )
        )
        order.total_price = amount
        order.status = m.OrderStatus.PAYMENT
        order.updated_at = func.now()
        order.version += 1
        await session.execute(
            insert(m.order_status_history).values(
                order_id=order_id,
                from_status=m.OrderStatus.WORKING,
                to_status=m.OrderStatus.PAYMENT,
                changed_by_master_id=master.id,
                reason="master_uploaded_act",
            )
        )
        await session.flush()
        await create_commission_for_order(session, order, master)
        await session.commit()
    amount_str = f"{amount:.2f}"
    await state.clear()
    await msg.answer(
        f"Заказ #{order_id}: акт получен, сумма {amount_str}. Комиссия сформирована.",
    )
    await render_active_order(msg, master_id, order_id=order_id)


async def watchdog_breaks(_bot: Bot):
    while True:
        async with SessionLocal() as session:
            q = await session.execute(
                select(m.masters).where(
                    and_(
                        m.masters.shift_status == m.ShiftStatus.BREAK,
                        m.masters.break_until.isnot(None),
                        m.masters.break_until < func.now(),
                    )
                )
            )
            changed = False
            for mst in q.scalars():
                mst.shift_status = m.ShiftStatus.SHIFT_ON
                mst.break_until = None
                changed = True
            if changed:
                await session.commit()
        await asyncio.sleep(30)
async def watchdog_commissions_block(_bot: Bot):
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
















