from __future__ import annotations

import math
from decimal import Decimal
from types import SimpleNamespace
from typing import Sequence

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, ContentType, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from field_service.db import models as m

from ..finance import format_pay_snapshot
from ..states import FinanceUploadStates
from ..utils import inline_keyboard, now_utc

router = Router(name="master_finance")

COMMISSIONS_PAGE_SIZE = 5
FINANCE_MODES: dict[str, tuple[str, tuple[m.CommissionStatus, ...]]] = {
    "aw": ("Ожидают оплаты", (m.CommissionStatus.WAIT_PAY, m.CommissionStatus.REPORTED)),
    "pd": ("Подтверждённые", (m.CommissionStatus.APPROVED,)),
    "ov": ("Просроченные", (m.CommissionStatus.OVERDUE,)),
}
MODE_ORDER = ("aw", "pd", "ov")

STATUS_LABELS: dict[m.CommissionStatus, str] = {
    m.CommissionStatus.WAIT_PAY: "Ожидают оплаты",
    m.CommissionStatus.REPORTED: "Сообщено об оплате",
    m.CommissionStatus.APPROVED: "Подтверждённые",
    m.CommissionStatus.OVERDUE: "Просроченные",
}

ORDER_TYPE_LABELS: dict[m.OrderType, str] = {
    m.OrderType.NORMAL: "Обычный",
    m.OrderType.GUARANTEE: "Гарантия",
}


@router.callback_query(F.data == "m:fin")
async def finances_root(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    master: m.masters,
) -> None:
    await _render_commission_list(callback, session, master, mode="aw", page=1, state=state)
    await callback.answer()


@router.callback_query(F.data.regexp(r"^m:fin:(aw|pd|ov):(\d+)$"))
async def finances_page(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    master: m.masters,
) -> None:
    _, _, mode, page_str = callback.data.split(":")
    page = int(page_str)
    await _render_commission_list(callback, session, master, mode=mode, page=page, state=state)
    await callback.answer()


@router.callback_query(F.data.regexp(r"^m:fin:cm:(\d+)$"))
async def finances_card(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    master: m.masters,
) -> None:
    commission_id = int(callback.data.split(":")[-1])
    await _render_commission_card(callback, session, master, commission_id, state)
    await callback.answer()


@router.callback_query(F.data.regexp(r"^m:fin:cm:pt:(\d+)$"))
async def finances_show_payto(
    callback: CallbackQuery,
    session: AsyncSession,
    master: m.masters,
) -> None:
    commission_id = int(callback.data.split(":")[-1])
    commission = await _get_commission(session, master.id, commission_id)
    if commission is None:
        await callback.answer("Комиссия не найдена.", show_alert=True)
        return

    snapshot_text = format_pay_snapshot(commission.pay_to_snapshot)
    if snapshot_text:
        await callback.message.answer(snapshot_text)
    else:
        await callback.message.answer("Реквизиты недоступны.")

    qr_id = commission.pay_to_snapshot.get("sbp_qr_file_id") if commission.pay_to_snapshot else None
    if qr_id:
        try:
            await callback.message.answer_photo(qr_id)
        except TelegramBadRequest:
            await callback.message.answer("Не удалось показать QR-код.")
    await callback.answer()


@router.callback_query(F.data.regexp(r"^m:fin:cm:chk:(\d+)$"))
async def finances_request_check(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    master: m.masters,
) -> None:
    commission_id = int(callback.data.split(":")[-1])
    commission = await _get_commission(session, master.id, commission_id)
    if commission is None:
        await callback.answer("Комиссия не найдена.", show_alert=True)
        return

    await state.update_data(fin_upload={"commission_id": commission_id})
    await state.set_state(FinanceUploadStates.check)
    await callback.message.answer("Загрузите чек об оплате (фото или PDF).")
    await callback.answer()


@router.callback_query(F.data.regexp(r"^m:fin:cm:ip:(\d+)$"))
async def finances_mark_paid(
    callback: CallbackQuery,
    session: AsyncSession,
    master: m.masters,
    state: FSMContext,
) -> None:
    commission_id = int(callback.data.split(":")[-1])
    commission = await _get_commission(session, master.id, commission_id)
    if commission is None:
        await callback.answer("Комиссия не найдена.", show_alert=True)
        return

    commission.paid_reported_at = now_utc()
    if commission.status == m.CommissionStatus.WAIT_PAY:
        commission.status = m.CommissionStatus.REPORTED
    await session.commit()
    await callback.answer("Отметили оплату. Ждём подтверждения.", show_alert=True)
    await _render_commission_card(callback, session, master, commission_id, state)


@router.message(
    FinanceUploadStates.check,
    F.content_type.in_({ContentType.PHOTO, ContentType.DOCUMENT}),
)
async def finances_upload_check(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    master: m.masters,
) -> None:
    data = await state.get_data()
    upload = data.get("fin_upload") or {}
    commission_id = upload.get("commission_id")
    if commission_id is None:
        await message.answer("Что-то пошло не так. Попробуйте заново из раздела «Финансы».")
        await state.clear()
        return

    commission = await _get_commission(session, master.id, int(commission_id))
    if commission is None:
        await message.answer("Комиссия не найдена.")
        await state.clear()
        return

    file_id = message.photo[-1].file_id if message.photo else message.document.file_id
    file_type = m.AttachmentFileType.PHOTO if message.photo else m.AttachmentFileType.DOCUMENT
    session.add(
        m.attachments(
            entity_type=m.AttachmentEntity.COMMISSION,
            entity_id=commission.id,
            file_type=file_type,
            file_id=file_id,
            uploaded_by_master_id=master.id,
        )
    )
    commission.has_checks = True
    await session.commit()

    await state.set_state(None)
    await state.update_data(fin_upload=None)
    await message.answer("Чек загружен.")
    await _render_commission_card(message, session, master, commission.id, state)


@router.message(FinanceUploadStates.check)
async def finances_upload_invalid(message: Message) -> None:
    await message.answer("Доступны только фото или PDF-файлы.")


async def _render_commission_list(
    event: Message | CallbackQuery,
    session: AsyncSession,
    master: m.masters,
    *,
    mode: str,
    page: int,
    state: FSMContext,
) -> None:
    title, statuses = FINANCE_MODES.get(mode, FINANCE_MODES["aw"])
    rows = await _load_commissions(session, master.id, statuses)

    await state.update_data(fin_ctx={"mode": mode, "page": page})
    total = len(rows)
    pages = max(1, math.ceil(total / COMMISSIONS_PAGE_SIZE))
    page = max(1, min(page, pages))
    start = (page - 1) * COMMISSIONS_PAGE_SIZE
    current = rows[start : start + COMMISSIONS_PAGE_SIZE]

    lines: list[str] = [f"{title}"]
    buttons: list[list[InlineKeyboardButton]] = []

    mode_buttons: list[InlineKeyboardButton] = []
    for code in MODE_ORDER:
        caption, _ = FINANCE_MODES[code]
        label = f"* {caption}" if code == mode else caption
        mode_buttons.append(InlineKeyboardButton(text=label, callback_data=f"m:fin:{code}:1"))
    buttons.append(mode_buttons)

    if not current:
        lines.append("No commissions in this section.")
    else:
        for commission in current:
            lines.append(_commission_summary_line(commission))
            lines.append(f"Status: {STATUS_LABELS.get(commission.status, commission.status.value)}")
            if commission.deadline_at:
                lines.append(
                    f"Дедлайн: {commission.deadline_at.strftime('%d.%m %H:%M')}"
                )
            lines.append("")
            buttons.append(
                [
                    InlineKeyboardButton(
                        text=f"Комиссия #{commission.id}",
                        callback_data=f"m:fin:cm:{commission.id}",
                    )
                ]
            )

        nav: list[InlineKeyboardButton] = []
        if page > 1:
            nav.append(InlineKeyboardButton(text="<", callback_data=f"m:fin:{mode}:{page - 1}"))
        nav.append(InlineKeyboardButton(text=f"{page}/{pages}", callback_data="noop"))
        if page < pages:
            nav.append(InlineKeyboardButton(text=">", callback_data=f"m:fin:{mode}:{page + 1}"))
        if nav:
            buttons.append(nav)

    buttons.append([InlineKeyboardButton(text="Меню", callback_data="m:menu")])
    await _respond(event, "\n".join([line for line in lines if line]), inline_keyboard(buttons))


async def _render_commission_card(
    event: Message | CallbackQuery,
    session: AsyncSession,
    master: m.masters,
    commission_id: int,
    state: FSMContext,
) -> None:
    row = await _load_commission_detail(session, master.id, commission_id)
    if row is None:
        if isinstance(event, Message):
            await event.answer("Комиссия не найдена.")
        elif isinstance(event, CallbackQuery) and event.message:
            await event.message.answer("Комиссия не найдена.")
        return

    commission = row.commission
    order = row.order
    status_label = STATUS_LABELS.get(commission.status, commission.status.value)

    lines = [f"Комиссия #{commission.id}", status_label]
    if order:
        order_label = ORDER_TYPE_LABELS.get(order.order_type, order.order_type.value)
        lines.append(f"Заказ №{order.id} ({order_label})")
        if order.total_sum is not None:
            lines.append(f"Сумма заказа: {Decimal(order.total_sum):.2f} ₽")
    lines.append(f"Комиссия: {Decimal(commission.amount):.2f} ₽")

    rate = commission.rate or commission.percent
    if rate is not None:
        rate_decimal = Decimal(str(rate))
        rate_percent = rate_decimal * 100 if rate_decimal <= 1 else rate_decimal
        lines.append(f"Ставка: {rate_percent:.2f}%")

    if commission.deadline_at:
        lines.append(f"Дедлайн: {commission.deadline_at.strftime('%d.%m %H:%M')}")
    if commission.paid_reported_at:
        lines.append(f"Отмечено как оплачено: {commission.paid_reported_at.strftime('%d.%m %H:%M')}")
    if commission.paid_approved_at:
        lines.append(f"Подтверждено: {commission.paid_approved_at.strftime('%d.%m %H:%M')}")
    if commission.paid_amount is not None:
        lines.append(f"Подтверждённая сумма: {Decimal(commission.paid_amount):.2f} ₽")
    lines.append(f"Чеки приложены: {'да' if commission.has_checks else 'нет'}")

    buttons: list[list[InlineKeyboardButton]] = []
    buttons.append([
        InlineKeyboardButton(text="Реквизиты", callback_data=f"m:fin:cm:pt:{commission.id}")
    ])
    buttons.append([
        InlineKeyboardButton(text="Загрузить чек", callback_data=f"m:fin:cm:chk:{commission.id}")
    ])
    if commission.status in {m.CommissionStatus.WAIT_PAY, m.CommissionStatus.REPORTED}:
        buttons.append([
            InlineKeyboardButton(text="Я оплатил", callback_data=f"m:fin:cm:ip:{commission.id}")
        ])

    ctx = await state.get_data()
    fin_ctx = ctx.get("fin_ctx", {"mode": "aw", "page": 1})
    buttons.append([
        InlineKeyboardButton(
            text="Назад",
            callback_data=f"m:fin:{fin_ctx.get('mode', 'aw')}:{fin_ctx.get('page', 1)}",
        )
    ])

    await _respond(event, "\n".join([line for line in lines if line]), inline_keyboard(buttons))


async def _load_commissions(
    session: AsyncSession,
    master_id: int,
    statuses: Sequence[m.CommissionStatus],
) -> list[m.commissions]:
    stmt = (
        select(m.commissions)
        .where(
            and_(
                m.commissions.master_id == master_id,
                m.commissions.status.in_(tuple(statuses)),
            )
        )
        .order_by(m.commissions.deadline_at.asc().nullslast(), m.commissions.id.desc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def _load_commission_detail(
    session: AsyncSession,
    master_id: int,
    commission_id: int,
) -> SimpleNamespace | None:
    stmt = (
        select(m.commissions, m.orders)
        .join(m.orders, m.orders.id == m.commissions.order_id, isouter=True)
        .where(
            and_(
                m.commissions.master_id == master_id,
                m.commissions.id == commission_id,
            )
        )
        .limit(1)
    )
    row = (await session.execute(stmt)).first()
    if not row:
        return None
    return SimpleNamespace(commission=row.commissions, order=row.orders)


async def _get_commission(
    session: AsyncSession,
    master_id: int,
    commission_id: int,
) -> m.commissions | None:
    stmt = (
        select(m.commissions)
        .where(
            and_(
                m.commissions.id == commission_id,
                m.commissions.master_id == master_id,
            )
        )
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


def _commission_summary_line(commission: m.commissions) -> str:
    amount = Decimal(commission.amount)
    summary = f"Комиссия №{commission.id} — {amount:.2f} ₽"
    if commission.deadline_at:
        summary += f" — дедлайн {commission.deadline_at.strftime('%d.%m %H:%M')}"
    return summary


async def _respond(
    event: Message | CallbackQuery,
    text: str,
    markup: InlineKeyboardMarkup | None,
) -> None:
    if isinstance(event, CallbackQuery) and event.message:
        try:
            await event.message.edit_text(text, reply_markup=markup)
            return
        except TelegramBadRequest:
            await event.message.answer(text, reply_markup=markup)
            return
    if isinstance(event, Message):
        await event.answer(text, reply_markup=markup)
    elif isinstance(event, CallbackQuery) and event.message:
        await event.message.answer(text, reply_markup=markup)
