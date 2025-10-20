from __future__ import annotations

from decimal import Decimal

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from field_service.bots.common import (
    MasterPaths,
    add_breadcrumbs_to_text,
    safe_answer_callback,
    safe_edit_or_send,
)
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


@router.callback_query(F.data == 'm:rf:share')
async def share_referral_code(callback: CallbackQuery, session: AsyncSession, master: m.masters) -> None:
    """Обработчик кнопки 'Поделиться кодом' - отправляет сообщение для пересылки"""
    referral_code = (master.referral_code or '').strip()

    if not referral_code:
        from field_service.services import referral_service
        referral_code = await referral_service.generate_referral_code(session, master.id)
        await session.commit()

    share_text = (
        f"👋 Присоединяйся к Field Service — сервису для мастеров!\n\n"
        f"🎁 Используй мой реферальный код: <code>{referral_code}</code>\n\n"
        f"✅ Получай бонусы за каждого приглашённого мастера\n"
        f"✅ Стабильный поток заказов\n"
        f"✅ Оплата в день выполнения\n\n"
        f"📲 Перешли это сообщение коллегам или скопируй код для отправки!"
    )

    # Отправляем сообщение, которое можно переслать
    if callback.message:
        await callback.message.answer(share_text)

    await safe_answer_callback(callback, "Сообщение с кодом отправлено! Теперь вы можете переслать его другим мастерам.")


async def _render_referrals(
    event: Message | CallbackQuery,
    session: AsyncSession,
    master: m.masters,
) -> None:
    master_id = master.id
    referral_code = (master.referral_code or '').strip()

    # Генерируем код автоматически, если его нет
    if not referral_code:
        from field_service.services import referral_service
        referral_code = await referral_service.generate_referral_code(session, master_id)
        await session.commit()

    # P1-7:
    invited_total_stmt = select(func.count()).select_from(m.masters).where(
        m.masters.referred_by_master_id == master_id
    )
    invited_total = int((await session.execute(invited_total_stmt)).scalar_one() or 0)
    
    invited_pending_stmt = select(func.count()).select_from(m.masters).where(
        m.masters.referred_by_master_id == master_id,
        m.masters.verified == False,
    )
    invited_pending = int((await session.execute(invited_pending_stmt)).scalar_one() or 0)

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
    lines: list[str] = ["<b>🤝 Реферальная программа</b>"]
    lines.append("")
    if referral_code:
        lines.append(f"Ваш код: <code>{referral_code}</code>")
    else:
        lines.append("Ваш реферальный код ещё не создан.")
    
    # P1-7:  
    lines.append("")
    lines.append(f"Приглашено мастеров: {invited_total}")
    if invited_pending > 0:
        lines.append(f"На модерации: {invited_pending}")
    
    lines.append("")
    lines.append("<b>Условия программы:</b>")
    lines.append("• Уровень 1 (прямые рефералы): 10% от комиссии")
    lines.append("• Уровень 2 (рефералы рефералов): 5% от комиссии")
    lines.append("• Вознаграждение начисляется автоматически")
    lines.append("")
    lines.append("<b>Как использовать бонусы:</b>")
    lines.append("Начисленные бонусы можно использовать для")
    lines.append("оплаты комиссий или вывести на счёт")
    lines.append("(функционал в разработке)")
    lines.append("")
    for level in (1, 2):
        bucket = level_stats[level]
        lines.append(
            f"Уровень {level}: {bucket['count']} начислений на {bucket['amount']:.2f} ₽"
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
            order_hint = f"ком #{commission_id}"
            if order_id is not None:
                order_hint += f", заказ #{order_id}"
            lines.append(
                f"{created_at:%d.%m %H:%M} • L{int(level)} • {amount_dec:.2f} ₽ • {status_label} ({order_hint})"
            )
    else:
        lines.append("")
        lines.append("Начислений пока нет.")

    # P1-7: Кнопка "Поделиться"
    buttons: list[list[InlineKeyboardButton]] = []
    if referral_code:
        buttons.append([
            InlineKeyboardButton(text="📤 Поделиться кодом", callback_data="m:rf:share"),
        ])
    buttons.append([
        InlineKeyboardButton(text="◀️ Главное меню", callback_data="m:menu")
    ])
    
    markup = inline_keyboard(buttons)
    text = "\n".join(lines)
    text = add_breadcrumbs_to_text(text, MasterPaths.REFERRAL)
    await safe_edit_or_send(event, text, markup)


async def _render_support(event: Message | CallbackQuery, session: AsyncSession) -> None:
    raw_values = await settings_service.get_values(["support_contact", "support_faq_url"])
    contact = (raw_values.get("support_contact", (None, None))[0] or '').strip()
    faq_url = (raw_values.get("support_faq_url", (None, None))[0] or '').strip()

    lines = ["<b>📚 База знаний</b>"]
    lines.append(f"Контакты поддержки: {contact or 'не указаны'}")
    if faq_url and faq_url != '-':
        lines.append(f"FAQ: {faq_url}")
    else:
        lines.append("FAQ: временно недоступен")

    markup = inline_keyboard([[
        InlineKeyboardButton(text="◀️ Главное меню", callback_data="m:menu")
    ]])
    text = "\n".join(lines)
    text = add_breadcrumbs_to_text(text, MasterPaths.KNOWLEDGE)
    await safe_edit_or_send(event, text, markup)

