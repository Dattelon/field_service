from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Optional, Sequence
from zoneinfo import ZoneInfo

from aiogram import F, Router, Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup, Message

from field_service.config import settings as env_settings
from field_service.services import export_service, live_log, time_service
from field_service.services import settings_service
from field_service.services.onboarding_service import normalize_phone
from field_service.bots.admin_bot.services_db import AccessCodeError

FINANCE_SEGMENT_TITLES = {
    "aw": "РћР¶РёРґР°СЋС‚ РѕРїР»Р°С‚С‹",
    "pd": "РћРїР»Р°С‡РµРЅРЅС‹Рµ",
    "ov": "РџСЂРѕСЃСЂРѕС‡РµРЅРЅС‹Рµ",
}

STAFF_CODE_PROMPT = "Р’РІРµРґРёС‚Рµ РєРѕРґ РґРѕСЃС‚СѓРїР°, РІС‹РґР°РЅРЅС‹Р№ РіР»РѕР±Р°Р»СЊРЅС‹Рј Р°РґРјРёРЅРёСЃС‚СЂР°С‚РѕСЂРѕРј."
STAFF_CODE_ERROR = "РљРѕРґ РЅРµ РЅР°Р№РґРµРЅ / РёСЃС‚С‘Рє / РѕС‚РѕР·РІР°РЅ / СѓР¶Рµ РёСЃРїРѕР»СЊР·РѕРІР°РЅ."
STAFF_PDN_TEXT = (
    "РЎРѕРіР»Р°СЃРёРµ РЅР° РѕР±СЂР°Р±РѕС‚РєСѓ РїРµСЂСЃРѕРЅР°Р»СЊРЅС‹С… РґР°РЅРЅС‹С….\nРЎРѕРіР»Р°СЃРёРµ РІРєР»СЋС‡Р°РµС‚ РѕР±СЂР°Р±РѕС‚РєСѓ Р¤Рћ, С‚РµР»РµС„РѕРЅР° Рё РґР°РЅРЅС‹С… Рѕ Р·Р°РєР°Р·Р°С… РґР»СЏ РґРѕРїСѓСЃРєР° Рє СЂР°Р±РѕС‚Рµ Рё РѕР±РµСЃРїРµС‡РµРЅРёСЏ Р±РµР·РѕРїР°СЃРЅРѕСЃС‚Рё СЃРµСЂРІРёСЃР°. РћС‚РїСЂР°РІСЊС‚Рµ \"РЎРѕРіР»Р°СЃРµРЅ\" РґР»СЏ РїСЂРѕРґРѕР»Р¶РµРЅРёСЏ РёР»Рё \"РќРµ СЃРѕРіР»Р°СЃРµРЅ\" РґР»СЏ РѕС‚РјРµРЅС‹."
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
    OrderCategory,
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
    logs_menu_keyboard,
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
    reports_menu_keyboard,
    settings_group_keyboard,
    settings_menu_keyboard,
)
from .normalizers import normalize_category, normalize_status
from .states import (FinanceActionFSM, NewOrderFSM, ReportsExportFSM, SettingsEditFSM, StaffAccessFSM)
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
from .handlers_finance import router as finance_router

router = Router(name="admin_handlers")
router.include_router(queue_router)
router.include_router(finance_router)


async def _edit_or_answer(message: Message, text: str, *, reply_markup=None, disable_web_page_preview=None) -> None:
    try:
        await message.edit_text(text, reply_markup=reply_markup, disable_web_page_preview=disable_web_page_preview)
    except Exception:
        await message.answer(text, reply_markup=reply_markup, disable_web_page_preview=disable_web_page_preview)

# Global safety patch: ensure any Message.edit_text falls back to sending a new message if editing fails
try:
    from aiogram.types import Message as _AiogramMessage

    if not getattr(_AiogramMessage, "_fs_safe_patched", False):
        _orig_edit_text = _AiogramMessage.edit_text

        async def _fs_safe_edit_text(self, text: str, **kwargs):
            try:
                return await _orig_edit_text(self, text, **kwargs)
            except Exception:
                return await self.answer(
                    text,
                    reply_markup=kwargs.get("reply_markup"),
                    disable_web_page_preview=kwargs.get("disable_web_page_preview"),
                )

        _AiogramMessage.edit_text = _fs_safe_edit_text  # type: ignore[assignment]
        _AiogramMessage._fs_safe_patched = True  # type: ignore[attr-defined]
except Exception:
    # If patching fails, proceed without it; explicit fallbacks still exist on critical paths
    pass

# --- Runtime safety/encoding patches ---
# Safe CallbackQuery.answer: swallow "query is too old/invalid" errors to avoid noisy logs
try:
    from aiogram.types import CallbackQuery as _AiogramCallbackQuery
    from aiogram.exceptions import TelegramBadRequest as _TgBadReq

    if not getattr(_AiogramCallbackQuery, "_fs_safe_answer_patched", False):
        _orig_cq_answer = _AiogramCallbackQuery.answer

        async def _fs_safe_cq_answer(self, *args, **kwargs):
            try:
                return await _orig_cq_answer(self, *args, **kwargs)
            except _TgBadReq as exc:  # type: ignore[misc]
                msg = str(getattr(exc, "message", "") or exc)
                msg_low = msg.lower()
                if (
                    "query is too old" in msg_low
                    or "response timeout expired" in msg_low
                    or "query id is invalid" in msg_low
                ):
                    return None
                raise
            except Exception:
                # Be conservative: unexpected errors bubble up
                raise

        _AiogramCallbackQuery.answer = _fs_safe_cq_answer  # type: ignore[assignment]
        _AiogramCallbackQuery._fs_safe_answer_patched = True  # type: ignore[attr-defined]
except Exception:
    pass

# Attempt to repair mojibake text (UTF-8 mis-decoded as cp1251) before sending
def _maybe_fix_mojibake(text: object) -> object:
    if not isinstance(text, str):
        return text
    sample = text[:200]
    suspicious = sum(1 for ch in sample if ch in "СЃвЂ№")
    if suspicious == 0:
        return text
    try:
        fixed = text.encode("cp1251", errors="ignore").decode("utf-8", errors="ignore")
        if fixed and (fixed.count("") + fixed.count("")) < suspicious:
            return fixed
    except Exception:
        pass
    return text

try:
    from aiogram.types import Message as _Msg
    _orig_edit = _Msg.edit_text
    _orig_answer = _Msg.answer

    async def _fs_edit_text(self, text: str, **kwargs):
        text = _maybe_fix_mojibake(text)  # type: ignore[assignment]
        try:
            return await _orig_edit(self, text, **kwargs)
        except Exception:
            # fallback to sending a new message
            return await _orig_answer(self, text, **kwargs)

    async def _fs_answer(self, text: str, **kwargs):
        text = _maybe_fix_mojibake(text)  # type: ignore[assignment]
        return await _orig_answer(self, text, **kwargs)

    _Msg.edit_text = _fs_edit_text  # type: ignore[assignment]
    _Msg.answer = _fs_answer  # type: ignore[assignment]
except Exception:
    pass


async def show_admin_main_menu(
    message: Message,
    staff: StaffUser,
    *,
    edit: bool = False,
    notice: Optional[str] = None,
) -> None:
    text = notice or "Р“Р»Р°РІРЅРѕРµ РјРµРЅСЋ:"
    markup = main_menu(staff)
    if edit:
        try:
            await message.edit_text(text, reply_markup=markup)
            return
        except Exception:
            pass
    await message.answer(text, reply_markup=markup)

STAFF_ROLE_LABELS = {
    StaffRole.GLOBAL_ADMIN: "Global admin",
    StaffRole.CITY_ADMIN: "City admin",
    StaffRole.LOGIST: "Logist",
}

ACCESS_CODE_ERROR_MESSAGES = {
    "invalid_code": STAFF_CODE_ERROR,
    "expired": STAFF_CODE_ERROR,
    "no_cities": "РљРѕРґ РЅРµ СЃРѕРґРµСЂР¶РёС‚ РіРѕСЂРѕРґРѕРІ. РћР±СЂР°С‚РёС‚РµСЃСЊ Рє РіР»РѕР±Р°Р»СЊРЅРѕРјСѓ Р°РґРјРёРЅРёСЃС‚СЂР°С‚РѕСЂСѓ.",
    "already_staff": "Р­С‚РѕС‚ РєРѕРґ СѓР¶Рµ РёСЃРїРѕР»СЊР·РѕРІР°РЅ.",
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
# Allow Cyrillic letters (upper/lower incl. /), spaces and hyphen, length 2..30
NAME_RE = re.compile(r"^[\u0410-\u042F\u0401\u0430-\u044F\u0451\-\s]{2,30}$")
ATTACHMENTS_LIMIT = 5
CATEGORY_CHOICES: list[tuple[OrderCategory, str]] = [
    (OrderCategory.ELECTRICS, "Р­Р»РµРєС‚СЂРёРєР°"),
    (OrderCategory.PLUMBING, "РЎР°РЅС‚РµС…РЅРёРєР°"),
    (OrderCategory.APPLIANCES, "Р‘С‹С‚РѕРІР°СЏ С‚РµС…РЅРёРєР°"),
    (OrderCategory.WINDOWS, "РћРєРЅР°"),
    (OrderCategory.HANDYMAN, "РЈРЅРёРІРµСЂСЃР°Р»"),
    (OrderCategory.ROADSIDE, "РђРІС‚РѕРїРѕРјРѕС‰СЊ"),
]
CATEGORY_LABELS = {category: label for category, label in CATEGORY_CHOICES}
CATEGORY_LABELS_BY_VALUE = {category.value: label for category, label in CATEGORY_CHOICES}
SLOT_BUCKETS = (
    ("10-13", time(10, 0), time(13, 0)),
    ("13-16", time(13, 0), time(16, 0)),
    ("16-19", time(16, 0), time(19, 0)),
)
WORKDAY_START_DEFAULT = time_service.parse_time_string(env_settings.workday_start, default=time(10, 0))
WORKDAY_END_DEFAULT = time_service.parse_time_string(env_settings.workday_end, default=time(20, 0))
LATE_ASAP_THRESHOLD = time_service.parse_time_string(env_settings.asap_late_threshold, default=time(19, 30))

REPORT_DEFINITIONS: dict[str, tuple[str, Any, str]] = {
    "orders": ("Р·Р°РєР°Р·С‹", export_service.export_orders, "Orders"),
    "commissions": ("РєРѕРјРёСЃСЃРёРё", export_service.export_commissions, "Commissions"),
    "ref_rewards": ("СЂРµС„РµСЂР°Р»СЊРЅС‹Рµ РЅР°С‡РёСЃР»РµРЅРёСЏ", export_service.export_referral_rewards, "Referral rewards"),
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
        title="Р Р°Р±РѕС‡РёР№ РґРµРЅСЊ",
        description="РќР°СЃС‚СЂРѕР№РєРё СЂР°Р±РѕС‡РµРіРѕ РѕРєРЅР° РїРѕ СѓРјРѕР»С‡Р°РЅРёСЋ РґР»СЏ РїР»Р°РЅРёСЂРѕРІР°РЅРёСЏ СЃР»РѕС‚РѕРІ Рё СЃС‚Р°С‚СѓСЃРѕРІ DEFERRED/SEARCHING.",
        fields=(
            SettingFieldDef(
                key="working_hours_start",
                label="РќР°С‡Р°Р»Рѕ СЂР°Р±РѕС‡РµРіРѕ РґРЅСЏ",
                schema="time",
                value_type="TIME",
                default=env_settings.working_hours_start,
                help_text="Р¤РѕСЂРјР°С‚ С‡С‡:РјРј, РїРѕ СѓРјРѕР»С‡Р°РЅРёСЋ 10:00.",
            ),
            SettingFieldDef(
                key="working_hours_end",
                label="РљРѕРЅРµС† СЂР°Р±РѕС‡РµРіРѕ РґРЅСЏ",
                schema="time",
                value_type="TIME",
                default=env_settings.working_hours_end,
                help_text="Р¤РѕСЂРјР°С‚ С‡С‡:РјРј, РїРѕ СѓРјРѕР»С‡Р°РЅРёСЋ 20:00.",
            ),
        ),
    ),
    "distribution": SettingGroupDef(
        key="distribution",
        title="Р Р°СЃРїСЂРµРґРµР»РµРЅРёРµ Р·Р°СЏРІРѕРє",
        description="РќР°СЃС‚СЂРѕР№РєРё РѕС‡РµСЂРµРґРё РѕС‚РїСЂР°РІРєРё РѕС„С„РµСЂРѕРІ Рё SLA СЂР°СЃРїСЂРµРґРµР»РµРЅРёСЏ.",
        fields=(
            SettingFieldDef(
                key="distribution_tick_seconds",
                label="РЁР°Рі РѕС‚РїСЂР°РІРєРё РѕС„С„РµСЂРѕРІ (СЃРµРє)",
                schema="int",
                value_type="INT",
                default=30,
            ),
            SettingFieldDef(
                key="distribution_sla_seconds",
                label="SLA СЂР°СЃРїСЂРµРґРµР»РµРЅРёСЏ (СЃРµРє)",
                schema="int",
                value_type="INT",
                default=env_settings.distribution_sla_seconds,
            ),
            SettingFieldDef(
                key="distribution_rounds",
                label="РљРѕР»РёС‡РµСЃС‚РІРѕ СЂР°СѓРЅРґРѕРІ",
                schema="int",
                value_type="INT",
                default=env_settings.distribution_rounds,
            ),
            SettingFieldDef(
                key="escalate_to_admin_after_min",
                label="Р­СЃРєР°Р»Р°С†РёСЏ Р°РґРјРёРЅРёСЃС‚СЂР°С‚РѕСЂСѓ (РјРёРЅ)",
                schema="int_non_negative",
                value_type="INT",
                default=10,
            ),
            SettingFieldDef(
                key="distribution_log_topn",
                label="Р Р°Р·РјРµСЂ topN РІ Р»РѕРіРµ РїРѕРґР±РѕСЂР°",
                schema="int",
                value_type="INT",
                default=10,
            ),
        ),
    ),
    "limits": SettingGroupDef(
        key="limits",
        title="Р›РёРјРёС‚С‹",
        fields=(
            SettingFieldDef(
                key="max_active_orders",
                label="РњР°РєСЃ. Р°РєС‚РёРІРЅС‹С… Р·Р°РєР°Р·РѕРІ РЅР° РјР°СЃС‚РµСЂР°",
                schema="int",
                value_type="INT",
                default=1,
            ),
        ),
    ),
    "support": SettingGroupDef(
        key="support",
        title="РџРѕРґРґРµСЂР¶РєР°",
        description="РљРѕРЅС‚Р°РєС‚С‹ Рё СЃСЃС‹Р»РєРё РґР»СЏ РјР°СЃС‚РµСЂРѕРІ Рё Р°РґРјРёРЅРёСЃС‚СЂР°С‚РѕСЂРѕРІ.",
        fields=(
            SettingFieldDef(
                key="support_contact",
                label="РљРѕРЅС‚Р°РєС‚ РїРѕРґРґРµСЂР¶РєРё",
                schema="string",
                value_type="STR",
                help_text="РЈРєР°Р¶РёС‚Рµ @username, РЅРѕРјРµСЂ С‚РµР»РµС„РѕРЅР° РёР»Рё СЃСЃС‹Р»РєСѓ.",
            ),
            SettingFieldDef(
                key="support_faq_url",
                label="РЎСЃС‹Р»РєР° РЅР° FAQ",
                schema="string_optional",
                value_type="STR",
                help_text="РЈРєР°Р¶РёС‚Рµ URL РёР»Рё '-' С‡С‚РѕР±С‹ РѕС‡РёСЃС‚РёС‚СЊ.",
            ),
        ),
    ),
    "geo": SettingGroupDef(
        key="geo",
        title="Р“РµРѕРєРѕРґРµСЂ",
        fields=(
            SettingFieldDef(
                key="geo_mode",
                label="Р РµР¶РёРј",
                schema="choice",
                value_type="STR",
                choices=(
                    ("local_centroids", "Р›РѕРєР°Р»СЊРЅС‹Рµ С†РµРЅС‚СЂРѕРёРґС‹"),
                    ("yandex", "РЇРЅРґРµРєСЃ"),
                ),
                default="local_centroids",
                help_text="1 вЂ” Р»РѕРєР°Р»СЊРЅРѕ, 2 вЂ” РЇРЅРґРµРєСЃ API.",
            ),
            SettingFieldDef(
                key="yandex_geocoder_key",
                label="API РєР»СЋС‡ РіРµРѕРєРѕРґРµСЂР°",
                schema="string_optional",
                value_type="STR",
                help_text="РЈРєР°Р¶РёС‚Рµ РєР»СЋС‡ РёР»Рё '-' С‡С‚РѕР±С‹ РѕС‡РёСЃС‚РёС‚СЊ.",
            ),
            SettingFieldDef(
                key="yandex_throttle_rps",
                label="RPS РѕРіСЂР°РЅРёС‡РµРЅРёРµ",
                schema="int_non_negative",
                value_type="INT",
                default=1,
            ),
            SettingFieldDef(
                key="yandex_daily_limit",
                label="Р”РЅРµРІРЅРѕР№ Р»РёРјРёС‚ Р·Р°РїСЂРѕСЃРѕРІ",
                schema="int_non_negative",
                value_type="INT",
                default=1000,
            ),
        ),
    ),
    "channels": SettingGroupDef(
        key="channels",
        title="РљР°РЅР°Р»С‹ СѓРІРµРґРѕРјР»РµРЅРёР№",
        description="РљР°РЅР°Р»С‹ РґР»СЏ Р°Р»РµСЂС‚РѕРІ, Р»РѕРіРѕРІ Рё РѕС‚С‡С‘С‚РѕРІ.",
        fields=(
            SettingFieldDef(
                key="alerts_channel_id",
                label="Alerts / РђР»РµСЂС‚С‹",
                schema="int_optional",
                value_type="STR",
                help_text="ID РєР°РЅР°Р»Р° РёР»Рё '-' С‡С‚РѕР±С‹ РѕС‡РёСЃС‚РёС‚СЊ.",
            ),
            SettingFieldDef(
                key="logs_channel_id",
                label="РљР°РЅР°Р» Р»РѕРіРѕРІ",
                schema="int_optional",
                value_type="STR",
                help_text="ID РєР°РЅР°Р»Р° РёР»Рё '-' С‡С‚РѕР±С‹ РѕС‡РёСЃС‚РёС‚СЊ.",
            ),
            SettingFieldDef(
                key="reports_channel_id",
                label="РљР°РЅР°Р» РѕС‚С‡С‘С‚РѕРІ",
                schema="int_optional",
                value_type="STR",
                help_text="ID РєР°РЅР°Р»Р° РёР»Рё '-' С‡С‚РѕР±С‹ РѕС‡РёСЃС‚РёС‚СЊ.",
            ),
        ),
    ),
}
SETTINGS_GROUPS = SETTING_GROUPS



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


EMPTY_PLACEHOLDER = "вЂ”"
SCHEMA_DEFAULT_HELP = {
    "time": "Р¤РѕСЂРјР°С‚ С‡С‡:РјРј, РЅР°РїСЂРёРјРµСЂ 10:00.",
    "int": "Р’РІРµРґРёС‚Рµ С†РµР»РѕРµ С‡РёСЃР»Рѕ Р±РѕР»СЊС€Рµ 0.",
    "int_non_negative": "Р’РІРµРґРёС‚Рµ С†РµР»РѕРµ С‡РёСЃР»Рѕ РЅРµ РјРµРЅСЊС€Рµ 0.",
    "string": "Р’РІРµРґРёС‚Рµ С‚РµРєСЃС‚.",
    "string_optional": "Р’РІРµРґРёС‚Рµ С‚РµРєСЃС‚ РёР»Рё '-' С‡С‚РѕР±С‹ РѕС‡РёСЃС‚РёС‚СЊ.",
    "int_optional": "Р’РІРµРґРёС‚Рµ ID РёР»Рё '-' С‡С‚РѕР±С‹ РѕС‡РёСЃС‚РёС‚СЊ.",
    "choice": "Р’С‹Р±РµСЂРёС‚Рµ РІР°СЂРёР°РЅС‚ РёР· СЃРїРёСЃРєР°.",
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
        lines.append(f"РўРµРєСѓС‰РµРµ Р·РЅР°С‡РµРЅРёРµ: <code>{html.escape(current_display, quote=False)}</code>")
    base_help = SCHEMA_DEFAULT_HELP.get(field.schema, "Р’РІРµРґРёС‚Рµ Р·РЅР°С‡РµРЅРёРµ.")
    if field.schema == "choice":
        options = _choice_help(field)
        if options:
            lines.append(base_help)
            lines.append(options)
        else:
            lines.append(base_help)
    else:
        lines.append(field.help_text or base_help)
    lines.append("РћС‚РїСЂР°РІСЊС‚Рµ /cancel РґР»СЏ РѕС‚РјРµРЅС‹.")
    return "".join(lines)


def _parse_setting_input(field: SettingFieldDef, user_input: str) -> tuple[str, str]:
    text = (user_input or "").strip()
    if field.schema in {"string_optional", "int_optional"} and text in {"", "-"}:
        return "", field.value_type
    if field.schema == "time":
        if not re.fullmatch(r"^\d{1,2}:\d{2}$", text):
            raise ValueError("РќРµРІРµСЂРЅС‹Р№ С„РѕСЂРјР°С‚ РІСЂРµРјРµРЅРё. СЃРїРѕР»СЊР·СѓР№С‚Рµ С‡С‡:РјРј.")
        hh, mm = map(int, text.split(":"))
        if not (0 <= hh < 24 and 0 <= mm < 60):
            raise ValueError("Р§Р°СЃС‹ 0вЂ“23 Рё РјРёРЅСѓС‚С‹ 0вЂ“59.")
        return text, field.value_type
    if field.schema == "int":
        try:
            value = int(text)
        except ValueError:
            raise ValueError("Р’РІРµРґРёС‚Рµ С†РµР»РѕРµ С‡РёСЃР»Рѕ.")
        if value <= 0:
            raise ValueError("Р—РЅР°С‡РµРЅРёРµ РґРѕР»Р¶РЅРѕ Р±С‹С‚СЊ Р±РѕР»СЊС€Рµ 0.")
        return str(value), field.value_type
    if field.schema == "int_non_negative":
        try:
            value = int(text)
        except ValueError:
            raise ValueError("Р’РІРµРґРёС‚Рµ С†РµР»РѕРµ С‡РёСЃР»Рѕ.")
        if value < 0:
            raise ValueError("Р—РЅР°С‡РµРЅРёРµ РЅРµ РјРѕР¶РµС‚ Р±С‹С‚СЊ РјРµРЅСЊС€Рµ 0.")
        return str(value), field.value_type
    if field.schema == "int_optional":
        try:
            value = int(text)
        except ValueError:
            raise ValueError("Р’РІРµРґРёС‚Рµ С†РµР»РѕРµ С‡РёСЃР»Рѕ РёР»Рё '-' С‡С‚РѕР±С‹ РѕС‡РёСЃС‚РёС‚СЊ.")
        return str(value), field.value_type
    if field.schema == "choice":
        normalized = text.lower()
        if field.choices:
            for idx, (code, label) in enumerate(field.choices, 1):
                if normalized in {code.lower(), label.lower(), str(idx)}:
                    return code, field.value_type
        raise ValueError("Р’С‹Р±РµСЂРёС‚Рµ РІР°СЂРёР°РЅС‚ РёР· СЃРїРёСЃРєР°.")
    if field.schema == "string_optional":
        return text, field.value_type
    if field.schema == "string":
        if not text:
            raise ValueError("Р—РЅР°С‡РµРЅРёРµ РЅРµ РјРѕР¶РµС‚ Р±С‹С‚СЊ РїСѓСЃС‚С‹Рј.")
        return text, field.value_type
    raise ValueError("РќРµРїРѕРґРґРµСЂР¶РёРІР°РµРјС‹Р№ С‚РёРї РїРѕР»СЏ.")


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
            value_line += " <i>(РїРѕ СѓРјРѕР»С‡Р°РЅРёСЋ)</i>"
        lines.append(value_line)
    lines.append("Р’С‹Р±РµСЂРёС‚Рµ РїРѕР»Рµ РЅРёР¶Рµ, С‡С‚РѕР±С‹ РёР·РјРµРЅРёС‚СЊ.")
    keyboard = settings_group_keyboard(
        group_key,
        [(field.key, field.label) for field in group.fields],
    )
    return "".join(lines), keyboard

def _format_log_entries(entries: Sequence[live_log.LiveLogEntry]) -> str:
    if not entries:
        return '<b>СЃС‚РѕСЂРёСЏ РїСѓСЃС‚Р°</b>'

    lines = ['<b>СЃС‚РѕСЂРёСЏ СЃРѕР±С‹С‚РёР№</b>']
    for entry in entries:
        local_time = entry.timestamp.astimezone(LOCAL_TZ)
        body = html.escape(entry.message, quote=False).replace('\n', '<br>')
        lines.append(f'[{local_time:%H:%M:%S}] <i>{entry.source}</i> вЂ” {body}')
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
        extra = f"(СѓР»РёС†Р° РІСЂСѓС‡РЅСѓСЋ: {manual_street})"
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
                options.append((f"TODAY:{bucket_key}", f"СЃРµРіРѕРґРЅСЏ {start:%H:%M}-{end:%H:%M}"))
    for bucket_key, start, end in SLOT_BUCKETS:
        options.append((f"TOM:{bucket_key}", f"Р·Р°РІС‚СЂР° {start:%H:%M}-{end:%H:%M}"))
    return options


def _format_slot_display(
    choice: str,
    computation: time_service.SlotComputation,
    *,
    tz: ZoneInfo,
) -> str:
    if choice == "ASAP":
        return "ASAP"
    formatted = time_service.format_timeslot_local(
        computation.start_utc,
        computation.end_utc,
        tz=tz,
    )
    return formatted or "вЂ”"



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
    slot_display = _format_slot_display(slot_choice, computation, tz=tz)

    await state.update_data(
        timeslot_display=slot_display,
        timeslot_start_utc=computation.start_utc,
        timeslot_end_utc=computation.end_utc,
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


async def _send_export_documents(
    bot: Bot,
    bundle: export_service.ExportBundle,
    caption: str,
    *,
    chat_id: int,
) -> None:
    documents = [
        (bundle.csv_bytes, bundle.csv_filename, f"{caption} - CSV"),
        (bundle.xlsx_bytes, bundle.xlsx_filename, f"{caption} - XLSX"),
    ]
    with TemporaryDirectory() as tmpdir:
        base_path = Path(tmpdir)
        for payload, filename, note in documents:
            file_path = base_path / filename
            file_path.write_bytes(payload)
            await bot.send_document(
                chat_id=chat_id,
                document=FSInputFile(file_path),
                caption=note,
            )


async def _render_created_order_card(message: Message, order_id: int, staff: StaffUser) -> None:
    orders_service = _orders_service(message.bot)
    detail = await orders_service.get_card(order_id, city_ids=visible_city_ids_for(staff))
    if not detail:
        await message.answer(f"Р—Р°СЏРІРєР° #{order_id} СЃРѕР·РґР°РЅР°.")
        return
    text = format_order_card(detail)
    markup = order_card_keyboard(
        detail.id,
        attachments=detail.attachments,
        allow_return=(detail.status.upper() not in {"CANCELED", "CLOSED"}),
        allow_cancel=(detail.status.upper() not in {"CANCELED", "CLOSED"}),
        show_guarantee=False,
    )
    try:
        await message.edit_text(text, reply_markup=markup)
    except Exception:
        await message.answer(text, reply_markup=markup)

@router.message(CommandStart(), StaffRoleFilter({StaffRole.GLOBAL_ADMIN, StaffRole.CITY_ADMIN, StaffRole.LOGIST}))
async def admin_start(message: Message, staff: StaffUser) -> None:
    await message.answer(
        "РђРґРјРёРЅ-Р±РѕС‚ Field Service. Р“Р»Р°РІРЅРѕРµ РјРµРЅСЋ:",
        reply_markup=main_menu(staff),
    )


@router.message(CommandStart())
async def not_allowed_start(message: Message, state: FSMContext) -> None:
    staff_service = _staff_service(message.bot)
    user_id = message.from_user.id if message.from_user else None
    staff = await staff_service.get_by_tg_id(user_id) if user_id else None
    if staff:
        await state.clear()
        await message.answer("Р’С‹ СѓР¶Рµ Р°РІС‚РѕСЂРёР·РѕРІР°РЅС‹.", reply_markup=main_menu(staff))
        return
    await state.clear()
    await state.set_state(StaffAccessFSM.code)
    await message.answer(STAFF_CODE_PROMPT)


@router.message(StateFilter(StaffAccessFSM.code))
async def staff_access_enter_code(message: Message, state: FSMContext) -> None:
    code_value = (message.text or "").strip()
    if not code_value:
        await message.answer("Р’РІРµРґРёС‚Рµ РєРѕРґ РґРѕСЃС‚СѓРїР°.")
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
        f"Р РѕР»СЊ: {role_label}",
        f"Р“РѕСЂРѕРґР°: {', '.join(city_names) if city_names else '-'}",
    ]
    await message.answer("\n".join(summary_lines))
    await state.set_state(StaffAccessFSM.pdn)
    await message.answer(STAFF_PDN_TEXT)


@router.message(StateFilter(StaffAccessFSM.pdn))
async def staff_access_pdn(message: Message, state: FSMContext) -> None:
    text_value = (message.text or "").strip().lower()
    if text_value in {"РЅРµ СЃРѕРіР»Р°СЃРµРЅ", "РЅРµС‚", "no"}:
        await state.clear()
        await message.answer("Р‘РµР· СЃРѕРіР»Р°СЃРёСЏ РїСЂРѕРґРѕР»Р¶РёС‚СЊ РЅРµР»СЊР·СЏ. РћС‚РїСЂР°РІСЊС‚Рµ /start, РµСЃР»Рё РїРµСЂРµРґСѓРјР°РµС‚Рµ.")
        return
    if text_value not in {"СЃРѕРіР»Р°СЃРµРЅ", "РґР°", "ok", "С…РѕСЂРѕС€Рѕ"}:
        await message.answer('Р’РІРµРґРёС‚Рµ "СЃРѕРіР»Р°СЃРµРЅ" РёР»Рё "РЅРµ СЃРѕРіР»Р°СЃРµРЅ".')
        return
    await state.set_state(StaffAccessFSM.full_name)
    await message.answer("Р’РІРµРґРёС‚Рµ Р¤Рћ РїРѕР»РЅРѕСЃС‚СЊСЋ (РЅР°РїСЂРёРјРµСЂ, РІР°РЅРѕРІ РІР°РЅ РІР°РЅРѕРІРёС‡).")


@router.message(StateFilter(StaffAccessFSM.full_name))
async def staff_access_full_name(message: Message, state: FSMContext) -> None:
    full_name = (message.text or "").strip()
    if len(full_name) < 5:
        await message.answer("Р’РІРµРґРёС‚Рµ Р¤Рћ РїРѕР»РЅРѕСЃС‚СЊСЋ.")
        return
    await state.update_data(full_name=full_name)
    await state.set_state(StaffAccessFSM.phone)
    await message.answer("Р’РІРµРґРёС‚Рµ С‚РµР»РµС„РѕРЅ РІ С„РѕСЂРјР°С‚Рµ +7XXXXXXXXXX РёР»Рё 8XXXXXXXXXX.")


@router.message(StateFilter(StaffAccessFSM.phone))
async def staff_access_phone(message: Message, state: FSMContext) -> None:
    raw_phone = (message.text or "").strip()
    try:
        normalized = normalize_phone(raw_phone)
    except ValueError:
        await message.answer("РќРµРІРµСЂРЅС‹Р№ С„РѕСЂРјР°С‚ С‚РµР»РµС„РѕРЅР°. РџСЂРёРјРµСЂ: +7XXXXXXXXXX РёР»Рё 8XXXXXXXXXX")
        return
    data = await state.get_data()
    code_value = data.get("access_code")
    full_name = data.get("full_name")
    role_token = data.get("access_role")
    if not code_value or not full_name or not role_token:
        await state.clear()
        await message.answer("РЎРµСЃСЃРёСЏ РёСЃС‚РµРєР»Р°. РћС‚РїСЂР°РІСЊС‚Рµ /start Рё РїРѕРїСЂРѕР±СѓР№С‚Рµ СЃРЅРѕРІР°.")
        return
    user = message.from_user
    if not user:
        await message.answer("РќРµ СѓРґР°Р»РѕСЃСЊ РїРѕР»СѓС‡РёС‚СЊ РґР°РЅРЅС‹Рµ РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ.")
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
            "РќРµ СѓРґР°Р»РѕСЃСЊ РїСЂРёРјРµРЅРёС‚СЊ РєРѕРґ. РћР±СЂР°С‚РёС‚РµСЃСЊ Рє РіР»РѕР±Р°Р»СЊРЅРѕРјСѓ Р°РґРјРёРЅРёСЃС‚СЂР°С‚РѕСЂСѓ.",
        )
        await message.answer(error_text)
        await state.set_state(StaffAccessFSM.code)
        await message.answer(STAFF_CODE_PROMPT)
        return
    await state.clear()
    role_label = STAFF_ROLE_LABELS.get(staff_user.role, staff_user.role.value)
    city_names = await _resolve_city_names(message.bot, staff_user.city_ids)
    lines = [
        f"Р’С‹ РґРѕР±Р°РІР»РµРЅС‹ РєР°Рє {role_label}.",
        f"Р“РѕСЂРѕРґР°: {', '.join(city_names) if city_names else '-'}",
    ]
    await message.answer("\n".join(lines))
    await message.answer("Р“РѕС‚РѕРІРѕ. Р“Р»Р°РІРЅРѕРµ РјРµРЅСЋ:", reply_markup=main_menu(staff_user))


@router.callback_query(
    F.data == "adm:menu",
    StaffRoleFilter({StaffRole.GLOBAL_ADMIN, StaffRole.CITY_ADMIN, StaffRole.LOGIST}),
)
async def cb_menu(cq: CallbackQuery, staff: StaffUser) -> None:
    await cq.message.edit_text("Р“Р»Р°РІРЅРѕРµ РјРµРЅСЋ:", reply_markup=main_menu(staff))
    await cq.answer()

@router.callback_query(
    F.data == "adm:m",
    StaffRoleFilter({StaffRole.GLOBAL_ADMIN, StaffRole.CITY_ADMIN, StaffRole.LOGIST}),
)
async def cb_masters_menu(cq: CallbackQuery) -> None:
    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="рџ›Ў РњРѕРґРµСЂР°С†РёСЏ", callback_data="adm:mod")],
            [InlineKeyboardButton(text="в—ЂпёЏ Р’ РјРµРЅСЋ", callback_data="adm:menu")],
        ]
    )
    await cq.message.edit_text(
        "Р Р°Р·РґРµР» В«РњР°СЃС‚РµСЂР°В». Р’С‹Р±РµСЂРёС‚Рµ РїРѕРґРїСѓРЅРєС‚:",
        reply_markup=markup,
    )
    await cq.answer()


@router.callback_query(
    F.data == "adm:mod",
    StaffRoleFilter({StaffRole.GLOBAL_ADMIN, StaffRole.CITY_ADMIN, StaffRole.LOGIST}),
)
async def cb_moderation_placeholder(cq: CallbackQuery) -> None:
    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="в—ЂпёЏ РќР°Р·Р°Рґ", callback_data="adm:m")],
            [InlineKeyboardButton(text="рџЏ  Р“Р»Р°РІРЅРѕРµ РјРµРЅСЋ", callback_data="adm:menu")],
        ]
    )
    await cq.message.edit_text(
        "Р Р°Р·РґРµР» В«РњРѕРґРµСЂР°С†РёСЏВ» РµС‰С‘ РІ СЂР°Р·СЂР°Р±РѕС‚РєРµ.",
        reply_markup=markup,
    )
    await cq.answer()


@router.callback_query(
    F.data == "adm:staff:menu",
    StaffRoleFilter({StaffRole.CITY_ADMIN, StaffRole.LOGIST}),
)
async def cb_staff_menu_denied(cq: CallbackQuery, staff: StaffUser) -> None:
    if cq.message is not None:
        await cq.message.edit_text(
            "РќРµРґРѕСЃС‚Р°С‚РѕС‡РЅРѕ РїСЂР°РІ. Р“Р»Р°РІРЅРѕРµ РјРµРЅСЋ:",
            reply_markup=main_menu(staff),
        )
    await cq.answer("РќРµРґРѕСЃС‚Р°С‚РѕС‡РЅРѕ РїСЂР°РІ", show_alert=True)


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
    parts = cq.data.split(":")
    page = 1
    if len(parts) > 3:
        try:
            page = max(1, int(parts[3]))
        except ValueError:
            page = 1
    if cq.message is None:
        await cq.answer()
        return
    await _render_finance_segment(cq.message, staff, "aw", page, state)
    await cq.answer()


@router.callback_query(
    F.data.startswith("adm:f:pd:"),
    StaffRoleFilter({StaffRole.GLOBAL_ADMIN, StaffRole.CITY_ADMIN}),
)
async def cb_finance_pd(cq: CallbackQuery, staff: StaffUser, state: FSMContext) -> None:
    parts = cq.data.split(":")
    page = 1
    if len(parts) > 3:
        try:
            page = max(1, int(parts[3]))
        except ValueError:
            page = 1
    if cq.message is None:
        await cq.answer()
        return
    await _render_finance_segment(cq.message, staff, "pd", page, state)
    await cq.answer()


@router.callback_query(
    F.data.startswith("adm:f:ov:"),
    StaffRoleFilter({StaffRole.GLOBAL_ADMIN, StaffRole.CITY_ADMIN}),
)
async def cb_finance_ov(cq: CallbackQuery, staff: StaffUser, state: FSMContext) -> None:
    parts = cq.data.split(":")
    page = 1
    if len(parts) > 3:
        try:
            page = max(1, int(parts[3]))
        except ValueError:
            page = 1
    if cq.message is None:
        await cq.answer()
        return
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
    F.data == "adm:r",
    StaffRoleFilter({StaffRole.GLOBAL_ADMIN, StaffRole.CITY_ADMIN}),
)
async def cb_reports(cq: CallbackQuery, staff: StaffUser, state: FSMContext) -> None:
    await state.clear()
    await cq.message.edit_text("РћС‚С‡С‘С‚С‹:", reply_markup=reports_menu_keyboard())
    await cq.answer()


async def _prompt_report_period(cq: CallbackQuery, state: FSMContext, report_kind: str) -> None:
    await state.clear()
    label, _, _ = REPORT_DEFINITIONS[report_kind]
    await state.set_state(ReportsExportFSM.awaiting_period)
    await state.update_data(report_kind=report_kind)
    await cq.message.answer(
        "Р’РІРµРґРёС‚Рµ РїРµСЂРёРѕРґ РґР»СЏ РІС‹РіСЂСѓР·РєРё (" + label + "). Р¤РѕСЂРјР°С‚: YYYY-MM-DD YYYY-MM-DD.\n"
        "РњРѕР¶РЅРѕ СѓРєР°Р·Р°С‚СЊ РѕРґРЅСѓ РґР°С‚Сѓ РґР»СЏ РѕРґРЅРѕРіРѕ РґРЅСЏ. Р”Р»СЏ РѕС‚РјРµРЅС‹ РѕС‚РїСЂР°РІСЊС‚Рµ /cancel."
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
    await msg.answer("РћС‚РјРµРЅР°. Р’С‹Р±РµСЂРёС‚Рµ РѕС‚С‡С‘С‚:", reply_markup=reports_menu_keyboard())


@router.message(StateFilter(ReportsExportFSM.awaiting_period))
async def reports_period_submit(msg: Message, staff: StaffUser, state: FSMContext) -> None:
    period = _parse_period_input(msg.text or "")
    if not period:
        await msg.answer(
            "РќРµ СѓРґР°Р»РѕСЃСЊ СЂР°Р·РѕР±СЂР°С‚СЊ РїРµСЂРёРѕРґ. РЈРєР°Р¶РёС‚Рµ РґР°С‚С‹ РІ С„РѕСЂРјР°С‚Рµ YYYY-MM-DD YYYY-MM-DD (РїСЂРёРјРµСЂ: 2025-09-01 2025-09-15)."
        )
        return

    start_dt, end_dt = period
    data = await state.get_data()
    report_kind = data.get("report_kind")
    definition = REPORT_DEFINITIONS.get(report_kind or "")
    if not definition:
        await state.clear()
        await msg.answer(
            "РўРёРї РѕС‚С‡С‘С‚Р° РЅРµ СЂР°СЃРїРѕР·РЅР°РЅ. РћС‚РєСЂРѕР№С‚Рµ РјРµРЅСЋ РѕС‚С‡С‘С‚РѕРІ Р·Р°РЅРѕРІРѕ:",
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
            "РќРµ СѓРґР°Р»РѕСЃСЊ СЃС„РѕСЂРјРёСЂРѕРІР°С‚СЊ РѕС‚С‡С‘С‚. РџРѕРїСЂРѕР±СѓР№С‚Рµ РїРѕР·Р¶Рµ.",
            reply_markup=reports_menu_keyboard(),
        )
        return

    period_label = _format_period_label(start_dt, end_dt)
    operator_chat_id = None
    if msg.chat:
        operator_chat_id = msg.chat.id
    elif msg.from_user:
        operator_chat_id = msg.from_user.id
    target_chat_id = env_settings.reports_channel_id or operator_chat_id
    if target_chat_id is None:
        await state.clear()
        await msg.answer(
            "РќРµ СѓРґР°Р»РѕСЃСЊ РѕРїСЂРµРґРµР»РёС‚СЊ С‡Р°С‚ РґР»СЏ РѕС‚РїСЂР°РІРєРё РѕС‚С‡С‘С‚Р°.",
            reply_markup=reports_menu_keyboard(),
        )
        return

    await _send_export_documents(
        msg.bot,
        bundle,
        f"{caption_prefix} {period_label}",
        chat_id=target_chat_id,
    )
    await state.clear()
    await msg.answer("РћС‚С‡С‘С‚ РѕС‚РїСЂР°РІР»РµРЅ", reply_markup=reports_menu_keyboard())

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
        try:
            await message.edit_text("Р“РѕСЂРѕРґР° РЅРµ РЅР°Р№РґРµРЅС‹. РћС‚РїСЂР°РІСЊС‚Рµ /cancel.")
        except TelegramBadRequest:
            await message.answer("Р“РѕСЂРѕРґР° РЅРµ РЅР°Р№РґРµРЅС‹. РћС‚РїСЂР°РІСЊС‚Рµ /cancel.")
        return
    per_page = 10
    total_pages = max(1, (len(cities) + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))
    start = (page - 1) * per_page
    chunk = cities[start : start + per_page]
    keyboard = new_order_city_keyboard([(c.id, c.name) for c in chunk], page=page, total_pages=total_pages)
    try:
        await message.edit_text("Р’С‹Р±РµСЂРёС‚Рµ РіРѕСЂРѕРґ:", reply_markup=keyboard)
    except TelegramBadRequest:
        # If we cannot edit (e.g., user text message), send a new one
        await message.answer("Р’С‹Р±РµСЂРёС‚Рµ РіРѕСЂРѕРґ:", reply_markup=keyboard)
    except Exception:
        await message.answer("Р’С‹Р±РµСЂРёС‚Рµ РіРѕСЂРѕРґ:", reply_markup=keyboard)
    await state.update_data(city_query=query, city_page=page)


@router.callback_query(
    F.data == "adm:new",
    StaffRoleFilter({StaffRole.GLOBAL_ADMIN, StaffRole.CITY_ADMIN, StaffRole.LOGIST}),
)
async def cb_new_order_start(cq: CallbackQuery, staff: StaffUser, state: FSMContext) -> None:
    await _start_new_order(cq, staff, state)


@router.message(
    Command("cancel"),
    StaffRoleFilter({StaffRole.GLOBAL_ADMIN, StaffRole.CITY_ADMIN, StaffRole.LOGIST}),
)
async def admin_cancel_command(message: Message, staff: StaffUser, state: FSMContext) -> None:
    await state.clear()
    await show_admin_main_menu(
        message,
        staff,
        notice="РЎРѕР·РґР°РЅРёРµ Р·Р°СЏРІРєРё РѕС‚РјРµРЅРµРЅРѕ. Р“Р»Р°РІРЅРѕРµ РјРµРЅСЋ:",
    )


@router.callback_query(F.data == "adm:new:cancel")
async def cb_new_order_cancel(cq: CallbackQuery, staff: StaffUser, state: FSMContext) -> None:
    await state.clear()
    if cq.message:
        await show_admin_main_menu(
            cq.message,
            staff,
            edit=True,
            notice="РЎРѕР·РґР°РЅРёРµ Р·Р°СЏРІРєРё РѕС‚РјРµРЅРµРЅРѕ. Р“Р»Р°РІРЅРѕРµ РјРµРЅСЋ:",
        )
    await cq.answer("РЎРѕР·РґР°РЅРёРµ Р·Р°СЏРІРєРё РѕС‚РјРµРЅРµРЅРѕ")


@router.callback_query(F.data.startswith("adm:new:city_page:"), StateFilter(NewOrderFSM.city))
async def cb_new_order_city_page(cq: CallbackQuery, state: FSMContext) -> None:
    # adm:new:city_page:{page}
    page = int(cq.data.split(":")[3])
    data = await state.get_data()
    query = data.get("city_query")
    await state.set_state(NewOrderFSM.city)
    await _render_city_step(cq.message, state, page=page, query=query)
    await cq.answer()


@router.callback_query(F.data == "adm:new:city_search", StateFilter(NewOrderFSM.city))
async def cb_new_order_city_search(cq: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(NewOrderFSM.city)
    try:
        await cq.message.edit_text("Р’РІРµРґРёС‚Рµ РЅР°Р·РІР°РЅРёРµ РіРѕСЂРѕРґР° (РјРёРЅ. 2 СЃРёРјРІРѕР»Р°). РћС‚РїСЂР°РІСЊС‚Рµ /cancel РґР»СЏ РѕС‚РјРµРЅС‹.")
    except TelegramBadRequest:
        await cq.message.answer("Р’РІРµРґРёС‚Рµ РЅР°Р·РІР°РЅРёРµ РіРѕСЂРѕРґР° (РјРёРЅ. 2 СЃРёРјРІРѕР»Р°). РћС‚РїСЂР°РІСЊС‚Рµ /cancel РґР»СЏ РѕС‚РјРµРЅС‹.")
    except Exception:
        await cq.message.answer("Р’РІРµРґРёС‚Рµ РЅР°Р·РІР°РЅРёРµ РіРѕСЂРѕРґР° (РјРёРЅ. 2 СЃРёРјРІРѕР»Р°). РћС‚РїСЂР°РІСЊС‚Рµ /cancel РґР»СЏ РѕС‚РјРµРЅС‹.")
    await cq.answer()


@router.message(StateFilter(NewOrderFSM.city))
async def new_order_city_input(msg: Message, state: FSMContext) -> None:
    query = msg.text.strip()
    if len(query) < 2:
        await msg.answer("Р’РІРµРґРёС‚Рµ РЅРµ РјРµРЅРµРµ 2 СЃРёРјРІРѕР»РѕРІ.")
        return
    await _render_city_step(msg, state, page=1, query=query)


@router.callback_query(F.data.startswith("adm:new:city:"), StateFilter(NewOrderFSM.city))
async def cb_new_order_city_pick(cq: CallbackQuery, state: FSMContext) -> None:
    # adm:new:city:{id}
    city_id = int(cq.data.split(":")[3])
    orders_service = _orders_service(cq.message.bot)
    city = await orders_service.get_city(city_id)
    if not city:
        await cq.answer("Р“РѕСЂРѕРґ РЅРµ РЅР°Р№РґРµРЅ", show_alert=True)
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
    try:
        await message.edit_text("Р’С‹Р±РµСЂРёС‚Рµ СЂР°Р№РѕРЅ (РёР»Рё Р±РµР· СЂР°Р№РѕРЅР°):", reply_markup=keyboard)
    except TelegramBadRequest:
        await message.answer("Р’С‹Р±РµСЂРёС‚Рµ СЂР°Р№РѕРЅ (РёР»Рё Р±РµР· СЂР°Р№РѕРЅР°):", reply_markup=keyboard)
    except Exception:
        await message.answer("Р’С‹Р±РµСЂРёС‚Рµ СЂР°Р№РѕРЅ (РёР»Рё Р±РµР· СЂР°Р№РѕРЅР°):", reply_markup=keyboard)
    await state.update_data(district_page=page)


@router.callback_query(F.data.startswith("adm:new:district_page:"), StateFilter(NewOrderFSM.district))
async def cb_new_order_district_page(cq: CallbackQuery, state: FSMContext) -> None:
    # adm:new:district_page:{page}
    page = int(cq.data.split(":")[3])
    await state.set_state(NewOrderFSM.district)
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
    await state.update_data(district_id=None, district_name="вЂ”")
    await state.set_state(NewOrderFSM.street_mode)
    await cq.message.edit_text(
        "Р’С‹Р±РµСЂРёС‚Рµ СЃРїРѕСЃРѕР± РІРІРѕРґР° СѓР»РёС†С‹:",
        reply_markup=new_order_street_mode_keyboard(),
    )
    await cq.answer()


@router.callback_query(F.data.startswith("adm:new:district:"), StateFilter(NewOrderFSM.district))
async def cb_new_order_district_pick(cq: CallbackQuery, state: FSMContext) -> None:
    # adm:new:district:{id}
    district_id = int(cq.data.split(":")[3])
    orders_service = _orders_service(cq.message.bot)
    district = await orders_service.get_district(district_id)
    if not district:
        await cq.answer("Р Р°Р№РѕРЅ РЅРµ РЅР°Р№РґРµРЅ", show_alert=True)
        return
    await state.update_data(district_id=district.id, district_name=district.name)
    await state.set_state(NewOrderFSM.street_mode)
    await cq.message.edit_text(
        "Р’С‹Р±РµСЂРёС‚Рµ СЃРїРѕСЃРѕР± РІРІРѕРґР° СѓР»РёС†С‹:",
        reply_markup=new_order_street_mode_keyboard(),
    )
    await cq.answer()
@router.callback_query(F.data == "adm:new:street:search", StateFilter(NewOrderFSM.street_mode))
async def cb_new_order_street_search(cq: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(NewOrderFSM.street_search)
    await cq.message.edit_text("Р’РІРµРґРёС‚Рµ РЅР°Р·РІР°РЅРёРµ СѓР»РёС†С‹ РґР»СЏ РїРѕРёСЃРєР°.")
    await cq.answer()


@router.callback_query(F.data == "adm:new:street:manual", StateFilter(NewOrderFSM.street_mode))
async def cb_new_order_street_manual(cq: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(NewOrderFSM.street_manual)
    await cq.message.edit_text(
        "Р’РІРµРґРёС‚Рµ СѓР»РёС†Сѓ РІСЂСѓС‡РЅСѓСЋ (2вЂ“50 СЃРёРјРІРѕР»РѕРІ).",
        reply_markup=new_order_street_manual_keyboard(),
    )
    await cq.answer()


@router.callback_query(F.data == "adm:new:street:none", StateFilter(NewOrderFSM.street_mode))
async def cb_new_order_street_none(cq: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(street_id=None, street_name="вЂ”", street_manual=None)
    await state.set_state(NewOrderFSM.house)
    await cq.message.edit_text("Р’РІРµРґРёС‚Рµ РґРѕРј (1вЂ“10 СЃРёРјРІРѕР»РѕРІ).")
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
        await msg.answer("Р’РІРµРґРёС‚Рµ СЃС‚СЂРѕРєСѓ РґР»РёРЅРѕР№ РѕС‚ 2 РґРѕ 50 СЃРёРјРІРѕР»РѕРІ.")
        return
    await state.update_data(street_id=None, street_name=value, street_manual=value)
    await state.set_state(NewOrderFSM.house)
    await msg.answer("Р’РІРµРґРёС‚Рµ РґРѕРј (1вЂ“10 СЃРёРјРІРѕР»РѕРІ).")


@router.message(StateFilter(NewOrderFSM.street_search))
async def new_order_street_search_input(msg: Message, state: FSMContext) -> None:
    query = msg.text.strip()
    if len(query) < 2:
        await msg.answer("Р’РІРµРґРёС‚Рµ РЅРµ РјРµРЅРµРµ 2 СЃРёРјРІРѕР»РѕРІ.")
        return
    data = await state.get_data()
    city_id = data.get("city_id")
    orders_service = _orders_service(msg.bot)
    streets = await orders_service.search_streets(city_id, query)
    # If nothing found, offer a way back to street mode selection
    if not streets:
        try:
            await msg.answer("  .     .")
        finally:
            await state.set_state(NewOrderFSM.street_mode)
            await msg.answer(
                "   :",
                reply_markup=new_order_street_mode_keyboard(),
            )
        return
    if not streets:
        await msg.answer("РќРёС‡РµРіРѕ РЅРµ РЅР°Р№РґРµРЅРѕ. Р·РјРµРЅРёС‚Рµ Р·Р°РїСЂРѕСЃ Рё РїРѕРїСЂРѕР±СѓР№С‚Рµ СЃРЅРѕРІР°.")
        return
    buttons = [
        (s.id, s.name if s.score is None else f"{s.name} ({int(s.score)}%)")
        for s in streets
    ]
    await msg.answer(
        "Р РµР·СѓР»СЊС‚Р°С‚С‹ РїРѕРёСЃРєР°:",
        reply_markup=new_order_street_keyboard(buttons),
    )
    await state.set_state(NewOrderFSM.street_mode)
    await state.update_data(street_search_results=buttons)


@router.callback_query(F.data.startswith("adm:new:street:"), StateFilter(NewOrderFSM.street_mode))
async def cb_new_order_street_pick(cq: CallbackQuery, state: FSMContext) -> None:
    # adm:new:street:{id|search_again|manual_back|back}
    tail = cq.data.split(":")[3]
    if tail == "search_again":
        await state.set_state(NewOrderFSM.street_search)
        await cq.message.edit_text("Р’РІРµРґРёС‚Рµ РЅР°Р·РІР°РЅРёРµ СѓР»РёС†С‹ РґР»СЏ РїРѕРёСЃРєР°.")
        await cq.answer()
        return
    if tail == "manual_back":
        await state.set_state(NewOrderFSM.street_mode)
        await cq.message.edit_text(
            "Р’С‹Р±РµСЂРёС‚Рµ СЃРїРѕСЃРѕР± РІРІРѕРґР° СѓР»РёС†С‹:",
            reply_markup=new_order_street_mode_keyboard(),
        )
        await cq.answer()
        return
    if tail == "back":
        await state.set_state(NewOrderFSM.street_mode)
        await cq.message.edit_text(
            "Р’С‹Р±РµСЂРёС‚Рµ СЃРїРѕСЃРѕР± РІРІРѕРґР° СѓР»РёС†С‹:",
            reply_markup=new_order_street_mode_keyboard(),
        )
        await cq.answer()
        return
    street_id = int(tail)
    orders_service = _orders_service(cq.message.bot)
    street = await orders_service.get_street(street_id)
    if not street:
        await cq.answer("РЈР»РёС†Р° РЅРµ РЅР°Р№РґРµРЅР°", show_alert=True)
        return
    await state.update_data(street_id=street.id, street_name=street.name, street_manual=None)
    await state.set_state(NewOrderFSM.house)
    await cq.message.edit_text("Р’РІРµРґРёС‚Рµ РґРѕРј (1вЂ“10 СЃРёРјРІРѕР»РѕРІ).")
    await cq.answer()


@router.message(StateFilter(NewOrderFSM.house))
async def new_order_house(msg: Message, state: FSMContext) -> None:
    value = msg.text.strip()
    if not (1 <= len(value) <= 10):
        await msg.answer("Р’РІРµРґРёС‚Рµ РѕС‚ 1 РґРѕ 10 СЃРёРјРІРѕР»РѕРІ.")
        return
    await state.update_data(house=value)
    await state.set_state(NewOrderFSM.apartment)
    await msg.answer("Р’РІРµРґРёС‚Рµ РЅРѕРјРµСЂ РєРІР°СЂС‚РёСЂС‹ (РёР»Рё '-' С‡С‚РѕР±С‹ РїСЂРѕРїСѓСЃС‚РёС‚СЊ).")


@router.message(StateFilter(NewOrderFSM.apartment))
async def new_order_apartment(msg: Message, state: FSMContext) -> None:
    value = msg.text.strip()
    if value == "-":
        value = ""
    if len(value) > 10:
        await msg.answer("РЎР»РёС€РєРѕРј РґР»РёРЅРЅРѕРµ Р·РЅР°С‡РµРЅРёРµ. Р”Рѕ 10 СЃРёРјРІРѕР»РѕРІ.")
        return
    await state.update_data(apartment=value or None)
    await state.set_state(NewOrderFSM.address_comment)
    await msg.answer("РљРѕРјРјРµРЅС‚Р°СЂРёР№ Рє Р°РґСЂРµСЃСѓ (РёР»Рё '-' С‡С‚РѕР±С‹ РїСЂРѕРїСѓСЃС‚РёС‚СЊ).")


@router.message(StateFilter(NewOrderFSM.address_comment))
async def new_order_address_comment(msg: Message, state: FSMContext) -> None:
    value = msg.text.strip()
    if value == "-":
        value = ""
    await state.update_data(address_comment=value or None)
    await state.set_state(NewOrderFSM.client_name)
    await msg.answer("Р’РІРµРґРёС‚Рµ Р¤Рћ РєР»РёРµРЅС‚Р° (2вЂ“30 СЃРёРјРІРѕР»РѕРІ, РєРёСЂРёР»Р»РёС†Р°).")


@router.message(StateFilter(NewOrderFSM.client_name))
async def new_order_client_name(msg: Message, state: FSMContext) -> None:
    value = msg.text.strip()
    if not _validate_name(value):
        await msg.answer("РјСЏ РґРѕР»Р¶РЅРѕ СЃРѕРґРµСЂР¶Р°С‚СЊ 2вЂ“30 СЃРёРјРІРѕР»РѕРІ (РєРёСЂРёР»Р»РёС†Р°, РїСЂРѕР±РµР»С‹ Рё С‚РёСЂРµ).")
        return
    await state.update_data(client_name=value)
    await state.set_state(NewOrderFSM.client_phone)
    await msg.answer("Р’РІРµРґРёС‚Рµ С‚РµР»РµС„РѕРЅ РєР»РёРµРЅС‚Р° (+7XXXXXXXXXX РёР»Рё 8XXXXXXXXXX).")


@router.message(StateFilter(NewOrderFSM.client_phone))
async def new_order_client_phone(msg: Message, state: FSMContext) -> None:
    raw = _normalize_phone(msg.text)
    if not _validate_phone(raw):
        await msg.answer("РќРµРІРµСЂРЅС‹Р№ С„РѕСЂРјР°С‚ С‚РµР»РµС„РѕРЅР°. РџСЂРёРјРµСЂ: +71234567890 РёР»Рё 81234567890.")
        return
    await state.update_data(client_phone=raw)
    await state.set_state(NewOrderFSM.category)
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    kb = InlineKeyboardBuilder()
    for category, label in CATEGORY_CHOICES:
        kb.button(text=label, callback_data=f"adm:new:cat:{category.value}")
    kb.adjust(2)
    await msg.answer("Р’С‹Р±РµСЂРёС‚Рµ РєР°С‚РµРіРѕСЂРёСЋ Р·Р°СЏРІРєРё:", reply_markup=kb.as_markup())


@router.callback_query(F.data.startswith("adm:new:cat:"), StateFilter(NewOrderFSM.category))
async def cb_new_order_category(cq: CallbackQuery, state: FSMContext) -> None:
    # adm:new:cat:{value}
    raw = cq.data.split(":")[3]
    category = normalize_category(raw)
    if category is None:
        await cq.answer("РќРµРёР·РІРµСЃС‚РЅР°СЏ РєР°С‚РµРіРѕСЂРёСЏ", show_alert=True)
        return
    await state.update_data(
        category=category,
        category_label=CATEGORY_LABELS.get(category, CATEGORY_LABELS_BY_VALUE.get(raw, raw)),
    )
    await state.set_state(NewOrderFSM.description)
    await cq.message.edit_text("Р’РІРµРґРёС‚Рµ РѕРїРёСЃР°РЅРёРµ Р·Р°СЏРІРєРё (10вЂ“500 СЃРёРјРІРѕР»РѕРІ).")
    await cq.answer()


@router.message(StateFilter(NewOrderFSM.description))
async def new_order_description(msg: Message, state: FSMContext) -> None:
    text = msg.text.strip()
    if not (10 <= len(text) <= 500):
        await msg.answer("Р’РІРµРґРёС‚Рµ РѕС‚ 10 РґРѕ 500 СЃРёРјРІРѕР»РѕРІ.")
        return
    await state.update_data(description=text)
    await state.set_state(NewOrderFSM.attachments)
    await msg.answer(
        "РћС‚РїСЂР°РІСЊС‚Рµ РІР»РѕР¶РµРЅРёСЏ (С„РѕС‚Рѕ/РґРѕРєСѓРјРµРЅС‚С‹) РёР»Рё РЅР°Р¶РјРёС‚Рµ 'РџСЂРѕРґРѕР»Р¶РёС‚СЊ'.",
        reply_markup=new_order_attachments_keyboard(False),
    )


@router.callback_query(F.data == "adm:new:att:add", StateFilter(NewOrderFSM.attachments))
async def cb_new_order_att_add(cq: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(NewOrderFSM.attachments)
    await cq.answer("РїС—Р…РїС—Р…РїС—Р…РїС—Р…РїС—Р…РїС—Р…РїС—Р…РїС—Р…РїС—Р… РїС—Р…РїС—Р…РїС—Р…РїС—Р… РїС—Р…РїС—Р…РїС—Р… РїС—Р…РїС—Р…РїС—Р…РїС—Р…РїС—Р…РїС—Р…РїС—Р…РїС—Р… РїС—Р…РїС—Р…РїС—Р…РїС—Р…РїС—Р…РїС—Р…РїС—Р…РїС—Р…РїС—Р…РїС—Р…")


@router.callback_query(F.data == "adm:new:att:clear", StateFilter(NewOrderFSM.attachments))
async def cb_new_order_att_clear(cq: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    data["attachments"] = []
    await state.update_data(**data)
    await state.set_state(NewOrderFSM.attachments)
    await cq.message.edit_text(
        "Р’Р»РѕР¶РµРЅРёСЏ РѕС‡РёС‰РµРЅС‹. РњРѕР¶РЅРѕ РѕС‚РїСЂР°РІРёС‚СЊ РЅРѕРІС‹Рµ С„Р°Р№Р»С‹.",
        reply_markup=new_order_attachments_keyboard(False),
    )
    await cq.answer()


@router.message(StateFilter(NewOrderFSM.attachments), F.photo)
async def new_order_attach_photo(msg: Message, state: FSMContext) -> None:
    attachments = _attachments_from_state(await state.get_data())
    if len(attachments) >= ATTACHMENTS_LIMIT:
        await msg.answer("Р”РѕСЃС‚РёРіРЅСѓС‚ Р»РёРјРёС‚ РІР»РѕР¶РµРЅРёР№. РЈРґР°Р»РёС‚Рµ Р»РёС€РЅРёРµ С„Р°Р№Р»С‹.")
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
        f"Р¤РѕС‚Рѕ РґРѕР±Р°РІР»РµРЅРѕ. Р’СЃРµРіРѕ РІР»РѕР¶РµРЅРёР№: {len(attachments)}.",
        reply_markup=new_order_attachments_keyboard(True),
    )


@router.message(StateFilter(NewOrderFSM.attachments), F.document)
async def new_order_attach_doc(msg: Message, state: FSMContext) -> None:
    attachments = _attachments_from_state(await state.get_data())
    if len(attachments) >= ATTACHMENTS_LIMIT:
        await msg.answer("Р”РѕСЃС‚РёРіРЅСѓС‚ Р»РёРјРёС‚ РІР»РѕР¶РµРЅРёР№. РЈРґР°Р»РёС‚Рµ Р»РёС€РЅРёРµ С„Р°Р№Р»С‹.")
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
        f"Р¤Р°Р№Р» РґРѕР±Р°РІР»РµРЅ. Р’СЃРµРіРѕ РІР»РѕР¶РµРЅРёР№: {len(attachments)}.",
        reply_markup=new_order_attachments_keyboard(True),
    )
@router.callback_query(F.data == "adm:new:att:done", StateFilter(NewOrderFSM.attachments))
async def cb_new_order_att_done(cq: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(NewOrderFSM.order_type)
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    kb = InlineKeyboardBuilder()
    kb.button(text="РћР±С‹С‡РЅР°СЏ", callback_data="adm:new:type:NORMAL")
    kb.button(text="Р“Р°СЂР°РЅС‚РёР№РЅР°СЏ", callback_data="adm:new:type:GUARANTEE")
    kb.adjust(2)
    await cq.message.edit_text("Р’С‹Р±РµСЂРёС‚Рµ С‚РёРї Р·Р°СЏРІРєРё:", reply_markup=kb.as_markup())
    await cq.answer()


@router.callback_query(F.data.startswith("adm:new:type:"), StateFilter(NewOrderFSM.order_type))
async def cb_new_order_type(cq: CallbackQuery, state: FSMContext) -> None:
    # adm:new:type:{code}
    code = cq.data.split(":")[3]
    await state.update_data(
        order_type=code,
        company_payment=2500 if code == "GUARANTEE" else 0,
        initial_status=None,
    )
    await state.set_state(NewOrderFSM.slot)
    data = await state.get_data()
    city_id = data.get("city_id")
    if not city_id:
        await cq.answer("РЎРЅР°С‡Р°Р»Р° РІС‹Р±РµСЂРёС‚Рµ РіРѕСЂРѕРґ.", show_alert=True)
        return
    tz = await _resolve_city_timezone(cq.message.bot, city_id)
    workday_start, workday_end = await _resolve_workday_window()
    now_local = time_service.now_in_city(tz)
    options = _slot_options(now_local, workday_start=workday_start, workday_end=workday_end)
    options = [(k, _maybe_fix_mojibake(lbl)) for (k, lbl) in options]
    await state.update_data(
        slot_options=options,
        city_timezone=_zone_storage_value(tz),
        pending_asap=False,
    )
    keyboard = new_order_slot_keyboard(options)
    await cq.message.edit_text("Р’С‹Р±РµСЂРёС‚Рµ СЃР»РѕС‚:", reply_markup=keyboard)
    await cq.answer()


@router.callback_query(F.data.startswith("adm:new:slot:"), StateFilter(NewOrderFSM.slot))
async def cb_new_order_slot(cq: CallbackQuery, state: FSMContext) -> None:
    # adm:new:slot:{key}
    key = ":".join(cq.data.split(":")[3:])
    data = await state.get_data()
    city_id = data.get("city_id")
    if not city_id:
        await cq.answer("РЎРЅР°С‡Р°Р»Р° РІС‹Р±РµСЂРёС‚Рµ РіРѕСЂРѕРґ.", show_alert=True)
        return
    await state.set_state(NewOrderFSM.slot)
    options = data.get("slot_options") or []
    valid_keys = {item[0] for item in options}
    if key not in valid_keys:
        await cq.answer("РќРµРІРµСЂРЅС‹Р№ РІС‹Р±РѕСЂ СЃР»РѕС‚Р°", show_alert=True)
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
            await state.set_state(NewOrderFSM.slot)
            await cq.message.edit_text(
                "ASAP РїРѕР·Р¶Рµ 19:30. Р’С‹Р±СЂР°С‚СЊ Р·Р°РІС‚СЂР° 10вЂ“13?",
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
        refreshed_options = [(k, _maybe_fix_mojibake(lbl)) for (k, lbl) in refreshed_options]
        await state.update_data(slot_options=refreshed_options, pending_asap=False, initial_status=None)
        await state.set_state(NewOrderFSM.slot)
        await cq.message.edit_text(
            "РЎР»РѕС‚ СѓСЃС‚Р°СЂРµР». Р’С‹Р±РµСЂРёС‚Рµ РІР°СЂРёР°РЅС‚ СЃРЅРѕРІР°:",
            reply_markup=new_order_slot_keyboard(refreshed_options),
        )
        await cq.answer("РЎР»РѕС‚ СѓСЃС‚Р°СЂРµР», РІС‹Р±РµСЂРёС‚Рµ СЃРЅРѕРІР°", show_alert=True)
        return
    await cq.answer()

@router.callback_query(F.data == "adm:new:slot:lateok", StateFilter(NewOrderFSM.slot))
async def cb_new_order_slot_lateok(cq: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    city_id = data.get("city_id")
    if not city_id:
        await cq.answer("РЎРЅР°С‡Р°Р»Р° РІС‹Р±РµСЂРёС‚Рµ РіРѕСЂРѕРґ.", show_alert=True)
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
        await cq.answer("РЎРЅР°С‡Р°Р»Р° РІС‹Р±РµСЂРёС‚Рµ РіРѕСЂРѕРґ.", show_alert=True)
        return
    await state.set_state(NewOrderFSM.slot)
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
    options = [(k, _maybe_fix_mojibake(lbl)) for (k, lbl) in options]
    await state.update_data(slot_options=options, pending_asap=False, initial_status=None)
    await cq.message.edit_text("Р’С‹Р±РµСЂРёС‚Рµ СЃР»РѕС‚:", reply_markup=new_order_slot_keyboard(options))
    await cq.answer()



@router.callback_query(F.data == "adm:new:confirm", StateFilter(NewOrderFSM.confirm))
async def cb_new_order_confirm(cq: CallbackQuery, state: FSMContext, staff: StaffUser | None = None) -> None:
    # Be robust if middleware didn't inject staff for some reason
    if staff is None:
        staff_service = _staff_service(cq.message.bot)
        staff = await staff_service.get_by_tg_id(cq.from_user.id if cq.from_user else 0)
        if staff is None:
            await cq.answer("РќРµС‚ РґРѕСЃС‚СѓРїР°", show_alert=True)
            return
    data = await state.get_data()
    try:
        new_order = _build_new_order_data(data, staff)
    except KeyError:
        await state.clear()
        await cq.answer("РќРµ С…РІР°С‚Р°РµС‚ РґР°РЅРЅС‹С… РґР»СЏ СЃРѕР·РґР°РЅРёСЏ Р·Р°СЏРІРєРё, РїРѕРїСЂРѕР±СѓР№С‚Рµ Р·Р°РЅРѕРІРѕ", show_alert=True)
        return
    orders_service = _orders_service(cq.message.bot)
    order_id = await orders_service.create_order(new_order)
    await state.clear()
    await cq.answer("Р—Р°СЏРІРєР° СЃРѕР·РґР°РЅР°")
    await _render_created_order_card(cq.message, order_id, staff)





@router.callback_query(
    F.data == "adm:s",
    StaffRoleFilter({StaffRole.GLOBAL_ADMIN}),
)
async def cb_settings_menu(cq: CallbackQuery, staff: StaffUser) -> None:
    await cq.message.edit_text(
        "<b>РќР°СЃС‚СЂРѕР№РєРё</b>\nР’С‹Р±РµСЂРёС‚Рµ РіСЂСѓРїРїСѓ РЅР°СЃС‚СЂРѕРµРє РґР»СЏ СЂРµРґР°РєС‚РёСЂРѕРІР°РЅРёСЏ.",
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
        await cq.answer("РќРµРёР·РІРµСЃС‚РЅР°СЏ РіСЂСѓРїРїР° РЅР°СЃС‚СЂРѕРµРє", show_alert=True)
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
        await cq.answer("РќРµРєРѕСЂСЂРµРєС‚РЅС‹Рµ РїР°СЂР°РјРµС‚СЂС‹", show_alert=True)
        return
    _, _, _, group_key, field_key = parts
    try:
        field = _get_setting_field(field_key)
    except KeyError:
        await cq.answer("РќРµРёР·РІРµСЃС‚РЅРѕРµ РїРѕР»Рµ РЅР°СЃС‚СЂРѕР№РєРё", show_alert=True)
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
    await msg.answer("Р·РјРµРЅРµРЅРёРµ РѕС‚РјРµРЅРµРЅРѕ.")


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
        await msg.answer("РЎРѕСЃС‚РѕСЏРЅРёРµ СѓСЃС‚Р°СЂРµР»Рѕ. РџРѕРІС‚РѕСЂРёС‚Рµ РґРµР№СЃС‚РІРёРµ.")
        return

    try:
        field = _get_setting_field(field_key)
    except KeyError:
        await state.clear()
        await msg.answer("РќРµРёР·РІРµСЃС‚РЅРѕРµ РїРѕР»Рµ РЅР°СЃС‚СЂРѕР№РєРё.")
        return

    if not msg.text:
        await msg.answer("РћС‚РїСЂР°РІСЊС‚Рµ Р·РЅР°С‡РµРЅРёРµ С‚РµРєСЃС‚РѕРј.")
        return

    try:
        value, value_type = _parse_setting_input(field, msg.text)
    except ValueError as exc:
        await msg.answer(str(exc))
        return

    service = _settings_service(msg.bot)
    await service.set_value(field.key, value, value_type=value_type)
    await state.clear()
    await msg.answer("РќР°СЃС‚СЂРѕР№РєР° СЃРѕС…СЂР°РЅРµРЅР°.")

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
    await cq.answer("Р“РѕС‚РѕРІРѕ")

