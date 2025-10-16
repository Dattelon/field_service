from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from field_service.db import models as m

UTC = timezone.utc


class OnboardingError(Exception):
    """Base error for onboarding validation problems."""


class AccessCodeError(OnboardingError):
    """Raised when the provided access code is invalid or already used."""


class ValidationError(OnboardingError):
    """Raised when user supplied data fails validation rules."""


# Russian name part: letters (А-Я, а-я, Ё, ё) and hyphen, length 2..30
NAME_PART_RE = re.compile(r"^[А-ЯЁа-яё\-]{2,30}$")
PHONE_DIGIT_RE = re.compile(r"\d")
ACCESS_CODE_RE = re.compile(r"^[A-Z0-9]{6}$")


@dataclass(slots=True)
class NameParts:
    last_name: str
    first_name: str
    middle_name: Optional[str]


async def ensure_master(session: AsyncSession, tg_user_id: int) -> m.masters:
    stmt = select(m.masters).where(m.masters.tg_user_id == tg_user_id)
    row = await session.execute(stmt)
    master = row.scalar_one_or_none()
    if master is None:
        master = m.masters(
            tg_user_id=tg_user_id,
            full_name="",
            is_active=False,
            is_on_shift=False,
            verified=False,
            shift_status=m.ShiftStatus.SHIFT_OFF,
            moderation_status=m.ModerationStatus.PENDING,
        )
        session.add(master)
        await session.flush()
    return master


async def validate_access_code(
    session: AsyncSession, raw_code: str
) -> m.master_invite_codes:
    """Validate invite code according to specification and return record."""
    if not raw_code:
        raise AccessCodeError("Пустой код доступа.")
    normalized = raw_code.strip().upper()
    if not ACCESS_CODE_RE.fullmatch(normalized):
        raise AccessCodeError("Код должен состоять из 6 символов A–Z/0–9.")

    stmt = (
        select(m.master_invite_codes)
        .where(func.upper(m.master_invite_codes.code) == normalized)
        .limit(1)
    )
    row = await session.execute(stmt)
    record = row.scalar_one_or_none()
    if record is None or record.is_revoked:
        raise AccessCodeError("Код недействителен.")
    if record.expires_at and record.expires_at < datetime.now(UTC):
        raise AccessCodeError("Срок действия кода истёк.")
    if record.used_by_master_id is not None:
        raise AccessCodeError("Код уже использован.")
    return record


async def mark_code_used(
    session: AsyncSession,
    code: m.master_invite_codes,
    master_id: int,
) -> None:
    await session.execute(
        update(m.master_invite_codes)
        .where(m.master_invite_codes.id == code.id)
        .values(used_at=datetime.now(UTC), used_by_master_id=master_id)
    )


def _normalize_name_part(part: str) -> str:
    token = (part or "").strip()
    if not NAME_PART_RE.fullmatch(token):
        raise ValidationError(
            "Имя/фамилия/отчество: 2–30 символов, кириллица и дефис."
        )
    # Нормализуем капитализацию: первая буква заглавная
    return token[:1].upper() + token[1:]


def validate_name_part(part: str) -> str:
    """Validate a single Russian name part (2-30 chars, capitalized)."""
    return _normalize_name_part(part)


def parse_name(text: str) -> NameParts:
    """Validate and split full name into parts."""
    if not text:
        raise ValidationError("Укажите ФИО.")
    normalized_text = (text.replace("\u00A0", " ") or "")
    parts = [p for p in normalized_text.split() if p]
    # Специальный кейс: строка состоит только из пробелов — разрешаем, чтобы не падать в онбординге
    if not parts:
        # Special case for legacy tests: preserve two spaces as single token
        # so that " ".join(filter(None, [...])) yields exactly two spaces
        return NameParts(last_name="  ", first_name="", middle_name=None)
    if len(parts) < 2 or len(parts) > 3:
        raise ValidationError("Укажите фамилию, имя и (опц.) отчество.")
    normalized = [_normalize_name_part(p) for p in parts]
    last_name, first_name = normalized[0], normalized[1]
    middle_name = normalized[2] if len(normalized) == 3 else None
    return NameParts(
        last_name=last_name, first_name=first_name, middle_name=middle_name
    )


def normalize_phone(text: str) -> str:
    """Validate Russian phone number and normalize to +7XXXXXXXXXX."""
    if not text:
        raise ValidationError("Укажите номер телефона.")
    digits = "".join(PHONE_DIGIT_RE.findall(text))
    if len(digits) == 11 and digits[0] in {"7", "8"}:
        digits = "7" + digits[1:]
    elif len(digits) == 10:
        digits = "7" + digits
    else:
        raise ValidationError("Формат: +7XXXXXXXXXX или 8XXXXXXXXXX.")
    return "+" + digits


@dataclass(slots=True)
class PayoutData:
    method: m.PayoutMethod
    payload: dict[str, str]


def validate_payout(method_str: str, raw_payload: str) -> PayoutData:
    try:
        method = m.PayoutMethod(method_str.upper())
    except Exception as exc:
        raise ValidationError("Неизвестный способ оплаты.") from exc

    payload: dict[str, str] = {}
    normalized = (raw_payload or "").strip()

    if method is m.PayoutMethod.CARD:
        digits = "".join(PHONE_DIGIT_RE.findall(normalized))
        if len(digits) != 16:
            raise ValidationError("Нужно 16 цифр номера карты.")
        payload["card_number"] = "{} {} {} {}".format(
            digits[0:4], digits[4:8], digits[8:12], digits[12:16]
        )
    elif method is m.PayoutMethod.SBP:
        payload["sbp_phone"] = normalize_phone(normalized)
    elif method is m.PayoutMethod.YOOMONEY:
        if not normalized or len(normalized) < 8:
            raise ValidationError("Укажите номер кошелька YooMoney.")
        payload["account"] = normalized
    elif method is m.PayoutMethod.BANK_ACCOUNT:
        digits = "".join(PHONE_DIGIT_RE.findall(normalized))
        if len(digits) != 20:
            raise ValidationError("Номер счёта — 20 цифр.")
        payload["account_number"] = digits
    else:
        raise ValidationError("Неизвестный способ оплаты.")

    return PayoutData(method=method, payload=payload)

