# field_service/bots/admin_bot/handlers/helpers.py
"""Общие хелперы для handlers."""
from __future__ import annotations

import html
import re
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any, Optional, Sequence
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.types import Message

from field_service.config import settings as env_settings
from field_service.services import export_service, live_log, time_service
from field_service.db.models import OrderType

from ...core.dto import NewOrderAttachment, NewOrderData, StaffUser
from ...utils.normalizers import normalize_category, normalize_status
from ...core.access import visible_city_ids_for
from ...utils.helpers import get_service


# Константы
PHONE_RE = re.compile(r"^\+7\d{10}$")
NAME_RE = re.compile(r"^[A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё\- ]{1,99}$")
ATTACHMENTS_LIMIT = 10
LOG_ENTRIES_LIMIT = 20
EMPTY_PLACEHOLDER = ""

# Геттеры сервисов
def _staff_service(bot):
    return get_service(bot, "staff_service")


def _orders_service(bot):
    return get_service(bot, "orders_service")


def _masters_service(bot):
    return get_service(bot, "masters_service")


def _distribution_service(bot):
    return get_service(bot, "distribution_service")


def _finance_service(bot):
    return get_service(bot, "finance_service")


def _settings_service(bot):
    return get_service(bot, "settings_service")


# Хелперы валидации
def _normalize_phone(value: str) -> str:
    digits = re.sub(r"[^0-9]", "", value)
    if digits.startswith("8") and len(digits) == 11:
        digits = "7" + digits[1:]
    if digits.startswith("7") and len(digits) == 11:
        return "+" + digits
    if digits.startswith("+7") and len(digits) == 12:
        return digits
    return value.strip()


def _validate_phone(value: str) -> bool:
    return bool(PHONE_RE.fullmatch(value))


def _validate_name(value: str) -> bool:
    return bool(NAME_RE.fullmatch(value))


# Хелперы для FSM
def _attachments_from_state(data: dict) -> list[dict[str, Any]]:
    attachments = data.get("attachments")
    if attachments is None:
        attachments = []
        data["attachments"] = attachments
    return attachments


# Построение данных заказа
def _build_new_order_data(data: dict, staff: StaffUser) -> NewOrderData:
    attachments = [
        NewOrderAttachment(
            file_id=item["file_id"],
            file_unique_id=item.get("file_unique_id"),
            file_type=item["file_type"],
            file_name=item.get("file_name"),
            mime_type=item.get("mime_type"),
            caption=item.get("caption"),
        )
        for item in data.get("attachments", [])
    ]
    address_comment = data.get("address_comment") or None
    manual_street = data.get("street_manual")
    if manual_street:
        extra = f"(Вручную: {manual_street})"
        address_comment = f"{address_comment} {extra}".strip() if address_comment else extra
    initial_status_value = data.get("initial_status")
    initial_status = normalize_status(initial_status_value)
    total_sum_value = data.get("total_sum")
    if total_sum_value is None:
        total_sum_value = 0
    lat_value = data.get("lat")
    if lat_value is not None:
        try:
            lat_value = float(lat_value)
        except (TypeError, ValueError):
            lat_value = None
    lon_value = data.get("lon")
    if lon_value is not None:
        try:
            lon_value = float(lon_value)
        except (TypeError, ValueError):
            lon_value = None
    category_value = data.get("category")
    category_enum = normalize_category(category_value)
    if category_enum is None:
        raise ValueError("Category is required")

    return NewOrderData(
        city_id=int(data["city_id"]),
        district_id=data.get("district_id"),
        street_id=data.get("street_id"),
        house=str(data.get("house", "")) or None,
        apartment=data.get("apartment"),
        address_comment=address_comment,
        client_name=str(data.get("client_name")),
        client_phone=str(data.get("client_phone")),
        category=category_enum,
        description=str(data.get("description", "")),
        order_type=OrderType(data.get("order_type", OrderType.NORMAL.value)),
        timeslot_start_utc=data.get("timeslot_start_utc"),
        timeslot_end_utc=data.get("timeslot_end_utc"),
        timeslot_display=data.get("timeslot_display"),
        lat=lat_value,
        lon=lon_value,
        no_district=data.get("district_id") is None,
        company_payment=Decimal(data.get("company_payment", 0)),
        total_sum=Decimal(total_sum_value or 0),
        created_by_staff_id=staff.id,
        initial_status=initial_status,
        attachments=attachments,
    )


# Хелперы для города
async def _resolve_city_names(bot, city_ids: Sequence[int]) -> list[str]:
    if not city_ids:
        return []
    orders = _orders_service(bot)
    names: list[str] = []
    for city_id in city_ids:
        city = await orders.get_city(city_id)
        names.append(city.name if city else str(city_id))
    return names


def _zone_storage_value(tz: ZoneInfo) -> str:
    return getattr(tz, 'key', str(tz))


async def _resolve_city_timezone(bot: Bot, city_id: Optional[int]) -> ZoneInfo:
    if not city_id:
        return time_service.resolve_timezone()
    orders = _orders_service(bot)
    try:
        tz_value = await orders.get_city_timezone(int(city_id))
    except Exception:
        tz_value = None
    return time_service.resolve_timezone(tz_value)


# Форматирование логов
def _format_log_entries(entries: Sequence[live_log.LiveLogEntry]) -> str:
    if not entries:
        return '<b>Логи</b>'
    lines = ['<b>Логи</b>']
    LOCAL_TZ = time_service.resolve_timezone(env_settings.timezone)
    for entry in entries:
        local_time = entry.timestamp.astimezone(LOCAL_TZ)
        body = html.escape(entry.message, quote=False).replace('\n', '<br>')
        lines.append(f'[{local_time:%H:%M:%S}] <i>{entry.source}</i> — {body}')
    return '\n'.join(lines)


__all__ = [
    "PHONE_RE",
    "NAME_RE",
    "ATTACHMENTS_LIMIT",
    "LOG_ENTRIES_LIMIT",
    "EMPTY_PLACEHOLDER",
    "_staff_service",
    "_orders_service",
    "_masters_service",
    "_distribution_service",
    "_finance_service",
    "_settings_service",
    "_normalize_phone",
    "_validate_phone",
    "_validate_name",
    "_attachments_from_state",
    "_build_new_order_data",
    "_resolve_city_names",
    "_zone_storage_value",
    "_resolve_city_timezone",
    "_format_log_entries",
]
