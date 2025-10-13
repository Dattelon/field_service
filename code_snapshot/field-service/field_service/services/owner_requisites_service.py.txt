from __future__ import annotations

import json
from typing import Any, Dict

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from field_service.db import models as m

ALLOWED_METHODS = {"card", "sbp", "cash"}

DEFAULT_REQUISITES: Dict[str, Any] = {
    "methods": [],
    "card_number": "",
    "card_holder": "",
    "card_bank": "",
    "sbp_phone": "",
    "sbp_bank": "",
    "sbp_qr_file_id": "",
    "other_text": "",
    "comment_template": "Комиссия #<order_id> от <master_fio>",
}


def is_default(raw: Any) -> bool:
    normalized = ensure_schema(raw) if isinstance(raw, dict) else DEFAULT_REQUISITES
    if normalized['methods']:
        return False
    for key in ('card_number', 'card_holder', 'card_bank', 'sbp_phone', 'sbp_bank', 'sbp_qr_file_id', 'other_text'):
        if normalized.get(key):
            return False
    default_comment = DEFAULT_REQUISITES['comment_template']
    if normalized.get('comment_template') and normalized['comment_template'] != default_comment:
        return False
    return True


async def fetch_effective(session: AsyncSession) -> dict[str, Any]:
    stmt = (
        select(m.staff_users.commission_requisites)
        .where(
            m.staff_users.role == m.StaffRole.ADMIN,
            m.staff_users.is_active.is_(True),
        )
        .order_by(m.staff_users.updated_at.desc(), m.staff_users.id.desc())
        .limit(1)
    )
    row = await session.execute(stmt)
    data = row.scalar_one_or_none()
    return ensure_schema(data)


async def fetch_for_staff(session: AsyncSession, staff_id: int) -> dict[str, Any]:
    stmt = select(m.staff_users.commission_requisites).where(
        m.staff_users.id == staff_id
    )
    row = await session.execute(stmt)
    data = row.scalar_one_or_none()
    return ensure_schema(data)


async def update_for_staff(session: AsyncSession, staff_id: int, payload: dict[str, Any]) -> None:
    normalized = ensure_schema(payload)
    await session.execute(
        update(m.staff_users)
        .where(m.staff_users.id == staff_id)
        .values(commission_requisites=normalized, updated_at=func.now())
    )


def ensure_schema(raw: Any) -> dict[str, Any]:
    base = dict(DEFAULT_REQUISITES)
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (TypeError, ValueError):
            raw = {}
    if not isinstance(raw, dict):
        return base
    for key in base:
        value = raw.get(key)
        if isinstance(base[key], list):
            base[key] = _normalize_methods(value)
        elif value is None:
            base[key] = ""
        else:
            base[key] = str(value)
    return base


def _normalize_methods(value: Any) -> list[str]:
    if isinstance(value, list):
        items = [str(item).strip() for item in value if isinstance(item, (str, int, float))]
    elif isinstance(value, str):
        items = [part.strip() for part in value.split(",") if part.strip()]
    else:
        items = []
    normalized: list[str] = []
    for item in items:
        lowered = item.lower()
        if lowered in ALLOWED_METHODS and lowered not in normalized:
            normalized.append(lowered)
    return normalized
