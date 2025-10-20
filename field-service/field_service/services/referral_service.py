from __future__ import annotations

import hashlib
import secrets
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from field_service.db import models as m

_PERCENT_RULES: dict[int, tuple[Decimal, Decimal]] = {
    1: (Decimal("10.00"), Decimal("0.10")),
    2: (Decimal("5.00"), Decimal("0.05")),
}
ROUND = Decimal("0.01")


async def _get_referrer_id(session: AsyncSession, master_id: Optional[int]) -> Optional[int]:
    if not master_id:
        return None
    result = await session.execute(
        select(m.referrals.referrer_id).where(m.referrals.master_id == master_id)
    )
    return result.scalar_one_or_none()


def _to_decimal(value: Optional[Decimal | int | float | str]) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    if isinstance(value, str):
        try:
            return Decimal(value)
        except Exception:
            return Decimal("0")
    return Decimal("0")


async def apply_rewards_for_commission(
    session: AsyncSession,
    *,
    commission_id: int,
    master_id: Optional[int],
    base_amount: Optional[Decimal | int | float | str],
) -> None:
    amount = _to_decimal(base_amount)
    if not master_id or amount <= 0:
        return

    chain: list[int] = []
    current_master = master_id
    for _level in (1, 2):
        ref_id = await _get_referrer_id(session, current_master)
        if ref_id is None:
            break
        chain.append(ref_id)
        current_master = ref_id

    if not chain:
        return

    seen: set[int] = set()
    for level, referrer_id in enumerate(chain, start=1):
        if referrer_id in seen:
            continue
        seen.add(referrer_id)
        config = _PERCENT_RULES.get(level)
        if not config:
            continue
        percent_display, rate = config
        reward_amount = (amount * rate).quantize(ROUND, rounding=ROUND_HALF_UP)
        if reward_amount <= 0:
            continue

        exists = await session.execute(
            select(m.referral_rewards.id).where(
                m.referral_rewards.commission_id == commission_id,
                m.referral_rewards.level == level,
            )
        )
        if exists.scalar_one_or_none() is not None:
            continue

        stmt = insert(m.referral_rewards).values(
            referrer_id=referrer_id,
            referred_master_id=master_id,
            commission_id=commission_id,
            level=level,
            percent=percent_display,
            amount=reward_amount,
            status=m.ReferralRewardStatus.ACCRUED,
        )
        await session.execute(stmt)

        # Получаем order_id для уведомления
        commission_data = await session.execute(
            select(m.commissions.order_id).where(m.commissions.id == commission_id)
        )
        order_id = commission_data.scalar_one_or_none()

        # Отправляем уведомление рефереру о начислении
        from field_service.services import push_notifications
        await push_notifications.notify_master(
            session,
            master_id=referrer_id,
            event=push_notifications.NotificationEvent.REFERRAL_REWARD_ACCRUED,
            amount=float(reward_amount),
            level=level,
            order_id=order_id or commission_id,
        )


async def generate_referral_code(session: AsyncSession, master_id: int) -> str:
    """
    Генерирует уникальный реферальный код для мастера.
    Формат: короткий хеш (8 символов, заглавные буквы и цифры)

    Args:
        session: Async database session
        master_id: ID мастера

    Returns:
        str: Сгенерированный уникальный код (8 символов)

    Raises:
        ValueError: Если не удалось сгенерировать уникальный код за 10 попыток
    """
    # Проверяем, есть ли уже код у мастера
    result = await session.execute(
        select(m.masters.referral_code).where(m.masters.id == master_id)
    )
    existing_code = result.scalar_one_or_none()
    if existing_code:
        return existing_code

    # Генерируем уникальный код
    max_attempts = 10
    for attempt in range(max_attempts):
        # Используем master_id + timestamp + случайность
        salt = secrets.token_hex(8)
        raw = f"{master_id}:{datetime.utcnow().isoformat()}:{salt}"
        code = hashlib.sha256(raw.encode()).hexdigest()[:8].upper()

        # Проверяем уникальность кода в БД
        check = await session.execute(
            select(m.masters.id).where(m.masters.referral_code == code)
        )
        if check.scalar_one_or_none() is None:
            # Код уникален - сохраняем в БД
            await session.execute(
                update(m.masters)
                .where(m.masters.id == master_id)
                .values(referral_code=code)
            )
            await session.flush()
            return code

    raise ValueError(f"Failed to generate unique referral code for master {master_id} after {max_attempts} attempts")
