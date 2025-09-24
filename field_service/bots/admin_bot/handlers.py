from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from decimal import Decimal
from typing import Any, Optional, Sequence

from aiogram import F, Router, Bot
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message, InlineKeyboardButton, InlineKeyboardMarkup

from field_service.config import settings as env_settings
from field_service.services import export_service, live_log, time_service
from field_service.services import settings_service
from field_service.services.onboarding_service import normalize_phone
from field_service.bots.admin_bot.services_db import AccessCodeError

FINANCE_SEGMENT_TITLES = {
    'aw': 'РћР¶РёРґР°СЋС‚ РѕРїР»Р°С‚С‹',
    'pd': 'РћРїР»Р°С‡РµРЅРЅС‹Рµ',
    'ov': 'РџСЂРѕСЃСЂРѕС‡РµРЅРЅС‹Рµ',
}

STAFF_CODE_PROMPT = "Введите код доступа, выданный глобальным администратором."
STAFF_CODE_ERROR = "Код не найден / истёк / отозван / уже использован."
STAFF_PDN_TEXT = (
    "Согласие на обработку персональных данных.\nСогласие включает обработку ФИО, телефона и данных о заказах для допуска к работе и обеспечения безопасности сервиса. Отправьте \"Согласен\" для продолжения или \"Не согласен\" для отмены."
)

from .access import visible_city_ids_for
from .dto import (
    CityRef,
    CommissionDetail,
    CommissionListItem,
    MasterBrief,
    NewOrderAttachment,
    NewOrderData,
    OrderCard,
    OrderDetail,
    OrderListItem,
    OrderType,
    OrderStatus,
    StaffRole,
    StaffUser,
    StreetRef,
)
from .filters import StaffRoleFilter
from .keyboards import (
    back_to_menu,
    finance_card_actions,
    finance_menu,
    finance_reject_cancel_keyboard,
    finance_segment_keyboard,
    main_menu,
    manual_candidates_keyboard,
    manual_confirm_keyboard,
    new_order_attachments_keyboard,
    new_order_city_keyboard,
    new_order_confirm_keyboard,
    new_order_district_keyboard,
    new_order_slot_keyboard,
    new_order_street_keyboard,
    new_order_street_manual_keyboard,
    new_order_street_mode_keyboard,
    order_card_keyboard,
)
from .keyboards import reports_menu_keyboard
from .states import (FinanceActionFSM, NewOrderFSM, OwnerPayEditFSM, ReportsExportFSM, SettingsEditFSM, StaffAccessFSM)
from .texts import (
    commission_detail as format_commission_detail,
    finance_list_line,
    master_brief_line,
    new_order_summary,
    order_card as format_order_card,
    order_teaser,
)
from .utils import get_service
from .queue import queue_router

router = Router(name="admin_handlers")
router.include_router(queue_router)

STAFF_ROLE_LABELS = {
    StaffRole.GLOBAL_ADMIN: "Global admin",
    StaffRole.CITY_ADMIN: "City admin",
    StaffRole.LOGIST: "Logist",
}

ACCESS_CODE_ERROR_MESSAGES = {
    "invalid_code": STAFF_CODE_ERROR,
    "expired": STAFF_CODE_ERROR,
    "no_cities": "Код не содержит городов. Обратитесь к глобальному администратору.",
    "already_staff": "Этот код уже использован.",
}



class _MessageEditProxy:
    __slots__ = ("bot", "chat_id", "message_id")

    def __init__(self, bot: Bot, chat_id: int, message_id: int) -> None:
        self.bot = bot
        self.chat_id = chat_id
        self.message_id = message_id

    async def edit_text(self, text: str, *, reply_markup=None, disable_web_page_preview=None) -> None:
        await self.bot.edit_message_text(
            text=text,
            chat_id=self.chat_id,
            message_id=self.message_id,
            reply_markup=reply_markup,
            disable_web_page_preview=disable_web_page_preview,
        )

LOCAL_TZ = settings_service.get_timezone()
UTC = timezone.utc
PHONE_RE = re.compile(r"^(?:\+7|8)\d{10}$")
NAME_RE = re.compile(r"^[пїЅ-ЯЁпїЅ-пїЅпїЅ\-\s]{2,30}$")
ATTACHMENTS_LIMIT = 5
CATEGORY_CHOICES = [
    ("ELECTRICS", "пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ"),
    ("PLUMBING", "пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ"),
    ("APPLIANCES", "пїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅ"),
    ("WINDOWS", "пїЅпїЅпїЅпїЅ"),
    ("HANDYMAN", "пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ"),
    ("ROADSIDE", "пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ"),
]
CATEGORY_LABELS = {code: label for code, label in CATEGORY_CHOICES}
SLOT_BUCKETS = (
    ("10-13", time(10, 0), time(13, 0)),
    ("13-16", time(13, 0), time(16, 0)),
    ("16-19", time(16, 0), time(19, 0)),
)
WORKDAY_START_DEFAULT = time_service.parse_time_string(env_settings.workday_start, default=time(10, 0))
WORKDAY_END_DEFAULT = time_service.parse_time_string(env_settings.workday_end, default=time(20, 0))
LATE_ASAP_THRESHOLD = time_service.parse_time_string(env_settings.asap_late_threshold, default=time(19, 30))

REPORT_DEFINITIONS: dict[str, tuple[str, Any, str]] = {
    "orders": ("заказы", export_service.export_orders, "Orders"),
    "commissions": ("комиссии", export_service.export_commissions, "Commissions"),
    "ref_rewards": ("реферальные начисления", export_service.export_referral_rewards, "Referral rewards"),
}

DATE_INPUT_FORMATS = ("%Y-%m-%d", "%d.%m.%Y")
@dataclass(frozen=True)
class SettingFieldDef:
    key: str
    label: str
    schema: str
    value_type: str = "STR"
    choices: tuple[tuple[str, str], ...] | None = None
    help_text: str = ""
    default: object | None = None


@dataclass(frozen=True)
class SettingGroupDef:
    key: str
    title: str
    fields: tuple[SettingFieldDef, ...]
    description: str = ""


SETTING_GROUPS: dict[str, SettingGroupDef] = {
    "workday": SettingGroupDef(
        key="workday",
        title="?? пїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅ",
        description="пїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅ DEFERRED пїЅ SEARCHING.",
        fields=(
            SettingFieldDef(
                key="working_hours_start",
                label="пїЅпїЅпїЅпїЅпїЅпїЅ",
                schema="time",
                value_type="TIME",
                default=env_settings.working_hours_start,
                help_text="пїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅ:пїЅпїЅ, пїЅпїЅпїЅпїЅпїЅпїЅ 10:00.",
            ),
            SettingFieldDef(
                key="working_hours_end",
                label="пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ",
                schema="time",
                value_type="TIME",
                default=env_settings.working_hours_end,
                help_text="пїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅ:пїЅпїЅ, пїЅпїЅпїЅпїЅпїЅпїЅ 20:00.",
            ),
        ),
    ),
    "distribution": SettingGroupDef(
        key="distribution",
        title="?? пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ",
        description="пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅ SLA пїЅпїЅпїЅпїЅпїЅпїЅпїЅ.",
        fields=(
            SettingFieldDef(
                key="distribution_tick_seconds",
                label="пїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ (пїЅпїЅпїЅ)",
                schema="int",
                value_type="INT",
                default=30,
            ),
            SettingFieldDef(
                key="distribution_sla_seconds",
                label="SLA пїЅпїЅпїЅпїЅпїЅпїЅ (пїЅпїЅпїЅ)",
                schema="int",
                value_type="INT",
                default=env_settings.distribution_sla_seconds,
            ),
            SettingFieldDef(
                key="distribution_rounds",
                label="пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅ",
                schema="int",
                value_type="INT",
                default=env_settings.distribution_rounds,
            ),
            SettingFieldDef(
                key="escalate_to_admin_after_min",
                label="пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅ (пїЅпїЅпїЅ)",
                schema="int_non_negative",
                value_type="INT",
                default=10,
            ),
            SettingFieldDef(
                key="distribution_log_topn",
                label="пїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ",
                schema="int",
                value_type="INT",
                default=10,
            ),
        ),
    ),
    "limits": SettingGroupDef(
        key="limits",
        title="?? пїЅпїЅпїЅпїЅпїЅпїЅ",
        fields=(
            SettingFieldDef(
                key="max_active_orders",
                label="пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅ",
                schema="int",
                value_type="INT",
                default=1,
            ),
        ),
    ),
    "support": SettingGroupDef(
        key="support",
        title="?? пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ",
        description="пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ.",
        fields=(
            SettingFieldDef(
                key="support_contact",
                label="пїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ",
                schema="string",
                value_type="STR",
                help_text="пїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅ, @username пїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅ.",
            ),
            SettingFieldDef(
                key="support_faq_url",
                label="пїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅ FAQ",
                schema="string_optional",
                value_type="STR",
                help_text="пїЅпїЅпїЅпїЅпїЅпїЅпїЅ URL пїЅпїЅпїЅ '-' пїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ.",
            ),
        ),
    ),
    "geo": SettingGroupDef(
        key="geo",
        title="??? пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ",
        fields=(
            SettingFieldDef(
                key="geo_mode",
                label="пїЅпїЅпїЅпїЅпїЅ",
                schema="choice",
                value_type="STR",
                choices=(
                    ("local_centroids", "пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ"),
                    ("yandex", "пїЅпїЅпїЅпїЅпїЅпїЅ"),
                ),
                default="local_centroids",
                help_text="1 пїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ, 2 пїЅ пїЅпїЅпїЅпїЅпїЅпїЅ API.",
            ),
            SettingFieldDef(
                key="yandex_geocoder_key",
                label="API пїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅ",
                schema="string_optional",
                value_type="STR",
                help_text="пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅ пїЅпїЅпїЅ '-' пїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ.",
            ),
            SettingFieldDef(
                key="yandex_throttle_rps",
                label="RPS пїЅпїЅпїЅпїЅпїЅ",
                schema="int_non_negative",
                value_type="INT",
                default=1,
            ),
            SettingFieldDef(
                key="yandex_daily_limit",
                label="пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅ",
                schema="int_non_negative",
                value_type="INT",
                default=1000,
            ),
        ),
    ),
    "channels": SettingGroupDef(
        key="channels",
        title="?? пїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ",
        description="пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅ пїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅ.",
        fields=(
            SettingFieldDef(
                key="alerts_channel_id",
                label="Alerts / пїЅпїЅпїЅпїЅпїЅпїЅ",
                schema="int_optional",
                value_type="STR",
                help_text="ID пїЅпїЅпїЅпїЅ пїЅпїЅпїЅ '-' пїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ.",
            ),
            SettingFieldDef(
                key="logs_channel_id",
                label="пїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅ",
                schema="int_optional",
                value_type="STR",
                help_text="ID пїЅпїЅпїЅпїЅ пїЅпїЅпїЅ '-' пїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ.",
            ),
            SettingFieldDef(
                key="reports_channel_id",
                label="пїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅ",
                schema="int_optional",
                value_type="STR",
                help_text="ID пїЅпїЅпїЅпїЅ пїЅпїЅпїЅ '-' пїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ.",
            ),
        ),
    ),
}

SETTING_FIELD_BY_KEY: dict[str, SettingFieldDef] = {
    field.key: field
    for group in SETTINGS_GROUPS.values()
    for field in group.fields
}

SETTING_FIELD_GROUP: dict[str, str] = {
    field.key: group.key
    for group in SETTINGS_GROUPS.values()
    for field in group.fields
}


EMPTY_PLACEHOLDER = "пїЅ"
SCHEMA_DEFAULT_HELP = {
    "time": "пїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅ:пїЅпїЅ, пїЅпїЅпїЅпїЅпїЅпїЅ 10:00.",
    "int": "пїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅ 0.",
    "int_non_negative": "пїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅ пїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅ 0.",
    "string": "пїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅ.",
    "string_optional": "пїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅ '-' пїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ.",
    "int_optional": "пїЅпїЅпїЅпїЅпїЅпїЅпїЅ ID пїЅпїЅпїЅпїЅ пїЅпїЅпїЅ '-' пїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ.",
    "choice": "пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ." ,
}
LOG_ENTRIES_LIMIT = 20


def _get_setting_group(group_key: str) -> SettingGroupDef:
    group = SETTING_GROUPS.get(group_key)
    if group is None:
        raise KeyError(f"Unknown settings group: {group_key}")
    return group


def _get_setting_field(field_key: str) -> SettingFieldDef:
    field = SETTING_FIELD_BY_KEY.get(field_key)
    if field is None:
        raise KeyError(f"Unknown setting field: {field_key}")
    return field


def _format_setting_value(field: SettingFieldDef, raw_value: Optional[str]) -> tuple[str, bool]:
    value = raw_value
    from_default = False
    if value in (None, ""):
        value = field.default
        from_default = raw_value in (None, "") and value not in (None, "")
    if value in (None, ""):
        return EMPTY_PLACEHOLDER, False
    if field.schema == "choice" and field.choices:
        text_value = str(value)
        for idx, (code, label) in enumerate(field.choices, 1):
            if text_value == code:
                return f"{label} ({code})", from_default
    return str(value), from_default


def _choice_help(field: SettingFieldDef) -> str:
    if not field.choices:
        return ""
    lines = []
    for idx, (code, label) in enumerate(field.choices, 1):
        lines.append(f"{idx}. {label} ({code})")
    return "".join(lines)


def _build_setting_prompt(field: SettingFieldDef, current_display: str) -> str:
    lines = [f"<b>{field.label}</b>"]
    if current_display and current_display != EMPTY_PLACEHOLDER:
        lines.append(f"пїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ: <code>{html.escape(current_display, quote=False)}</code>")
    base_help = SCHEMA_DEFAULT_HELP.get(field.schema, "пїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ.")
    if field.schema == "choice":
        options = _choice_help(field)
        if options:
            lines.append(base_help)
            lines.append(options)
        else:
            lines.append(base_help)
    else:
        lines.append(field.help_text or base_help)
    lines.append("пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ /cancel пїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅ.")
    return "".join(lines)


def _parse_setting_input(field: SettingFieldDef, user_input: str) -> tuple[str, str]:
    text = (user_input or "").strip()
    if field.schema in {"string_optional", "int_optional"} and text in {"", "-"}:
        return "", field.value_type
    if field.schema == "time":
        if not re.fullmatch(r"^\d{1,2}:\d{2}$", text):
            raise ValueError("пїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅ пїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅ:пїЅпїЅ.")
        hh, mm = map(int, text.split(":"))
        if not (0 <= hh < 24 and 0 <= mm < 60):
            raise ValueError("пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅ.")
        return text, field.value_type
    if field.schema == "int":
        try:
            value = int(text)
        except ValueError:
            raise ValueError("пїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅ.")
        if value <= 0:
            raise ValueError("пїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅ 0.")
        return str(value), field.value_type
    if field.schema == "int_non_negative":
        try:
            value = int(text)
        except ValueError:
            raise ValueError("пїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅ.")
        if value < 0:
            raise ValueError("пїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅ пїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅ 0.")
        return str(value), field.value_type
    if field.schema == "int_optional":
        try:
            value = int(text)
        except ValueError:
            raise ValueError("пїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅ '-' пїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅ.")
        return str(value), field.value_type
    if field.schema == "choice":
        normalized = text.lower()
        if field.choices:
            for idx, (code, label) in enumerate(field.choices, 1):
                if normalized in {code.lower(), label.lower(), str(idx)}:
                    return code, field.value_type
        raise ValueError("пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅ.")
    if field.schema == "string_optional":
        return text, field.value_type
    if field.schema == "string":
        if not text:
            raise ValueError("пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅ пїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅ.")
        return text, field.value_type
    raise ValueError("пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ.")


async def _build_settings_view(bot, group_key: str) -> tuple[str, InlineKeyboardMarkup]:
    group = _get_setting_group(group_key)
    service = _settings_service(bot)
    raw_map = await service.get_values([field.key for field in group.fields])
    lines: list[str] = [f"<b>{group.title}</b>"]
    if group.description:
        lines.append(group.description)
    for field in group.fields:
        raw_value = raw_map.get(field.key, (None, None))[0]
        display, from_default = _format_setting_value(field, raw_value)
        if display == EMPTY_PLACEHOLDER:
            value_line = f"{field.label}: {EMPTY_PLACEHOLDER}"
        else:
            value_line = f"{field.label}: <code>{html.escape(display, quote=False)}</code>"
        if from_default and field.default not in (None, ""):
            value_line += " <i>(пїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ)</i>"
        lines.append(value_line)
    lines.append("пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ.")
    keyboard = settings_group_keyboard(
        group_key,
        [(field.key, field.label) for field in group.fields],
    )
    return "".join(lines), keyboard

def _format_log_entries(entries: Sequence[live_log.LiveLogEntry]) -> str:
    if not entries:
        return '<b>История пуста</b>'

    lines = ['<b>История событий</b>']
    for entry in entries:
        local_time = entry.timestamp.astimezone(LOCAL_TZ)
        body = html.escape(entry.message, quote=False).replace('\n', '<br>')
        lines.append(f'[{local_time:%H:%M:%S}] <i>{entry.source}</i> — {body}')
    return '\n'.join(lines)

def _staff_service(bot):
    return get_service(bot, "staff_service")


def _orders_service(bot):
    return get_service(bot, "orders_service")


async def _resolve_city_names(bot, city_ids: Sequence[int]) -> list[str]:
    if not city_ids:
        return []
    orders = _orders_service(bot)
    names: list[str] = []
    for city_id in city_ids:
        city = await orders.get_city(city_id)
        names.append(city.name if city else str(city_id))
    return names


def _masters_service(bot):
    return get_service(bot, "masters_service")


def _distribution_service(bot):
    return get_service(bot, "distribution_service")


def _finance_service(bot):
    return get_service(bot, "finance_service")


def _settings_service(bot):
    return get_service(bot, "settings_service")


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


def _attachments_from_state(data: dict) -> list[dict[str, Any]]:
    attachments = data.get("attachments")
    if attachments is None:
        attachments = []
        data["attachments"] = attachments
    return attachments


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
        extra = f"(???????????????: {manual_street})"
        address_comment = f"{address_comment} {extra}".strip() if address_comment else extra
    initial_status_value = data.get("initial_status")
    initial_status = None
    if isinstance(initial_status_value, OrderStatus):
        initial_status = initial_status_value
    elif isinstance(initial_status_value, str):
        try:
            initial_status = OrderStatus(initial_status_value)
        except ValueError:
            initial_status = None
    return NewOrderData(
        city_id=int(data["city_id"]),
        district_id=data.get("district_id"),
        street_id=data.get("street_id"),
        house=str(data.get("house", "")) or None,
        apartment=data.get("apartment"),
        address_comment=address_comment,
        client_name=str(data.get("client_name")),
        client_phone=str(data.get("client_phone")),
        category=str(data.get("category")),
        description=str(data.get("description", "")),
        order_type=OrderType(data.get("order_type", OrderType.NORMAL.value)),
        scheduled_date=data.get("scheduled_date"),
        time_slot_start=data.get("time_slot_start"),
        time_slot_end=data.get("time_slot_end"),
        slot_label=data.get("slot_label"),
        latitude=None,
        longitude=None,
        company_payment=Decimal(data.get("company_payment", 0)),
        total_price=Decimal(data.get("total_price", 0)),
        created_by_staff_id=staff.id,
        initial_status=initial_status,
        attachments=attachments,
    )



def _slot_options(
    now_local: datetime,
    *,
    workday_start: time,
    workday_end: time,
) -> list[tuple[str, str]]:
    current = now_local.timetz()
    if current.tzinfo is not None:
        current = current.replace(tzinfo=None)
    options: list[tuple[str, str]] = []
    if current < workday_end:
        options.append(("ASAP", "ASAP"))
        for bucket_key, start, end in SLOT_BUCKETS:
            if current < start:
                options.append((f"TODAY:{bucket_key}", f"??????? {start:%H:%M}-{end:%H:%M}"))
    for bucket_key, start, end in SLOT_BUCKETS:
        options.append((f"TOM:{bucket_key}", f"?????? {start:%H:%M}-{end:%H:%M}"))
    return options


def _format_slot_display(
    choice: str,
    computation: time_service.SlotComputation,
    *,
    tz: ZoneInfo,
) -> str:
    if choice == "ASAP":
        return "ASAP"
    today = time_service.now_in_city(tz).date()
    scheduled = computation.scheduled_date
    if scheduled == today:
        prefix = "???????"
    elif scheduled == today + timedelta(days=1):
        prefix = "??????"
    else:
        prefix = scheduled.strftime("%d.%m")
    return f"{prefix} {computation.start_local:%H:%M}-{computation.end_local:%H:%M}"


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


async def _resolve_workday_window() -> tuple[time, time]:
    try:
        return await settings_service.get_working_window()
    except Exception:
        return WORKDAY_START_DEFAULT, WORKDAY_END_DEFAULT



async def _finalize_slot_selection(
    message: Message,
    state: FSMContext,
    *,
    slot_choice: str,
    tz: ZoneInfo,
    workday_start: time,
    workday_end: time,
    initial_status_override: Optional[OrderStatus] = None,
) -> None:
    computation = time_service.compute_slot(
        city_tz=tz,
        choice=slot_choice,
        workday_start=workday_start,
        workday_end=workday_end,
    )
    slot_display = _format_slot_display(slot_choice, computation, tz)
    await state.update_data(
        slot_label=slot_display,
        slot_label_display=slot_display,
        scheduled_date=computation.scheduled_date,
        time_slot_start=computation.start_local,
        time_slot_end=computation.end_local,
        initial_status=initial_status_override,
        pending_asap=False,
    )
    summary = new_order_summary(await state.get_data())
    await state.set_state(NewOrderFSM.confirm)
    await message.edit_text(
        summary,
        reply_markup=new_order_confirm_keyboard(),
        disable_web_page_preview=True,
    )



def _send_export_documents(message: Message, bundle: export_service.ExportBundle, caption: str) -> None:
    documents = [
        (bundle.csv_bytes, bundle.csv_filename, f"{caption} - CSV"),
        (bundle.xlsx_bytes, bundle.xlsx_filename, f"{caption} - XLSX"),
    ]
    for payload, filename, note in documents:
        file = BufferedInputFile(payload, filename)
        message.bot.loop.create_task(message.answer_document(file, caption=note))

@router.message(CommandStart(), StaffRoleFilter({StaffRole.GLOBAL_ADMIN, StaffRole.CITY_ADMIN, StaffRole.LOGIST}))
async def admin_start(message: Message, staff: StaffUser) -> None:
    await message.answer(
        "пїЅпїЅпїЅпїЅпїЅ-пїЅпїЅпїЅ Field Service. пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅ:",
        reply_markup=main_menu(staff),
    )


@router.message(CommandStart())
async def not_allowed_start(message: Message, state: FSMContext) -> None:
    staff_service = _staff_service(message.bot)
    user_id = message.from_user.id if message.from_user else None
    staff = await staff_service.get_by_tg_id(user_id) if user_id else None
    if staff:
        await state.clear()
        await message.answer("Вы уже авторизованы.", reply_markup=main_menu(staff))
        return
    await state.clear()
    await state.set_state(StaffAccessFSM.code)
    await message.answer(STAFF_CODE_PROMPT)


@router.message(StateFilter(StaffAccessFSM.code))
async def staff_access_enter_code(message: Message, state: FSMContext) -> None:
    code_value = (message.text or "").strip()
    if not code_value:
        await message.answer("Введите код доступа.")
        return
    staff_service = _staff_service(message.bot)
    record = await staff_service.validate_access_code_value(code_value)
    if not record:
        await message.answer(STAFF_CODE_ERROR)
        return
    role_label = STAFF_ROLE_LABELS.get(record.role, record.role.value)
    city_names = await _resolve_city_names(message.bot, record.city_ids)
    await state.update_data(
        access_code=record.code,
        access_code_id=record.id,
        access_role=record.role.value,
        access_city_ids=list(record.city_ids),
    )
    summary_lines = [
        f"Роль: {role_label}",
        f"Города: {', '.join(city_names) if city_names else '-'}",
    ]
    await message.answer("\n".join(summary_lines))
    await state.set_state(StaffAccessFSM.pdn)
    await message.answer(STAFF_PDN_TEXT)


@router.message(StateFilter(StaffAccessFSM.pdn))
async def staff_access_pdn(message: Message, state: FSMContext) -> None:
    text_value = (message.text or "").strip().lower()
    if text_value in {"не согласен", "нет", "no"}:
        await state.clear()
        await message.answer("Без согласия продолжить нельзя. Отправьте /start, если передумаете.")
        return
    if text_value not in {"согласен", "да", "ok", "хорошо"}:
        await message.answer('Отправьте "Согласен" или "Не согласен".')
        return
    await state.set_state(StaffAccessFSM.full_name)
    await message.answer("Введите ФИО полностью (например, Иванов Иван Иванович).")


@router.message(StateFilter(StaffAccessFSM.full_name))
async def staff_access_full_name(message: Message, state: FSMContext) -> None:
    full_name = (message.text or "").strip()
    if len(full_name) < 5:
        await message.answer("Введите ФИО полностью.")
        return
    await state.update_data(full_name=full_name)
    await state.set_state(StaffAccessFSM.phone)
    await message.answer("Введите телефон в формате +7XXXXXXXXXX или 8XXXXXXXXXX.")


@router.message(StateFilter(StaffAccessFSM.phone))
async def staff_access_phone(message: Message, state: FSMContext) -> None:
    raw_phone = (message.text or "").strip()
    try:
        normalized = normalize_phone(raw_phone)
    except ValueError:
        await message.answer("Неверный формат телефона. Пример: +7XXXXXXXXXX или 8XXXXXXXXXX")
        return
    data = await state.get_data()
    code_value = data.get("access_code")
    full_name = data.get("full_name")
    role_token = data.get("access_role")
    if not code_value or not full_name or not role_token:
        await state.clear()
        await message.answer("Сессия истекла. Отправьте /start и попробуйте снова.")
        return
    user = message.from_user
    if not user:
        await message.answer("Не удалось получить данные пользователя.")
        return
    staff_service = _staff_service(message.bot)
    try:
        staff_user = await staff_service.register_staff_user_from_code(
            code_value=code_value,
            tg_user_id=user.id,
            username=user.username,
            full_name=full_name,
            phone=normalized,
        )
    except AccessCodeError as exc:
        error_text = ACCESS_CODE_ERROR_MESSAGES.get(
            exc.reason,
            "Не удалось применить код. Обратитесь к глобальному администратору.",
        )
        await message.answer(error_text)
        await state.set_state(StaffAccessFSM.code)
        await message.answer(STAFF_CODE_PROMPT)
        return
    await state.clear()
    role_label = STAFF_ROLE_LABELS.get(staff_user.role, staff_user.role.value)
    city_names = await _resolve_city_names(message.bot, staff_user.city_ids)
    lines = [
        f"Вы добавлены как {role_label}.",
        f"Города: {', '.join(city_names) if city_names else '-'}",
    ]
    await message.answer("\n".join(lines))
    await message.answer("Готово. Главное меню:", reply_markup=main_menu(staff_user))


@router.callback_query(
    F.data == "adm:menu",
    StaffRoleFilter({StaffRole.GLOBAL_ADMIN, StaffRole.CITY_ADMIN, StaffRole.LOGIST}),
)
async def cb_menu(cq: CallbackQuery, staff: StaffUser) -> None:
    await cq.message.edit_text("пїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅ:", reply_markup=main_menu(staff))
    await cq.answer()


@router.callback_query(
    F.data == "adm:f",
    StaffRoleFilter({StaffRole.GLOBAL_ADMIN, StaffRole.CITY_ADMIN}),
)
async def cb_finance_root(cq: CallbackQuery, staff: StaffUser, state: FSMContext) -> None:
    await state.clear()
    await cq.message.edit_text("Р’С‹Р±РµСЂРёС‚Рµ СЂР°Р·РґРµР»:", reply_markup=finance_menu(staff))
    await cq.answer()


async def _render_finance_segment(
    message: Message,
    staff: StaffUser,
    segment: str,
    page: int,
    state: FSMContext,
) -> None:
    finance_service = _finance_service(message.bot)
    rows, has_next = await finance_service.list_commissions(
        segment,
        page=page,
        page_size=10,
        city_ids=visible_city_ids_for(staff),
    )

    await state.update_data(fin_segment=segment, fin_page=page)

    title = FINANCE_SEGMENT_TITLES.get(segment, segment.upper())
    if not rows:
        text = f"<b>{title}</b>\nРљРѕРјРёСЃСЃРёРё РЅРµ РЅР°Р№РґРµРЅС‹."
    else:
        lines = [f"<b>{title}</b>", ""]
        for row in rows:
            if isinstance(row, CommissionListItem):
                lines.append(f"вЂў {html.escape(finance_list_line(row))}")
            else:
                lines.append(f"вЂў {html.escape(str(row))}")
        text = "\n".join(lines)

    button_rows: list[list[InlineKeyboardButton]] = []
    for row in rows:
        if isinstance(row, CommissionListItem):
            label = f"#{row.id} В· {row.amount:.0f} в‚Ѕ"
            button_rows.append([
                InlineKeyboardButton(
                    text=label,
                    callback_data=f"adm:f:cm:card:{row.id}",
                )
            ])

    nav_markup = finance_segment_keyboard(segment, page=page, has_next=has_next)
    button_rows.extend(nav_markup.inline_keyboard)
    markup = InlineKeyboardMarkup(inline_keyboard=button_rows)

    await message.edit_text(text, reply_markup=markup)


@router.callback_query(
    F.data.startswith("adm:f:aw:"),
    StaffRoleFilter({StaffRole.GLOBAL_ADMIN, StaffRole.CITY_ADMIN}),
)
async def cb_finance_aw(cq: CallbackQuery, staff: StaffUser, state: FSMContext) -> None:
    page = int(cq.data.split(":")[2])
    await _render_finance_segment(cq.message, staff, "aw", page, state)
    await cq.answer()


@router.callback_query(
    F.data.startswith("adm:f:pd:"),
    StaffRoleFilter({StaffRole.GLOBAL_ADMIN, StaffRole.CITY_ADMIN}),
)
async def cb_finance_pd(cq: CallbackQuery, staff: StaffUser, state: FSMContext) -> None:
    page = int(cq.data.split(":")[2])
    await _render_finance_segment(cq.message, staff, "pd", page, state)
    await cq.answer()


@router.callback_query(
    F.data.startswith("adm:f:ov:"),
    StaffRoleFilter({StaffRole.GLOBAL_ADMIN, StaffRole.CITY_ADMIN}),
)
async def cb_finance_ov(cq: CallbackQuery, staff: StaffUser, state: FSMContext) -> None:
    page = int(cq.data.split(":")[2])
    await _render_finance_segment(cq.message, staff, "ov", page, state)
    await cq.answer()


@router.callback_query(
    F.data.startswith("adm:f:cm"),
    StaffRoleFilter({StaffRole.GLOBAL_ADMIN, StaffRole.CITY_ADMIN}),
)
async def cb_finance_card(cq: CallbackQuery, staff: StaffUser, state: FSMContext) -> None:
    parts = cq.data.split(":")
    action = parts[2]
    commission_id = int(parts[3])
    finance_service = _finance_service(cq.message.bot)
    detail = await finance_service.get_commission_detail(commission_id)
    if not detail:
        await cq.answer("РљРѕРјРёСЃСЃРёСЏ РЅРµ РЅР°Р№РґРµРЅР°.", show_alert=True)
        return

    data = await state.get_data()
    segment = data.get("fin_segment", "aw")
    page = int(data.get("fin_page", 1))

    text_body = format_commission_detail(detail)

    if action == "card":
        await state.set_state(None)
        markup = finance_card_actions(detail, segment, page)
        await cq.message.edit_text(
            text_body,
            reply_markup=markup,
            disable_web_page_preview=True,
        )
        await cq.answer()
        return

    if action == "open":
        if not detail.attachments:
            await cq.answer("Р§РµРєРё РѕС‚СЃСѓС‚СЃС‚РІСѓСЋС‚.", show_alert=True)
            return
        for attachment in detail.attachments:
            try:
                file_type = (attachment.file_type or "").upper()
                if file_type == "PHOTO":
                    await cq.message.answer_photo(attachment.file_id, caption=attachment.caption)
                else:
                    await cq.message.answer_document(attachment.file_id, caption=attachment.caption)
            except TelegramBadRequest:
                await cq.message.answer("РќРµ СѓРґР°Р»РѕСЃСЊ РїРѕРєР°Р·Р°С‚СЊ РІР»РѕР¶РµРЅРёРµ С‡РµРєР°.")
        await cq.answer()
        return

    if action == "ok":
        await state.set_state(FinanceActionFSM.approve_amount)
        await state.update_data(
            commission_id=commission_id,
            segment=segment,
            page=page,
            default_amount=f"{detail.amount:.2f}",
            source_chat_id=cq.message.chat.id,
            source_message_id=cq.message.message_id,
        )
        prompt = (
            "Р’РІРµРґРёС‚Рµ С„Р°РєС‚РёС‡РµСЃРєСѓСЋ СЃСѓРјРјСѓ РѕРїР»Р°С‚С‹ (РїРѕ СѓРјРѕР»С‡Р°РЅРёСЋ {amount:.2f}).\n"
            "РћС‚РїСЂР°РІСЊС‚Рµ /skip, С‡С‚РѕР±С‹ РѕСЃС‚Р°РІРёС‚СЊ Р·РЅР°С‡РµРЅРёРµ Р±РµР· РёР·РјРµРЅРµРЅРёР№."
        ).format(amount=detail.amount)
        await cq.message.edit_text(
            f"{text_body}\n\n{prompt}",
            reply_markup=finance_reject_cancel_keyboard(commission_id),
            disable_web_page_preview=True,
        )
        await cq.answer()
        return

    if action == "blk":
        ok = await finance_service.block_master_for_overdue(
            detail.master_id or 0,
            by_staff_id=staff.id,
        )
        await cq.answer(
            "РњР°СЃС‚РµСЂ Р·Р°Р±Р»РѕРєРёСЂРѕРІР°РЅ." if ok else "РќРµ СѓРґР°Р»РѕСЃСЊ Р·Р°Р±Р»РѕРєРёСЂРѕРІР°С‚СЊ РјР°СЃС‚РµСЂР°.",
            show_alert=not ok,
        )
        proxy = _MessageEditProxy(cq.message.bot, cq.message.chat.id, cq.message.message_id)
        await _render_finance_segment(proxy, staff, "ov", page=1, state=state)
        if ok:
            live_log.push("finance", f"commission#{commission_id} blocked by staff {staff.id}")
        return

    if action == "rej":
        await state.set_state(FinanceActionFSM.reject_reason)
        await state.update_data(
            commission_id=commission_id,
            segment=segment,
            page=page,
            source_chat_id=cq.message.chat.id,
            source_message_id=cq.message.message_id,
        )
        await cq.message.edit_text(
            "РЈРєР°Р¶РёС‚Рµ РїСЂРёС‡РёРЅСѓ РѕС‚РєР»РѕРЅРµРЅРёСЏ РїР»Р°С‚РµР¶Р° (С‚РµРєСЃС‚РѕРј) РёР»Рё РЅР°Р¶РјРёС‚Рµ В«РќР°Р·Р°РґВ».",
            reply_markup=finance_reject_cancel_keyboard(commission_id),
        )
        await cq.answer()
        return

    await cq.answer()
@router.message(StateFilter(FinanceActionFSM.reject_reason))
async def finance_reject_reason(msg: Message, staff: StaffUser, state: FSMContext) -> None:
    reason = (msg.text or "").strip()
    if len(reason) < 3:
        await msg.answer("РўРµРєСЃС‚ РґРѕР»Р¶РµРЅ СЃРѕРґРµСЂР¶Р°С‚СЊ РЅРµ РјРµРЅРµРµ 3 СЃРёРјРІРѕР»РѕРІ.")
        return

    data = await state.get_data()
    commission_id = data.get("commission_id")
    segment = data.get("segment", "aw")
    page = int(data.get("page", 1))
    source_chat_id = data.get("source_chat_id")
    source_message_id = data.get("source_message_id")

    if not commission_id:
        await state.clear()
        await msg.answer("РЎРµСЃСЃРёСЏ РёСЃС‚РµРєР»Р°. РћС‚РєСЂРѕР№С‚Рµ РєР°СЂС‚РѕС‡РєСѓ РєРѕРјРёСЃСЃРёРё Р·Р°РЅРѕРІРѕ.")
        return

    finance_service = _finance_service(msg.bot)
    ok = await finance_service.reject(int(commission_id), reason=reason, by_staff_id=staff.id)
    await state.clear()
    if ok:
        live_log.push("finance", f"commission#{commission_id} rejected by staff {staff.id}")
        await msg.answer("РћС‚РїСЂР°РІР»РµРЅРѕ РјР°СЃС‚РµСЂСѓ РЅР° РґРѕСЂР°Р±РѕС‚РєСѓ.")
    else:
        await msg.answer("РќРµ СѓРґР°Р»РѕСЃСЊ РѕС‚РєР»РѕРЅРёС‚СЊ РѕРїР»Р°С‚Сѓ.")
        return

    if source_chat_id and source_message_id:
        proxy = _MessageEditProxy(msg.bot, source_chat_id, source_message_id)
        await _render_finance_segment(proxy, staff, segment, page, state)
@router.message(StateFilter(FinanceActionFSM.approve_amount))
async def finance_approve_amount(msg: Message, staff: StaffUser, state: FSMContext) -> None:
    data = await state.get_data()
    commission_id = data.get("commission_id")
    if not commission_id:
        await state.clear()
        await msg.answer("РЎРµСЃСЃРёСЏ РїРѕРґС‚РІРµСЂР¶РґРµРЅРёСЏ РёСЃС‚РµРєР»Р°. РћС‚РєСЂРѕР№С‚Рµ РєРѕРјРёСЃСЃРёСЋ Р·Р°РЅРѕРІРѕ.")
        return

    segment = data.get("segment", "aw")
    page = int(data.get("page", 1))
    source_chat_id = data.get("source_chat_id")
    source_message_id = data.get("source_message_id")
    default_amount = Decimal(data.get("default_amount", "0"))

    text_value = (msg.text or "").strip()
    if text_value.lower() == "/cancel":
        await state.clear()
        if source_chat_id and source_message_id:
            proxy = _MessageEditProxy(msg.bot, source_chat_id, source_message_id)
            await _render_finance_segment(proxy, staff, segment, page, state)
        await msg.answer("РџРѕРґС‚РІРµСЂР¶РґРµРЅРёРµ РѕС‚РјРµРЅРµРЅРѕ.")
        return

    if text_value.lower() in {"/skip", "skip", "РїСЂРѕРїСѓСЃС‚РёС‚СЊ", ""}:
        amount = default_amount
    else:
        normalized = text_value.replace(",", ".")
        if not re.fullmatch(r"^\d{1,7}(?:\.\d{1,2})?$", normalized):
            await msg.answer("Р’РІРµРґРёС‚Рµ СЃСѓРјРјСѓ РІ С„РѕСЂРјР°С‚Рµ 3500 РёР»Рё 4999.99, Р»РёР±Рѕ РѕС‚РїСЂР°РІСЊС‚Рµ /skip.")
            return
        amount = Decimal(normalized)

    finance_service = _finance_service(msg.bot)
    ok = await finance_service.approve(int(commission_id), paid_amount=amount, by_staff_id=staff.id)
    await state.clear()
    if ok:
        live_log.push("finance", f"commission#{commission_id} approved by staff {staff.id} amount={amount}")
        await msg.answer("РљРѕРјРёСЃСЃРёСЏ РїРѕРґС‚РІРµСЂР¶РґРµРЅР°.")
        if source_chat_id and source_message_id:
            proxy = _MessageEditProxy(msg.bot, source_chat_id, source_message_id)
            await _render_finance_segment(proxy, staff, segment, page, state)
    else:
        await msg.answer("РќРµ СѓРґР°Р»РѕСЃСЊ РїРѕРґС‚РІРµСЂРґРёС‚СЊ РѕРїР»Р°С‚Сѓ.")

@router.callback_query(
    F.data == "adm:f:set",
    StaffRoleFilter({StaffRole.GLOBAL_ADMIN}),
)
async def cb_finance_owner_snapshot(cq: CallbackQuery) -> None:
    settings_service = _settings_service(cq.message.bot)
    snapshot = await settings_service.get_owner_pay_snapshot()
    text = "<b>пїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ</b>\n" + json.dumps(snapshot, ensure_ascii=False, indent=2)
    keyboard = finance_reject_cancel_keyboard(0)
    await cq.message.edit_text(text, reply_markup=keyboard)
    await cq.answer()


@router.callback_query(
    F.data == "adm:f:set:edit",
    StaffRoleFilter({StaffRole.GLOBAL_ADMIN}),
)
async def cb_finance_owner_edit(cq: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(OwnerPayEditFSM.value)
    await cq.message.edit_text(
        "пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ JSON пїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ (methods, card, sbp пїЅ пїЅ.пїЅ.), пїЅпїЅпїЅ /cancel.",
    )
    await cq.answer()


@router.message(StateFilter(OwnerPayEditFSM.value))
async def finance_owner_edit_value(msg: Message, state: FSMContext) -> None:
    try:
        payload = json.loads(msg.text)
    except json.JSONDecodeError:
        await msg.answer("пїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ JSON. пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅ пїЅпїЅпїЅ пїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ /cancel.")
        return
    settings_service = _settings_service(msg.bot)
    await settings_service.update_owner_pay_snapshot(**payload)
    await state.clear()
    await msg.answer("пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ.")


@router.message(StateFilter(OwnerPayEditFSM.value), F.text == "/cancel")
async def finance_owner_edit_cancel(msg: Message, state: FSMContext) -> None:
    await state.clear()
    await msg.answer("пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ.")
@router.callback_query(
    F.data == "adm:r",
    StaffRoleFilter({StaffRole.GLOBAL_ADMIN, StaffRole.CITY_ADMIN}),
)
async def cb_reports(cq: CallbackQuery, staff: StaffUser, state: FSMContext) -> None:
    await state.clear()
    await cq.message.edit_text("Отчёты:", reply_markup=reports_menu_keyboard())
    await cq.answer()


async def _prompt_report_period(cq: CallbackQuery, state: FSMContext, report_kind: str) -> None:
    await state.clear()
    label, _, _ = REPORT_DEFINITIONS[report_kind]
    await state.set_state(ReportsExportFSM.awaiting_period)
    await state.update_data(report_kind=report_kind)
    await cq.message.answer(
        "Введите период для выгрузки (" + label + "). Формат: YYYY-MM-DD YYYY-MM-DD.\n"
        "Можно указать одну дату для одного дня. Для отмены отправьте /cancel."
    )
    await cq.answer()


@router.callback_query(
    F.data == "adm:r:o",
    StaffRoleFilter({StaffRole.GLOBAL_ADMIN, StaffRole.CITY_ADMIN}),
)
async def cb_reports_orders(cq: CallbackQuery, state: FSMContext) -> None:
    await _prompt_report_period(cq, state, "orders")


@router.callback_query(
    F.data == "adm:r:c",
    StaffRoleFilter({StaffRole.GLOBAL_ADMIN, StaffRole.CITY_ADMIN}),
)
async def cb_reports_commissions(cq: CallbackQuery, state: FSMContext) -> None:
    await _prompt_report_period(cq, state, "commissions")


@router.callback_query(
    F.data == "adm:r:rr",
    StaffRoleFilter({StaffRole.GLOBAL_ADMIN, StaffRole.CITY_ADMIN}),
)
async def cb_reports_referrals(cq: CallbackQuery, state: FSMContext) -> None:
    await _prompt_report_period(cq, state, "ref_rewards")


@router.message(StateFilter(ReportsExportFSM.awaiting_period), F.text == "/cancel")
async def reports_cancel(msg: Message, state: FSMContext) -> None:
    await state.clear()
    await msg.answer("Отмена. Выберите отчёт:", reply_markup=reports_menu_keyboard())


@router.message(StateFilter(ReportsExportFSM.awaiting_period))
async def reports_period_submit(msg: Message, staff: StaffUser, state: FSMContext) -> None:
    period = _parse_period_input(msg.text or "")
    if not period:
        await msg.answer(
            "Не удалось разобрать период. Укажите даты в формате YYYY-MM-DD YYYY-MM-DD (пример: 2025-09-01 2025-09-15)."
        )
        return

    start_dt, end_dt = period
    data = await state.get_data()
    report_kind = data.get("report_kind")
    definition = REPORT_DEFINITIONS.get(report_kind or "")
    if not definition:
        await state.clear()
        await msg.answer(
            "Тип отчёта не распознан. Откройте меню отчётов заново:",
            reply_markup=reports_menu_keyboard(),
        )
        return

    label, exporter, caption_prefix = definition
    city_ids = visible_city_ids_for(staff)

    try:
        bundle = await exporter(date_from=start_dt, date_to=end_dt, city_ids=city_ids)
    except Exception:
        await state.clear()
        await msg.answer(
            "Не удалось сформировать отчёт. Попробуйте позже.",
            reply_markup=reports_menu_keyboard(),
        )
        return

    period_label = _format_period_label(start_dt, end_dt)
    _send_export_documents(msg, bundle, f"{caption_prefix} {period_label}")
    await state.clear()
    await msg.answer("Файлы отправлены. Выберите другой отчёт:", reply_markup=reports_menu_keyboard())

async def _start_new_order(cq: CallbackQuery, staff: StaffUser, state: FSMContext) -> None:
    await state.clear()
    await state.update_data(staff_id=staff.id, attachments=[], order_type=OrderType.NORMAL.value)
    await state.set_state(NewOrderFSM.city)
    await _render_city_step(cq.message, state, page=1)
    await cq.answer()


async def _render_city_step(message: Message, state: FSMContext, page: int, query: Optional[str] = None) -> None:
    orders_service = _orders_service(message.bot)
    limit = 80
    if query:
        cities = await orders_service.list_cities(query=query, limit=limit)
    else:
        cities = await orders_service.list_cities(limit=limit)
    if not cities:
        await message.edit_text("пїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅ. пїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅ /cancel.")
        return
    per_page = 10
    total_pages = max(1, (len(cities) + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))
    start = (page - 1) * per_page
    chunk = cities[start : start + per_page]
    keyboard = new_order_city_keyboard([(c.id, c.name) for c in chunk], page=page, total_pages=total_pages)
    await message.edit_text("пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅ:", reply_markup=keyboard)
    await state.update_data(city_query=query, city_page=page)


@router.callback_query(
    F.data == "adm:new",
    StaffRoleFilter({StaffRole.GLOBAL_ADMIN, StaffRole.CITY_ADMIN, StaffRole.LOGIST}),
)
async def cb_new_order_start(cq: CallbackQuery, staff: StaffUser, state: FSMContext) -> None:
    await _start_new_order(cq, staff, state)


@router.callback_query(F.data == "adm:new:cancel")
async def cb_new_order_cancel(cq: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await cq.message.edit_text("пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ.")
    await cq.answer()


@router.callback_query(F.data.startswith("adm:new:city_page:"), StateFilter(NewOrderFSM.city))
async def cb_new_order_city_page(cq: CallbackQuery, state: FSMContext) -> None:
    page = int(cq.data.split(":")[2])
    data = await state.get_data()
    query = data.get("city_query")
    await _render_city_step(cq.message, state, page=page, query=query)
    await cq.answer()


@router.callback_query(F.data == "adm:new:city_search", StateFilter(NewOrderFSM.city))
async def cb_new_order_city_search(cq: CallbackQuery) -> None:
    await cq.message.edit_text("пїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅ (пїЅпїЅпїЅпїЅпїЅпїЅпїЅ). пїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅ /cancel.")
    await cq.answer()


@router.message(StateFilter(NewOrderFSM.city))
async def new_order_city_input(msg: Message, state: FSMContext) -> None:
    query = msg.text.strip()
    if len(query) < 2:
        await msg.answer("пїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅ пїЅпїЅ пїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅ.")
        return
    await _render_city_step(msg, state, page=1, query=query)


@router.callback_query(F.data.startswith("adm:new:city:"), StateFilter(NewOrderFSM.city))
async def cb_new_order_city_pick(cq: CallbackQuery, state: FSMContext) -> None:
    city_id = int(cq.data.split(":")[2])
    orders_service = _orders_service(cq.message.bot)
    city = await orders_service.get_city(city_id)
    if not city:
        await cq.answer("пїЅпїЅпїЅпїЅпїЅ пїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅ", show_alert=True)
        return
    await state.update_data(city_id=city.id, city_name=city.name)
    await state.set_state(NewOrderFSM.district)
    await _render_district_step(cq.message, state, page=1)
    await cq.answer()


async def _render_district_step(message: Message, state: FSMContext, page: int) -> None:
    data = await state.get_data()
    city_id = data.get("city_id")
    orders_service = _orders_service(message.bot)
    districts, has_next = await orders_service.list_districts(city_id, page=page, page_size=5)
    buttons = [(d.id, d.name) for d in districts]
    keyboard = new_order_district_keyboard(buttons, page=page, has_next=has_next)
    await message.edit_text("пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅ (пїЅпїЅпїЅ пїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅ):", reply_markup=keyboard)
    await state.update_data(district_page=page)


@router.callback_query(F.data.startswith("adm:new:district_page:"), StateFilter(NewOrderFSM.district))
async def cb_new_order_district_page(cq: CallbackQuery, state: FSMContext) -> None:
    page = int(cq.data.split(":")[2])
    await _render_district_step(cq.message, state, page=page)
    await cq.answer()


@router.callback_query(F.data == "adm:new:city_back", StateFilter(NewOrderFSM.district))
async def cb_new_order_city_back(cq: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(NewOrderFSM.city)
    data = await state.get_data()
    await _render_city_step(
        cq.message,
        state,
        page=data.get("city_page", 1),
        query=data.get("city_query"),
    )
    await cq.answer()


@router.callback_query(F.data == "adm:new:district:none", StateFilter(NewOrderFSM.district))
async def cb_new_order_district_none(cq: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(district_id=None, district_name="пїЅ")
    await state.set_state(NewOrderFSM.street_mode)
    await cq.message.edit_text(
        "пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅ:",
        reply_markup=new_order_street_mode_keyboard(),
    )
    await cq.answer()


@router.callback_query(F.data.startswith("adm:new:district:"), StateFilter(NewOrderFSM.district))
async def cb_new_order_district_pick(cq: CallbackQuery, state: FSMContext) -> None:
    district_id = int(cq.data.split(":")[2])
    orders_service = _orders_service(cq.message.bot)
    district = await orders_service.get_district(district_id)
    if not district:
        await cq.answer("пїЅпїЅпїЅпїЅпїЅ пїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅ", show_alert=True)
        return
    await state.update_data(district_id=district.id, district_name=district.name)
    await state.set_state(NewOrderFSM.street_mode)
    await cq.message.edit_text(
        "пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅ:",
        reply_markup=new_order_street_mode_keyboard(),
    )
    await cq.answer()
@router.callback_query(F.data == "adm:new:street:search", StateFilter(NewOrderFSM.street_mode))
async def cb_new_order_street_search(cq: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(NewOrderFSM.street_search)
    await cq.message.edit_text("пїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅ.")
    await cq.answer()


@router.callback_query(F.data == "adm:new:street:manual", StateFilter(NewOrderFSM.street_mode))
async def cb_new_order_street_manual(cq: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(NewOrderFSM.street_manual)
    await cq.message.edit_text(
        "пїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅ (2-50 пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ).",
        reply_markup=new_order_street_manual_keyboard(),
    )
    await cq.answer()


@router.callback_query(F.data == "adm:new:street:none", StateFilter(NewOrderFSM.street_mode))
async def cb_new_order_street_none(cq: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(street_id=None, street_name="пїЅ", street_manual=None)
    await state.set_state(NewOrderFSM.house)
    await cq.message.edit_text("пїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅ (1-10 пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ).")
    await cq.answer()


@router.callback_query(F.data == "adm:new:district_back", StateFilter(NewOrderFSM.street_mode))
async def cb_new_order_street_back(cq: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(NewOrderFSM.district)
    page = (await state.get_data()).get("district_page", 1)
    await _render_district_step(cq.message, state, page=page)
    await cq.answer()


@router.message(StateFilter(NewOrderFSM.street_manual))
async def new_order_street_manual_input(msg: Message, state: FSMContext) -> None:
    value = msg.text.strip()
    if not (2 <= len(value) <= 50):
        await msg.answer("пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅ пїЅпїЅ 2 пїЅпїЅ 50 пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ.")
        return
    await state.update_data(street_id=None, street_name=value, street_manual=value)
    await state.set_state(NewOrderFSM.house)
    await msg.answer("пїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅ (1-10 пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ).")


@router.message(StateFilter(NewOrderFSM.street_search))
async def new_order_street_search_input(msg: Message, state: FSMContext) -> None:
    query = msg.text.strip()
    if len(query) < 2:
        await msg.answer("пїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅ пїЅпїЅ пїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅ.")
        return
    data = await state.get_data()
    city_id = data.get("city_id")
    orders_service = _orders_service(msg.bot)
    streets = await orders_service.search_streets(city_id, query)
    if not streets:
        await msg.answer("пїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅ. пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅ.")
        return
    buttons = [
        (s.id, s.name if s.score is None else f"{s.name} ({int(s.score)}%)")
        for s in streets
    ]
    await msg.answer(
        "пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅ:",
        reply_markup=new_order_street_keyboard(buttons),
    )
    await state.update_data(street_search_results=buttons)


@router.callback_query(F.data.startswith("adm:new:street:"), StateFilter(NewOrderFSM.street_mode))
async def cb_new_order_street_pick(cq: CallbackQuery, state: FSMContext) -> None:
    tail = cq.data.split(":")[2]
    if tail == "search_again":
        await state.set_state(NewOrderFSM.street_search)
        await cq.message.edit_text("пїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅ пїЅпїЅпїЅ.")
        await cq.answer()
        return
    if tail == "manual_back":
        await state.set_state(NewOrderFSM.street_mode)
        await cq.message.edit_text(
            "пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅ:",
            reply_markup=new_order_street_mode_keyboard(),
        )
        await cq.answer()
        return
    street_id = int(tail)
    orders_service = _orders_service(cq.message.bot)
    street = await orders_service.get_street(street_id)
    if not street:
        await cq.answer("пїЅпїЅпїЅпїЅпїЅ пїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅ", show_alert=True)
        return
    await state.update_data(street_id=street.id, street_name=street.name, street_manual=None)
    await state.set_state(NewOrderFSM.house)
    await cq.message.edit_text("пїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅ (1-10 пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ).")
    await cq.answer()


@router.message(StateFilter(NewOrderFSM.house))
async def new_order_house(msg: Message, state: FSMContext) -> None:
    value = msg.text.strip()
    if not (1 <= len(value) <= 10):
        await msg.answer("пїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅ пїЅпїЅ 1 пїЅпїЅ 10 пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ.")
        return
    await state.update_data(house=value)
    await state.set_state(NewOrderFSM.apartment)
    await msg.answer("пїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ (пїЅпїЅпїЅ '-' пїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ).")


@router.message(StateFilter(NewOrderFSM.apartment))
async def new_order_apartment(msg: Message, state: FSMContext) -> None:
    value = msg.text.strip()
    if value == "-":
        value = ""
    if len(value) > 10:
        await msg.answer("пїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ. пїЅпїЅ 10 пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ.")
        return
    await state.update_data(apartment=value or None)
    await state.set_state(NewOrderFSM.address_comment)
    await msg.answer("пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅ пїЅпїЅпїЅпїЅпїЅпїЅ (пїЅпїЅпїЅ '-' пїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ).")


@router.message(StateFilter(NewOrderFSM.address_comment))
async def new_order_address_comment(msg: Message, state: FSMContext) -> None:
    value = msg.text.strip()
    if value == "-":
        value = ""
    await state.update_data(address_comment=value or None)
    await state.set_state(NewOrderFSM.client_name)
    await msg.answer("пїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅ (2-30 пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ, пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ).")


@router.message(StateFilter(NewOrderFSM.client_name))
async def new_order_client_name(msg: Message, state: FSMContext) -> None:
    value = msg.text.strip()
    if not _validate_name(value):
        await msg.answer("пїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅ 2-30 пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ, пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ, пїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅ.")
        return
    await state.update_data(client_name=value)
    await state.set_state(NewOrderFSM.client_phone)
    await msg.answer("пїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅ (+7XXXXXXXXXX пїЅпїЅпїЅ 8XXXXXXXXXX).")


@router.message(StateFilter(NewOrderFSM.client_phone))
async def new_order_client_phone(msg: Message, state: FSMContext) -> None:
    raw = _normalize_phone(msg.text)
    if not _validate_phone(raw):
        await msg.answer("пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ. пїЅпїЅпїЅпїЅпїЅпїЅ: +71234567890 пїЅпїЅпїЅ 81234567890.")
        return
    await state.update_data(client_phone=raw)
    await state.set_state(NewOrderFSM.category)
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    kb = InlineKeyboardBuilder()
    for code, label in CATEGORY_CHOICES:
        kb.button(text=label, callback_data=f"adm:new:cat:{code}")
    kb.adjust(2)
    await msg.answer("пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅ:", reply_markup=kb.as_markup())


@router.callback_query(F.data.startswith("adm:new:cat:"), StateFilter(NewOrderFSM.category))
async def cb_new_order_category(cq: CallbackQuery, state: FSMContext) -> None:
    code = cq.data.split(":")[2]
    await state.update_data(category=code, category_label=CATEGORY_LABELS.get(code, code))
    await state.set_state(NewOrderFSM.description)
    await cq.message.edit_text("пїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ (10-500 пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ).")
    await cq.answer()


@router.message(StateFilter(NewOrderFSM.description))
async def new_order_description(msg: Message, state: FSMContext) -> None:
    text = msg.text.strip()
    if not (10 <= len(text) <= 500):
        await msg.answer("пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅ пїЅпїЅ 10 пїЅпїЅ 500 пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ.")
        return
    await state.update_data(description=text)
    await state.set_state(NewOrderFSM.attachments)
    await msg.answer(
        "пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ (пїЅпїЅпїЅпїЅ/пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ) пїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅ 'пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ'.",
        reply_markup=new_order_attachments_keyboard(False),
    )


@router.callback_query(F.data == "adm:new:att:add", StateFilter(NewOrderFSM.attachments))
async def cb_new_order_att_add(cq: CallbackQuery) -> None:
    await cq.answer("пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅ пїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ")


@router.callback_query(F.data == "adm:new:att:clear", StateFilter(NewOrderFSM.attachments))
async def cb_new_order_att_clear(cq: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    data["attachments"] = []
    await state.update_data(**data)
    await cq.message.edit_text(
        "пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅ. пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ.",
        reply_markup=new_order_attachments_keyboard(False),
    )
    await cq.answer()


@router.message(StateFilter(NewOrderFSM.attachments), F.photo)
async def new_order_attach_photo(msg: Message, state: FSMContext) -> None:
    attachments = _attachments_from_state(await state.get_data())
    if len(attachments) >= ATTACHMENTS_LIMIT:
        await msg.answer("пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ. пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ.")
        return
    photo = msg.photo[-1]
    attachments.append(
        {
            "file_id": photo.file_id,
            "file_unique_id": photo.file_unique_id,
            "file_type": "photo",
            "file_name": None,
            "mime_type": None,
            "caption": msg.caption,
        }
    )
    await state.update_data(attachments=attachments)
    await msg.answer(
        f"пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅ. пїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ: {len(attachments)}.",
        reply_markup=new_order_attachments_keyboard(True),
    )


@router.message(StateFilter(NewOrderFSM.attachments), F.document)
async def new_order_attach_doc(msg: Message, state: FSMContext) -> None:
    attachments = _attachments_from_state(await state.get_data())
    if len(attachments) >= ATTACHMENTS_LIMIT:
        await msg.answer("пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ. пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ.")
        return
    doc = msg.document
    attachments.append(
        {
            "file_id": doc.file_id,
            "file_unique_id": doc.file_unique_id,
            "file_type": "document",
            "file_name": doc.file_name,
            "mime_type": doc.mime_type,
            "caption": msg.caption,
        }
    )
    await state.update_data(attachments=attachments)
    await msg.answer(
        f"пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ. пїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ: {len(attachments)}.",
        reply_markup=new_order_attachments_keyboard(True),
    )
@router.callback_query(F.data == "adm:new:att:done", StateFilter(NewOrderFSM.attachments))
async def cb_new_order_att_done(cq: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(NewOrderFSM.order_type)
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    kb = InlineKeyboardBuilder()
    kb.button(text="пїЅпїЅпїЅпїЅпїЅпїЅпїЅ", callback_data="adm:new:type:NORMAL")
    kb.button(text="пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ", callback_data="adm:new:type:GUARANTEE")
    kb.adjust(2)
    await cq.message.edit_text("пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅ:", reply_markup=kb.as_markup())
    await cq.answer()


@router.callback_query(F.data.startswith("adm:new:type:"), StateFilter(NewOrderFSM.order_type))
async def cb_new_order_type(cq: CallbackQuery, state: FSMContext) -> None:
    code = cq.data.split(":")[2]
    await state.update_data(
        order_type=code,
        company_payment=2500 if code == "GUARANTEE" else 0,
        initial_status=None,
    )
    await state.set_state(NewOrderFSM.slot)
    data = await state.get_data()
    city_id = data.get("city_id")
    if not city_id:
        await cq.answer("????? ?? ??????", show_alert=True)
        return
    tz = await _resolve_city_timezone(cq.message.bot, city_id)
    workday_start, workday_end = await _resolve_workday_window()
    now_local = time_service.now_in_city(tz)
    options = _slot_options(now_local, workday_start=workday_start, workday_end=workday_end)
    await state.update_data(
        slot_options=options,
        city_timezone=_zone_storage_value(tz),
        pending_asap=False,
    )
    keyboard = new_order_slot_keyboard(options)
    await cq.message.edit_text("???????? ????:", reply_markup=keyboard)
    await cq.answer()


@router.callback_query(F.data.startswith("adm:new:slot:"), StateFilter(NewOrderFSM.slot))
async def cb_new_order_slot(cq: CallbackQuery, state: FSMContext) -> None:
    key = cq.data.split(":")[2]
    data = await state.get_data()
    city_id = data.get("city_id")
    if not city_id:
        await cq.answer("????? ?? ??????", show_alert=True)
        return
    options = data.get("slot_options") or []
    valid_keys = {item[0] for item in options}
    if key not in valid_keys:
        await cq.answer("???? ??????????", show_alert=True)
        return
    tz_value = data.get("city_timezone")
    if tz_value:
        tz = time_service.resolve_timezone(tz_value)
    else:
        tz = await _resolve_city_timezone(cq.message.bot, city_id)
        await state.update_data(city_timezone=_zone_storage_value(tz))
    workday_start, workday_end = await _resolve_workday_window()
    now_local = time_service.now_in_city(tz)
    if key == "ASAP":
        normalized = time_service.normalize_asap_choice(
            now_local=now_local,
            workday_start=workday_start,
            workday_end=workday_end,
            late_threshold=LATE_ASAP_THRESHOLD,
        )
        if normalized == "DEFERRED_TOM_10_13":
            await state.update_data(pending_asap=True)
            await cq.message.edit_text(
                "ASAP ????? 19:30. ????????? ?? ?????? 10-13?",
                reply_markup=new_order_asap_late_keyboard(),
            )
            await cq.answer()
            return
        slot_choice = "ASAP"
        initial_status = None
    else:
        slot_choice = key
        initial_status = None
    try:
        await _finalize_slot_selection(
            message=cq.message,
            state=state,
            slot_choice=slot_choice,
            tz=tz,
            workday_start=workday_start,
            workday_end=workday_end,
            initial_status_override=initial_status,
        )
    except ValueError:
        refreshed_options = _slot_options(
            time_service.now_in_city(tz),
            workday_start=workday_start,
            workday_end=workday_end,
        )
        await state.update_data(slot_options=refreshed_options, pending_asap=False, initial_status=None)
        await cq.message.edit_text(
            "???? ??????????. ???????? ?????? ????:",
            reply_markup=new_order_slot_keyboard(refreshed_options),
        )
        await cq.answer("???? ??????????, ???????? ??????", show_alert=True)
        return
    await cq.answer()

@router.callback_query(F.data == "adm:new:slot:lateok", StateFilter(NewOrderFSM.slot))
async def cb_new_order_slot_lateok(cq: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    city_id = data.get("city_id")
    if not city_id:
        await cq.answer("????? ?? ??????", show_alert=True)
        return
    tz_value = data.get("city_timezone")
    if tz_value:
        tz = time_service.resolve_timezone(tz_value)
    else:
        tz = await _resolve_city_timezone(cq.message.bot, city_id)
        await state.update_data(city_timezone=_zone_storage_value(tz))
    workday_start, workday_end = await _resolve_workday_window()
    await _finalize_slot_selection(
        message=cq.message,
        state=state,
        slot_choice="TOM:10-13",
        tz=tz,
        workday_start=workday_start,
        workday_end=workday_end,
        initial_status_override=OrderStatus.DEFERRED,
    )
    await cq.answer()


@router.callback_query(F.data == "adm:new:slot:reslot", StateFilter(NewOrderFSM.slot))
async def cb_new_order_slot_reslot(cq: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    city_id = data.get("city_id")
    if not city_id:
        await cq.answer("????? ?? ??????", show_alert=True)
        return
    tz_value = data.get("city_timezone")
    if tz_value:
        tz = time_service.resolve_timezone(tz_value)
    else:
        tz = await _resolve_city_timezone(cq.message.bot, city_id)
        await state.update_data(city_timezone=_zone_storage_value(tz))
    workday_start, workday_end = await _resolve_workday_window()
    options = _slot_options(
        time_service.now_in_city(tz),
        workday_start=workday_start,
        workday_end=workday_end,
    )
    await state.update_data(slot_options=options, pending_asap=False, initial_status=None)
    await cq.message.edit_text("???????? ????:", reply_markup=new_order_slot_keyboard(options))
    await cq.answer()



@router.callback_query(F.data == "adm:new:confirm", StateFilter(NewOrderFSM.confirm))
async def cb_new_order_confirm(cq: CallbackQuery, staff: StaffUser, state: FSMContext) -> None:
    data = await state.get_data()
    try:
        new_order = _build_new_order_data(data, staff)
    except KeyError:
        await state.clear()
        await cq.answer("пїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅ, пїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅ", show_alert=True)
        return
    orders_service = _orders_service(cq.message.bot)
    order_id = await orders_service.create_order(new_order)
    await state.clear()
    await cq.answer("пїЅпїЅпїЅпїЅпїЅпїЅпїЅ")
    await _render_order_card(cq.message, order_id, staff)





@router.callback_query(
    F.data == "adm:s",
    StaffRoleFilter({StaffRole.GLOBAL_ADMIN}),
)
async def cb_settings_menu(cq: CallbackQuery, staff: StaffUser) -> None:
    await cq.message.edit_text(
        "<b>пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅ</b>\nпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ.",
        reply_markup=settings_menu_keyboard(),
    )
    await cq.answer()


@router.callback_query(
    F.data.startswith("adm:s:group:"),
    StaffRoleFilter({StaffRole.GLOBAL_ADMIN}),
)
async def cb_settings_group(cq: CallbackQuery, staff: StaffUser) -> None:
    group_key = cq.data.split(":")[3]
    try:
        view_text, keyboard = await _build_settings_view(cq.message.bot, group_key)
    except KeyError:
        await cq.answer("пїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ", show_alert=True)
        return
    await cq.message.edit_text(
        view_text,
        reply_markup=keyboard,
        disable_web_page_preview=True,
    )
    await cq.answer()


@router.callback_query(
    F.data.startswith("adm:s:edit:"),
    StaffRoleFilter({StaffRole.GLOBAL_ADMIN}),
)
async def cb_settings_edit_start(
    cq: CallbackQuery, staff: StaffUser, state: FSMContext
) -> None:
    parts = cq.data.split(":")
    if len(parts) != 5:
        await cq.answer("пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅ", show_alert=True)
        return
    _, _, _, group_key, field_key = parts
    try:
        field = _get_setting_field(field_key)
    except KeyError:
        await cq.answer("пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅ", show_alert=True)
        return

    service = _settings_service(cq.message.bot)
    raw_map = await service.get_values([field.key])
    current_raw = raw_map.get(field.key, (None, None))[0]
    display, _ = _format_setting_value(field, current_raw)
    prompt = _build_setting_prompt(field, display)

    await state.set_state(SettingsEditFSM.awaiting_value)
    await state.update_data(
        edit_key=field.key,
        group_key=group_key,
        source_chat_id=cq.message.chat.id,
        source_message_id=cq.message.message_id,
    )
    await cq.message.answer(prompt, disable_web_page_preview=True)
    await cq.answer()


@router.message(
    StateFilter(SettingsEditFSM.awaiting_value),
    StaffRoleFilter({StaffRole.GLOBAL_ADMIN}),
    F.text == "/cancel",
)
async def settings_edit_cancel(msg: Message, state: FSMContext) -> None:
    await state.clear()
    await msg.answer("пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ.")


@router.message(
    StateFilter(SettingsEditFSM.awaiting_value),
    StaffRoleFilter({StaffRole.GLOBAL_ADMIN}),
)
async def settings_edit_value(
    msg: Message, staff: StaffUser, state: FSMContext
) -> None:
    data = await state.get_data()
    field_key = data.get("edit_key")
    group_key = data.get("group_key")
    source_chat_id = data.get("source_chat_id")
    source_message_id = data.get("source_message_id")

    if not field_key or not group_key or source_chat_id is None or source_message_id is None:
        await state.clear()
        await msg.answer(
            "пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ. пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅ."
        )
        return

    try:
        field = _get_setting_field(field_key)
    except KeyError:
        await state.clear()
        await msg.answer("пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅ.")
        return

    if not msg.text:
        await msg.answer("пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ.")
        return

    try:
        value, value_type = _parse_setting_input(field, msg.text)
    except ValueError as exc:
        await msg.answer(str(exc))
        return

    service = _settings_service(msg.bot)
    await service.set_value(field.key, value, value_type=value_type)
    await state.clear()
    await msg.answer("пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ пїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅпїЅ.")

    try:
        view_text, keyboard = await _build_settings_view(msg.bot, group_key)
        await msg.bot.edit_message_text(
            view_text,
            chat_id=source_chat_id,
            message_id=source_message_id,
            reply_markup=keyboard,
            disable_web_page_preview=True,
        )
    except Exception:
        pass


@router.callback_query(
    F.data == "adm:l",
    StaffRoleFilter({StaffRole.GLOBAL_ADMIN, StaffRole.CITY_ADMIN, StaffRole.LOGIST}),
)
async def cb_logs_menu(cq: CallbackQuery, staff: StaffUser) -> None:
    entries = live_log.snapshot(LOG_ENTRIES_LIMIT)
    text = _format_log_entries(entries)
    keyboard = logs_menu_keyboard(can_clear=staff.role is StaffRole.GLOBAL_ADMIN)
    await cq.message.edit_text(
        text,
        reply_markup=keyboard,
        disable_web_page_preview=True,
    )
    await cq.answer()


@router.callback_query(
    F.data == "adm:l:refresh",
    StaffRoleFilter({StaffRole.GLOBAL_ADMIN, StaffRole.CITY_ADMIN, StaffRole.LOGIST}),
)
async def cb_logs_refresh(cq: CallbackQuery, staff: StaffUser) -> None:
    entries = live_log.snapshot(LOG_ENTRIES_LIMIT)
    text = _format_log_entries(entries)
    keyboard = logs_menu_keyboard(can_clear=staff.role is StaffRole.GLOBAL_ADMIN)
    await cq.message.edit_text(
        text,
        reply_markup=keyboard,
        disable_web_page_preview=True,
    )
    await cq.answer()


@router.callback_query(
    F.data == "adm:l:clear",
    StaffRoleFilter({StaffRole.GLOBAL_ADMIN}),
)
async def cb_logs_clear(cq: CallbackQuery, staff: StaffUser) -> None:
    live_log.clear()
    entries = live_log.snapshot(LOG_ENTRIES_LIMIT)
    text = _format_log_entries(entries)
    keyboard = logs_menu_keyboard(can_clear=True)
    await cq.message.edit_text(
        text,
        reply_markup=keyboard,
        disable_web_page_preview=True,
    )
    await cq.answer("пїЅпїЅпїЅпїЅпїЅпїЅпїЅ")














