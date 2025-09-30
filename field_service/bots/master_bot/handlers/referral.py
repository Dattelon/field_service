from __future__ import annotations

from decimal import Decimal

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from field_service.bots.common import safe_answer_callback, safe_edit_or_send
from field_service.db import models as m
from field_service.services import settings_service

from ..utils import inline_keyboard

router = Router(name='master_referral')

REFERRAL_STATUS_LABELS = {
    m.ReferralRewardStatus.ACCRUED.value: "Начислено",
    m.ReferralRewardStatus.PAID.value: "Выплачено",
    m.ReferralRewardStatus.CANCELED.value: "Отменено",
}


@router.callback_query(F.data == 'm:rf')
async def referrals_root(callback: CallbackQuery, session: AsyncSession, master: m.masters) -> None:
    await _render_referrals(callback, session, master)
    await safe_answer_callback(callback)


@router.callback_query(F.data == 'm:kb')
async def knowledge_base(callback: CallbackQuery, session: AsyncSession, master: m.masters) -> None:
    await _render_support(callback, session)
    await safe_answer_callback(callback)


async def _render_referrals(
    event: Message | CallbackQuery,
    session: AsyncSession,
    master: m.masters,
) -> None:
    master_id = master.id
    referral_code = (master.referral_code or '').strip()

    totals_stmt = (
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
    totals = (await session.execute(totals_stmt)).all()

    latest_stmt = (
        select(
            m.referral_rewards.level,
            m.referral_rewards.amount,
            m.referral_rewards.created_at,
            m.referral_rewards.status,
            m.referral_rewards.commission_id,
            m.commissions.order_id,
        )
        .join(m.commissions, m.commissions.id == m.referral_rewards.commission_id)
        .where(
            m.referral_rewards.referrer_id == master_id,
            m.referral_rewards.status != m.ReferralRewardStatus.CANCELED,
        )
        .order_by(m.referral_rewards.created_at.desc())
        .limit(5)
    )
    latest = (await session.execute(latest_stmt)).all()

    level_stats = {1: {'count': 0, 'amount': Decimal('0')}, 2: {'count': 0, 'amount': Decimal('0')}}
    for level, count, total in totals:
        try:
            level_index = int(level)
        except (TypeError, ValueError):
            continue
        bucket = level_stats.get(level_index)
        if not bucket:
            continue
        bucket['count'] = int(count or 0)
        bucket['amount'] = Decimal(total or 0)

    total_amount = level_stats[1]['amount'] + level_stats[2]['amount']
    lines: list[str] = ["<b>🎁 Реферальная программа</b>"]
    if referral_code:
        lines.append(f"Ваш код: <code>{referral_code}</code>")
    else:
        lines.append("Код появится после активации аккаунта.")
    lines.append("Приглашайте мастеров: уровень 1 — 10%, уровень 2 — 5% от комиссии.")
    lines.append("")
    for level in (1, 2):
        bucket = level_stats[level]
        lines.append(
            f"Уровень {level}: {bucket['count']} приглашений • {bucket['amount']:.2f} ₽"
        )
    lines.append("")
    lines.append(f"Всего начислено: {total_amount:.2f} ₽")

    if latest:
        lines.append("")
        lines.append("Последние начисления:")
        for row in latest:
            level, amount, created_at, status, commission_id, order_id = row
            amount_dec = Decimal(amount or 0)
            status_key = getattr(status, 'value', status)
            status_label = REFERRAL_STATUS_LABELS.get(status_key, status_key)
            order_hint = f"комиссия #{commission_id}"
            if order_id is not None:
                order_hint += f", заказ #{order_id}"
            lines.append(
                f"{created_at:%d.%m %H:%M} • L{int(level)} • {amount_dec:.2f} ₽ • {status_label} ({order_hint})"
            )
    else:
        lines.append("")
        lines.append("Начислений пока не было.")

    markup = inline_keyboard([[InlineKeyboardButton(text='⬅️ В главное меню', callback_data='m:menu')]])
    await safe_edit_or_send(event, "\n".join(lines), markup)


async def _render_support(event: Message | CallbackQuery, session: AsyncSession) -> None:
    raw_values = await settings_service.get_values(["support_contact", "support_faq_url"])
    contact = (raw_values.get("support_contact", (None, None))[0] or '').strip()
    faq_url = (raw_values.get("support_faq_url", (None, None))[0] or '').strip()

    lines = ["<b>📚 База знаний</b>"]
    lines.append(f"Поддержка: {contact or '—'}")
    if faq_url and faq_url != '-':
        lines.append(f"FAQ: {faq_url}")
    else:
        lines.append("FAQ: ссылка пока недоступна")

    markup = inline_keyboard([[InlineKeyboardButton(text='⬅️ В главное меню', callback_data='m:menu')]])
    await safe_edit_or_send(event, "\n".join(lines), markup)

