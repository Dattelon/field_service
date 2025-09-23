from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any, Optional, Sequence

from aiogram import F, Router, Bot
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message, InlineKeyboardButton, InlineKeyboardMarkup

from field_service.config import settings as env_settings
from field_service.services import export_service, live_log
from field_service.services.settings_service import get_timezone

FINANCE_SEGMENT_TITLES = {
    'aw': 'Ожидают оплаты',
    'pd': 'Оплаченные',
    'ov': 'Просроченные',
}

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
from .states import (FinanceActionFSM, NewOrderFSM, OwnerPayEditFSM, SettingsEditFSM)
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

LOCAL_TZ = get_timezone()
PHONE_RE = re.compile(r"^(?:\+7|8)\d{10}$")
NAME_RE = re.compile(r"^[�-ߨ�-��\-\s]{2,30}$")
ATTACHMENTS_LIMIT = 5
CATEGORY_CHOICES = [
    ("ELECTRICS", "���������"),
    ("PLUMBING", "����������"),
    ("APPLIANCES", "������� �������"),
    ("WINDOWS", "����"),
    ("HANDYMAN", "���������"),
    ("ROADSIDE", "����������"),
]
CATEGORY_LABELS = {code: label for code, label in CATEGORY_CHOICES}
LATE_ASAP_THRESHOLD = time(19, 30)
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
        title="?? ������� ����",
        description="������ �� �������������� ������� ������ ����� DEFERRED � SEARCHING.",
        fields=(
            SettingFieldDef(
                key="working_hours_start",
                label="������",
                schema="time",
                value_type="TIME",
                default=env_settings.working_hours_start,
                help_text="������ ��:��, ������ 10:00.",
            ),
            SettingFieldDef(
                key="working_hours_end",
                label="���������",
                schema="time",
                value_type="TIME",
                default=env_settings.working_hours_end,
                help_text="������ ��:��, ������ 20:00.",
            ),
        ),
    ),
    "distribution": SettingGroupDef(
        key="distribution",
        title="?? �������������",
        description="��������� �������� ������������ � SLA �������.",
        fields=(
            SettingFieldDef(
                key="distribution_tick_seconds",
                label="��� ������������ (���)",
                schema="int",
                value_type="INT",
                default=30,
            ),
            SettingFieldDef(
                key="distribution_sla_seconds",
                label="SLA ������ (���)",
                schema="int",
                value_type="INT",
                default=env_settings.distribution_sla_seconds,
            ),
            SettingFieldDef(
                key="distribution_rounds",
                label="���������� �������",
                schema="int",
                value_type="INT",
                default=env_settings.distribution_rounds,
            ),
            SettingFieldDef(
                key="escalate_to_admin_after_min",
                label="��������� ������ (���)",
                schema="int_non_negative",
                value_type="INT",
                default=10,
            ),
            SettingFieldDef(
                key="distribution_log_topn",
                label="������� ���������� ����������",
                schema="int",
                value_type="INT",
                default=10,
            ),
        ),
    ),
    "limits": SettingGroupDef(
        key="limits",
        title="?? ������",
        fields=(
            SettingFieldDef(
                key="max_active_orders",
                label="�������� �������� ������� �� �������",
                schema="int",
                value_type="INT",
                default=1,
            ),
        ),
    ),
    "support": SettingGroupDef(
        key="support",
        title="?? ���������",
        description="������������ ��� ��������� �������� � ��������.",
        fields=(
            SettingFieldDef(
                key="support_contact",
                label="������� ���������",
                schema="string",
                value_type="STR",
                help_text="������� �������, @username ��� ������.",
            ),
            SettingFieldDef(
                key="support_faq_url",
                label="������ �� FAQ",
                schema="string_optional",
                value_type="STR",
                help_text="������� URL ��� '-' ����� ��������.",
            ),
        ),
    ),
    "geo": SettingGroupDef(
        key="geo",
        title="??? ��������",
        fields=(
            SettingFieldDef(
                key="geo_mode",
                label="�����",
                schema="choice",
                value_type="STR",
                choices=(
                    ("local_centroids", "��������� ���������"),
                    ("yandex", "������"),
                ),
                default="local_centroids",
                help_text="1 � ��������, 2 � ������ API.",
            ),
            SettingFieldDef(
                key="yandex_geocoder_key",
                label="API ���� ������",
                schema="string_optional",
                value_type="STR",
                help_text="�������� ���� ��� '-' ����� ��������.",
            ),
            SettingFieldDef(
                key="yandex_throttle_rps",
                label="RPS �����",
                schema="int_non_negative",
                value_type="INT",
                default=1,
            ),
            SettingFieldDef(
                key="yandex_daily_limit",
                label="�������� �����",
                schema="int_non_negative",
                value_type="INT",
                default=1000,
            ),
        ),
    ),
    "channels": SettingGroupDef(
        key="channels",
        title="?? ������ �����������",
        description="������������ ����� ��� �������� ����� � �������.",
        fields=(
            SettingFieldDef(
                key="alerts_channel_id",
                label="Alerts / ������",
                schema="int_optional",
                value_type="STR",
                help_text="ID ���� ��� '-' ����� ��������.",
            ),
            SettingFieldDef(
                key="logs_channel_id",
                label="����� �����",
                schema="int_optional",
                value_type="STR",
                help_text="ID ���� ��� '-' ����� ��������.",
            ),
            SettingFieldDef(
                key="reports_channel_id",
                label="����� �������",
                schema="int_optional",
                value_type="STR",
                help_text="ID ���� ��� '-' ����� ��������.",
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


EMPTY_PLACEHOLDER = "�"
SCHEMA_DEFAULT_HELP = {
    "time": "������ ��:��, ������ 10:00.",
    "int": "������� ����� ����� ������ 0.",
    "int_non_negative": "������� ����� ����� �� ������ 0.",
    "string": "������� �����.",
    "string_optional": "������� ����� ��� '-' ����� ��������.",
    "int_optional": "������� ID ���� ��� '-' ����� ��������.",
    "choice": "��������� ����� �������� ��� ��������." ,
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
        lines.append(f"������� ��������: <code>{html.escape(current_display, quote=False)}</code>")
    base_help = SCHEMA_DEFAULT_HELP.get(field.schema, "������� ��������.")
    if field.schema == "choice":
        options = _choice_help(field)
        if options:
            lines.append(base_help)
            lines.append(options)
        else:
            lines.append(base_help)
    else:
        lines.append(field.help_text or base_help)
    lines.append("��������� /cancel ��� ������.")
    return "".join(lines)


def _parse_setting_input(field: SettingFieldDef, user_input: str) -> tuple[str, str]:
    text = (user_input or "").strip()
    if field.schema in {"string_optional", "int_optional"} and text in {"", "-"}:
        return "", field.value_type
    if field.schema == "time":
        if not re.fullmatch(r"^\d{1,2}:\d{2}$", text):
            raise ValueError("������� ����� � ������� ��:��.")
        hh, mm = map(int, text.split(":"))
        if not (0 <= hh < 24 and 0 <= mm < 60):
            raise ValueError("�������� �������� �������.")
        return text, field.value_type
    if field.schema == "int":
        try:
            value = int(text)
        except ValueError:
            raise ValueError("������� ����� �����.")
        if value <= 0:
            raise ValueError("����� ������ ���� ������ 0.")
        return str(value), field.value_type
    if field.schema == "int_non_negative":
        try:
            value = int(text)
        except ValueError:
            raise ValueError("������� ����� �����.")
        if value < 0:
            raise ValueError("����� ������ ���� �� ������ 0.")
        return str(value), field.value_type
    if field.schema == "int_optional":
        try:
            value = int(text)
        except ValueError:
            raise ValueError("������� ����� ����� ��� '-' ��� �������.")
        return str(value), field.value_type
    if field.schema == "choice":
        normalized = text.lower()
        if field.choices:
            for idx, (code, label) in enumerate(field.choices, 1):
                if normalized in {code.lower(), label.lower(), str(idx)}:
                    return code, field.value_type
        raise ValueError("�������� ������� �� ������.")
    if field.schema == "string_optional":
        return text, field.value_type
    if field.schema == "string":
        if not text:
            raise ValueError("�������� �� ����� ���� ������.")
        return text, field.value_type
    raise ValueError("���������������� ��� ���������.")


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
            value_line += " <i>(�� ���������)</i>"
        lines.append(value_line)
    lines.append("�������� �������� ��� ��������������.")
    keyboard = settings_group_keyboard(
        group_key,
        [(field.key, field.label) for field in group.fields],
    )
    return "".join(lines), keyboard

def _format_log_entries(entries: Sequence[live_log.LiveLogEntry]) -> str:
    if not entries:
        return '<b>����� ����</b>\n���� ������� ���.'
    lines = ['<b>����� ����</b>']
    for entry in entries:
        local_time = entry.timestamp.astimezone(LOCAL_TZ)
        body = html.escape(entry.message, quote=False).replace('\n', '<br>')
        lines.append(f'[{{local_time:%H:%M:%S}}] <i>{{entry.source}}</i> � {{body}}')
    return '\n'.join(lines)






def _city_filter(staff: StaffUser) -> Optional[Sequence[int]]:
    if staff.role is StaffRole.GLOBAL_ADMIN:
        return None
    return list(staff.city_ids)


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
        extra = f"(�����: {manual_street})"
        address_comment = f"{address_comment} {extra}".strip() if address_comment else extra
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
        attachments=attachments,
    )


def _slot_options(now: datetime) -> list[tuple[str, str, Optional[date], Optional[time], Optional[time]]]:
    today = now.date()
    today_options = [
        ("today_10_13", "������� 10:00-13:00", time(10, 0), time(13, 0)),
        ("today_13_16", "������� 13:00-16:00", time(13, 0), time(16, 0)),
        ("today_16_19", "������� 16:00-19:00", time(16, 0), time(19, 0)),
    ]
    tomorrow = today + timedelta(days=1)
    tomorrow_options = [
        ("tomorrow_10_13", "������ 10:00-13:00", time(10, 0), time(13, 0)),
        ("tomorrow_13_16", "������ 13:00-16:00", time(13, 0), time(16, 0)),
        ("tomorrow_16_19", "������ 16:00-19:00", time(16, 0), time(19, 0)),
    ]
    options: list[tuple[str, str, Optional[date], Optional[time], Optional[time]]] = [
        ("asap", "ASAP", None, None, None)
    ]
    current_time = now.time()
    for key, label, start, end in today_options:
        if current_time < end:
            options.append((key, label, today, start, end))
    for key, label, start, end in tomorrow_options:
        options.append((key, label, tomorrow, start, end))
    return options


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
        "�����-��� Field Service. �������� ������:",
        reply_markup=main_menu(staff),
    )


@router.message(CommandStart())
async def not_allowed_start(message: Message) -> None:
    await message.answer(
        "������, � ��� ��� ������� � �����-����. ���������� � ����������� ��������������.",
    )


@router.callback_query(
    F.data == "adm:menu",
    StaffRoleFilter({StaffRole.GLOBAL_ADMIN, StaffRole.CITY_ADMIN, StaffRole.LOGIST}),
)
async def cb_menu(cq: CallbackQuery, staff: StaffUser) -> None:
    await cq.message.edit_text("������� ����:", reply_markup=main_menu(staff))
    await cq.answer()


@router.callback_query(
    F.data == "adm:f",
    StaffRoleFilter({StaffRole.GLOBAL_ADMIN, StaffRole.CITY_ADMIN}),
)
async def cb_finance_root(cq: CallbackQuery, staff: StaffUser, state: FSMContext) -> None:
    await state.clear()
    await cq.message.edit_text("Выберите раздел:", reply_markup=finance_menu(staff))
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
        city_ids=_city_filter(staff),
    )

    await state.update_data(fin_segment=segment, fin_page=page)

    title = FINANCE_SEGMENT_TITLES.get(segment, segment.upper())
    if not rows:
        text = f"<b>{title}</b>\nКомиссии не найдены."
    else:
        lines = [f"<b>{title}</b>", ""]
        for row in rows:
            if isinstance(row, CommissionListItem):
                lines.append(f"• {html.escape(finance_list_line(row))}")
            else:
                lines.append(f"• {html.escape(str(row))}")
        text = "\n".join(lines)

    button_rows: list[list[InlineKeyboardButton]] = []
    for row in rows:
        if isinstance(row, CommissionListItem):
            label = f"#{row.id} · {row.amount:.0f} ₽"
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
        await cq.answer("Комиссия не найдена.", show_alert=True)
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
            await cq.answer("Чеки отсутствуют.", show_alert=True)
            return
        for attachment in detail.attachments:
            try:
                file_type = (attachment.file_type or "").upper()
                if file_type == "PHOTO":
                    await cq.message.answer_photo(attachment.file_id, caption=attachment.caption)
                else:
                    await cq.message.answer_document(attachment.file_id, caption=attachment.caption)
            except TelegramBadRequest:
                await cq.message.answer("Не удалось показать вложение чека.")
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
            "Введите фактическую сумму оплаты (по умолчанию {amount:.2f}).\n"
            "Отправьте /skip, чтобы оставить значение без изменений."
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
            "Мастер заблокирован." if ok else "Не удалось заблокировать мастера.",
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
            "Укажите причину отклонения платежа (текстом) или нажмите «Назад».",
            reply_markup=finance_reject_cancel_keyboard(commission_id),
        )
        await cq.answer()
        return

    await cq.answer()
@router.message(StateFilter(FinanceActionFSM.reject_reason))
async def finance_reject_reason(msg: Message, staff: StaffUser, state: FSMContext) -> None:
    reason = (msg.text or "").strip()
    if len(reason) < 3:
        await msg.answer("Текст должен содержать не менее 3 символов.")
        return

    data = await state.get_data()
    commission_id = data.get("commission_id")
    segment = data.get("segment", "aw")
    page = int(data.get("page", 1))
    source_chat_id = data.get("source_chat_id")
    source_message_id = data.get("source_message_id")

    if not commission_id:
        await state.clear()
        await msg.answer("Сессия истекла. Откройте карточку комиссии заново.")
        return

    finance_service = _finance_service(msg.bot)
    ok = await finance_service.reject(int(commission_id), reason=reason, by_staff_id=staff.id)
    await state.clear()
    if ok:
        live_log.push("finance", f"commission#{commission_id} rejected by staff {staff.id}")
        await msg.answer("Отправлено мастеру на доработку.")
    else:
        await msg.answer("Не удалось отклонить оплату.")
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
        await msg.answer("Сессия подтверждения истекла. Откройте комиссию заново.")
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
        await msg.answer("Подтверждение отменено.")
        return

    if text_value.lower() in {"/skip", "skip", "пропустить", ""}:
        amount = default_amount
    else:
        normalized = text_value.replace(",", ".")
        if not re.fullmatch(r"^\d{1,7}(?:\.\d{1,2})?$", normalized):
            await msg.answer("Введите сумму в формате 3500 или 4999.99, либо отправьте /skip.")
            return
        amount = Decimal(normalized)

    finance_service = _finance_service(msg.bot)
    ok = await finance_service.approve(int(commission_id), paid_amount=amount, by_staff_id=staff.id)
    await state.clear()
    if ok:
        live_log.push("finance", f"commission#{commission_id} approved by staff {staff.id} amount={amount}")
        await msg.answer("Комиссия подтверждена.")
        if source_chat_id and source_message_id:
            proxy = _MessageEditProxy(msg.bot, source_chat_id, source_message_id)
            await _render_finance_segment(proxy, staff, segment, page, state)
    else:
        await msg.answer("Не удалось подтвердить оплату.")

@router.callback_query(
    F.data == "adm:f:set",
    StaffRoleFilter({StaffRole.GLOBAL_ADMIN}),
)
async def cb_finance_owner_snapshot(cq: CallbackQuery) -> None:
    settings_service = _settings_service(cq.message.bot)
    snapshot = await settings_service.get_owner_pay_snapshot()
    text = "<b>������� ��������� ���������</b>\n" + json.dumps(snapshot, ensure_ascii=False, indent=2)
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
        "�������� JSON � ����������� ����������� (methods, card, sbp � �.�.), ��� /cancel.",
    )
    await cq.answer()


@router.message(StateFilter(OwnerPayEditFSM.value))
async def finance_owner_edit_value(msg: Message, state: FSMContext) -> None:
    try:
        payload = json.loads(msg.text)
    except json.JSONDecodeError:
        await msg.answer("�� ������� ���������� JSON. ���������� ��� ��� ��� ��������� /cancel.")
        return
    settings_service = _settings_service(msg.bot)
    await settings_service.update_owner_pay_snapshot(**payload)
    await state.clear()
    await msg.answer("��������� ���������.")


@router.message(StateFilter(OwnerPayEditFSM.value), F.text == "/cancel")
async def finance_owner_edit_cancel(msg: Message, state: FSMContext) -> None:
    await state.clear()
    await msg.answer("��������� ���������� ��������.")
@router.callback_query(
    F.data == "adm:r",
    StaffRoleFilter({StaffRole.GLOBAL_ADMIN, StaffRole.CITY_ADMIN}),
)
async def cb_reports(cq: CallbackQuery, staff: StaffUser) -> None:
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    kb = InlineKeyboardBuilder()
    kb.button(text="������ CSV/XLSX", callback_data="adm:export:orders")
    kb.button(text="�������� CSV/XLSX", callback_data="adm:export:commissions")
    kb.button(text="��������� CSV/XLSX", callback_data="adm:export:ref")
    kb.button(text="?? � ����", callback_data="adm:menu")
    kb.adjust(2, 2)
    await cq.message.edit_text("��������:", reply_markup=kb.as_markup())
    await cq.answer()


@router.callback_query(
    F.data == "adm:export:orders",
    StaffRoleFilter({StaffRole.GLOBAL_ADMIN, StaffRole.CITY_ADMIN}),
)
async def cb_export_orders(cq: CallbackQuery, staff: StaffUser) -> None:
    date_to = datetime.now(LOCAL_TZ)
    date_from = date_to - timedelta(days=7)
    bundle = await export_service.export_orders(
        date_from=date_from,
        date_to=date_to,
        city_ids=_city_filter(staff),
    )
    _send_export_documents(cq.message, bundle, "Orders (last 7 days)")
    await cq.answer("������")


@router.callback_query(
    F.data == "adm:export:commissions",
    StaffRoleFilter({StaffRole.GLOBAL_ADMIN, StaffRole.CITY_ADMIN}),
)
async def cb_export_commissions(cq: CallbackQuery, staff: StaffUser) -> None:
    date_to = datetime.now(LOCAL_TZ)
    date_from = date_to - timedelta(days=7)
    bundle = await export_service.export_commissions(
        date_from=date_from,
        date_to=date_to,
        city_ids=_city_filter(staff),
    )
    _send_export_documents(cq.message, bundle, "Commissions (last 7 days)")
    await cq.answer("������")


@router.callback_query(
    F.data == "adm:export:ref",
    StaffRoleFilter({StaffRole.GLOBAL_ADMIN, StaffRole.CITY_ADMIN}),
)
async def cb_export_ref(cq: CallbackQuery, staff: StaffUser) -> None:
    date_to = datetime.now(LOCAL_TZ)
    date_from = date_to - timedelta(days=7)
    bundle = await export_service.export_referral_rewards(
        date_from=date_from,
        date_to=date_to,
        city_ids=_city_filter(staff),
    )
    _send_export_documents(cq.message, bundle, "Referral rewards (last 7 days)")
    await cq.answer("������")
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
        await message.edit_text("������ �� �������. ������� ������ ������ ��� /cancel.")
        return
    per_page = 10
    total_pages = max(1, (len(cities) + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))
    start = (page - 1) * per_page
    chunk = cities[start : start + per_page]
    keyboard = new_order_city_keyboard([(c.id, c.name) for c in chunk], page=page, total_pages=total_pages)
    await message.edit_text("�������� ����� ������:", reply_markup=keyboard)
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
    await cq.message.edit_text("�������� ������ ��������.")
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
    await cq.message.edit_text("������� �������� ������ (�������). ��� ������ /cancel.")
    await cq.answer()


@router.message(StateFilter(NewOrderFSM.city))
async def new_order_city_input(msg: Message, state: FSMContext) -> None:
    query = msg.text.strip()
    if len(query) < 2:
        await msg.answer("������� ���� �� ��� �������.")
        return
    await _render_city_step(msg, state, page=1, query=query)


@router.callback_query(F.data.startswith("adm:new:city:"), StateFilter(NewOrderFSM.city))
async def cb_new_order_city_pick(cq: CallbackQuery, state: FSMContext) -> None:
    city_id = int(cq.data.split(":")[2])
    orders_service = _orders_service(cq.message.bot)
    city = await orders_service.get_city(city_id)
    if not city:
        await cq.answer("����� �� ������", show_alert=True)
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
    await message.edit_text("�������� ����� (��� ��� ������):", reply_markup=keyboard)
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
    await state.update_data(district_id=None, district_name="�")
    await state.set_state(NewOrderFSM.street_mode)
    await cq.message.edit_text(
        "�������� ������ �������� �����:",
        reply_markup=new_order_street_mode_keyboard(),
    )
    await cq.answer()


@router.callback_query(F.data.startswith("adm:new:district:"), StateFilter(NewOrderFSM.district))
async def cb_new_order_district_pick(cq: CallbackQuery, state: FSMContext) -> None:
    district_id = int(cq.data.split(":")[2])
    orders_service = _orders_service(cq.message.bot)
    district = await orders_service.get_district(district_id)
    if not district:
        await cq.answer("����� �� ������", show_alert=True)
        return
    await state.update_data(district_id=district.id, district_name=district.name)
    await state.set_state(NewOrderFSM.street_mode)
    await cq.message.edit_text(
        "�������� ������ �������� �����:",
        reply_markup=new_order_street_mode_keyboard(),
    )
    await cq.answer()
@router.callback_query(F.data == "adm:new:street:search", StateFilter(NewOrderFSM.street_mode))
async def cb_new_order_street_search(cq: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(NewOrderFSM.street_search)
    await cq.message.edit_text("������� ����� �������� �����.")
    await cq.answer()


@router.callback_query(F.data == "adm:new:street:manual", StateFilter(NewOrderFSM.street_mode))
async def cb_new_order_street_manual(cq: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(NewOrderFSM.street_manual)
    await cq.message.edit_text(
        "������� �������� ����� ������� (2-50 ��������).",
        reply_markup=new_order_street_manual_keyboard(),
    )
    await cq.answer()


@router.callback_query(F.data == "adm:new:street:none", StateFilter(NewOrderFSM.street_mode))
async def cb_new_order_street_none(cq: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(street_id=None, street_name="�", street_manual=None)
    await state.set_state(NewOrderFSM.house)
    await cq.message.edit_text("������� ����� ���� (1-10 ��������).")
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
        await msg.answer("�������� ����� ������ ���� �� 2 �� 50 ��������.")
        return
    await state.update_data(street_id=None, street_name=value, street_manual=value)
    await state.set_state(NewOrderFSM.house)
    await msg.answer("������� ����� ���� (1-10 ��������).")


@router.message(StateFilter(NewOrderFSM.street_search))
async def new_order_street_search_input(msg: Message, state: FSMContext) -> None:
    query = msg.text.strip()
    if len(query) < 2:
        await msg.answer("������� ���� �� ��� �������.")
        return
    data = await state.get_data()
    city_id = data.get("city_id")
    orders_service = _orders_service(msg.bot)
    streets = await orders_service.search_streets(city_id, query)
    if not streets:
        await msg.answer("������ �� �������. ���������� ������ ������ ��� ������� �������.")
        return
    buttons = [
        (s.id, s.name if s.score is None else f"{s.name} ({int(s.score)}%)")
        for s in streets
    ]
    await msg.answer(
        "�������� �����:",
        reply_markup=new_order_street_keyboard(buttons),
    )
    await state.update_data(street_search_results=buttons)


@router.callback_query(F.data.startswith("adm:new:street:"), StateFilter(NewOrderFSM.street_mode))
async def cb_new_order_street_pick(cq: CallbackQuery, state: FSMContext) -> None:
    tail = cq.data.split(":")[2]
    if tail == "search_again":
        await state.set_state(NewOrderFSM.street_search)
        await cq.message.edit_text("������� ����� �������� ����� ��� ���.")
        await cq.answer()
        return
    if tail == "manual_back":
        await state.set_state(NewOrderFSM.street_mode)
        await cq.message.edit_text(
            "�������� ������ �������� �����:",
            reply_markup=new_order_street_mode_keyboard(),
        )
        await cq.answer()
        return
    street_id = int(tail)
    orders_service = _orders_service(cq.message.bot)
    street = await orders_service.get_street(street_id)
    if not street:
        await cq.answer("����� �� �������", show_alert=True)
        return
    await state.update_data(street_id=street.id, street_name=street.name, street_manual=None)
    await state.set_state(NewOrderFSM.house)
    await cq.message.edit_text("������� ����� ���� (1-10 ��������).")
    await cq.answer()


@router.message(StateFilter(NewOrderFSM.house))
async def new_order_house(msg: Message, state: FSMContext) -> None:
    value = msg.text.strip()
    if not (1 <= len(value) <= 10):
        await msg.answer("����� ���� ������ ���� �� 1 �� 10 ��������.")
        return
    await state.update_data(house=value)
    await state.set_state(NewOrderFSM.apartment)
    await msg.answer("������� �������� (��� '-' ��� ��������).")


@router.message(StateFilter(NewOrderFSM.apartment))
async def new_order_apartment(msg: Message, state: FSMContext) -> None:
    value = msg.text.strip()
    if value == "-":
        value = ""
    if len(value) > 10:
        await msg.answer("������� ������� ��������. �� 10 ��������.")
        return
    await state.update_data(apartment=value or None)
    await state.set_state(NewOrderFSM.address_comment)
    await msg.answer("�������� ����������� � ������ (��� '-' ��� ��������).")


@router.message(StateFilter(NewOrderFSM.address_comment))
async def new_order_address_comment(msg: Message, state: FSMContext) -> None:
    value = msg.text.strip()
    if value == "-":
        value = ""
    await state.update_data(address_comment=value or None)
    await state.set_state(NewOrderFSM.client_name)
    await msg.answer("������� ��� ������� (2-30 ��������, ���������).")


@router.message(StateFilter(NewOrderFSM.client_name))
async def new_order_client_name(msg: Message, state: FSMContext) -> None:
    value = msg.text.strip()
    if not _validate_name(value):
        await msg.answer("��� ������ ���� 2-30 ��������, ���������, ������ ��� �����.")
        return
    await state.update_data(client_name=value)
    await state.set_state(NewOrderFSM.client_phone)
    await msg.answer("������� ������� ������� (+7XXXXXXXXXX ��� 8XXXXXXXXXX).")


@router.message(StateFilter(NewOrderFSM.client_phone))
async def new_order_client_phone(msg: Message, state: FSMContext) -> None:
    raw = _normalize_phone(msg.text)
    if not _validate_phone(raw):
        await msg.answer("�������� ������ ��������. ������: +71234567890 ��� 81234567890.")
        return
    await state.update_data(client_phone=raw)
    await state.set_state(NewOrderFSM.category)
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    kb = InlineKeyboardBuilder()
    for code, label in CATEGORY_CHOICES:
        kb.button(text=label, callback_data=f"adm:new:cat:{code}")
    kb.adjust(2)
    await msg.answer("�������� ��������� ������:", reply_markup=kb.as_markup())


@router.callback_query(F.data.startswith("adm:new:cat:"), StateFilter(NewOrderFSM.category))
async def cb_new_order_category(cq: CallbackQuery, state: FSMContext) -> None:
    code = cq.data.split(":")[2]
    await state.update_data(category=code, category_label=CATEGORY_LABELS.get(code, code))
    await state.set_state(NewOrderFSM.description)
    await cq.message.edit_text("������� �������� (10-500 ��������).")
    await cq.answer()


@router.message(StateFilter(NewOrderFSM.description))
async def new_order_description(msg: Message, state: FSMContext) -> None:
    text = msg.text.strip()
    if not (10 <= len(text) <= 500):
        await msg.answer("�������� ������ ���� �� 10 �� 500 ��������.")
        return
    await state.update_data(description=text)
    await state.set_state(NewOrderFSM.attachments)
    await msg.answer(
        "�������� �������� (����/��������) ��� ������� '����������'.",
        reply_markup=new_order_attachments_keyboard(False),
    )


@router.callback_query(F.data == "adm:new:att:add", StateFilter(NewOrderFSM.attachments))
async def cb_new_order_att_add(cq: CallbackQuery) -> None:
    await cq.answer("��������� ���� ��� �������� ����������")


@router.callback_query(F.data == "adm:new:att:clear", StateFilter(NewOrderFSM.attachments))
async def cb_new_order_att_clear(cq: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    data["attachments"] = []
    await state.update_data(**data)
    await cq.message.edit_text(
        "�������� �������. �������� ����� ��� ����������.",
        reply_markup=new_order_attachments_keyboard(False),
    )
    await cq.answer()


@router.message(StateFilter(NewOrderFSM.attachments), F.photo)
async def new_order_attach_photo(msg: Message, state: FSMContext) -> None:
    attachments = _attachments_from_state(await state.get_data())
    if len(attachments) >= ATTACHMENTS_LIMIT:
        await msg.answer("�������� ���� ��������. �������� ������ ��� ����������.")
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
        f"��������� ����. ����� ��������: {len(attachments)}.",
        reply_markup=new_order_attachments_keyboard(True),
    )


@router.message(StateFilter(NewOrderFSM.attachments), F.document)
async def new_order_attach_doc(msg: Message, state: FSMContext) -> None:
    attachments = _attachments_from_state(await state.get_data())
    if len(attachments) >= ATTACHMENTS_LIMIT:
        await msg.answer("�������� ���� ��������. �������� ������ ��� ����������.")
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
        f"�������� ��������. ����� ��������: {len(attachments)}.",
        reply_markup=new_order_attachments_keyboard(True),
    )
@router.callback_query(F.data == "adm:new:att:done", StateFilter(NewOrderFSM.attachments))
async def cb_new_order_att_done(cq: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(NewOrderFSM.order_type)
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    kb = InlineKeyboardBuilder()
    kb.button(text="�������", callback_data="adm:new:type:NORMAL")
    kb.button(text="��������", callback_data="adm:new:type:GUARANTEE")
    kb.adjust(2)
    await cq.message.edit_text("�������� ��� ������:", reply_markup=kb.as_markup())
    await cq.answer()


@router.callback_query(F.data.startswith("adm:new:type:"), StateFilter(NewOrderFSM.order_type))
async def cb_new_order_type(cq: CallbackQuery, state: FSMContext) -> None:
    code = cq.data.split(":")[2]
    await state.update_data(
        order_type=code,
        company_payment=2500 if code == "GUARANTEE" else 0,
    )
    await state.set_state(NewOrderFSM.slot)
    now_local = datetime.now(LOCAL_TZ)
    options = _slot_options(now_local)
    keyboard = new_order_slot_keyboard([(key, label) for key, label, *_ in options])
    await state.update_data(slot_options=options)
    await cq.message.edit_text("�������� ��������� ����:", reply_markup=keyboard)
    await cq.answer()


@router.callback_query(F.data.startswith("adm:new:slot:"), StateFilter(NewOrderFSM.slot))
async def cb_new_order_slot(cq: CallbackQuery, state: FSMContext) -> None:
    key = cq.data.split(":")[2]
    data = await state.get_data()
    options = data.get("slot_options", [])
    slot_map = {item[0]: item for item in options}
    if key not in slot_map:
        await cq.answer("���� ����������", show_alert=True)
        return
    _, label, scheduled_date, start, end = slot_map[key]
    if key == "asap" and datetime.now(LOCAL_TZ).time() >= LATE_ASAP_THRESHOLD:
        label = "ASAP (������� �� ������ 10-13)"
        scheduled_date = datetime.now(LOCAL_TZ).date() + timedelta(days=1)
        start = time(10, 0)
        end = time(13, 0)
    await state.update_data(
        slot_label=key,
        slot_label_display=label,
        scheduled_date=scheduled_date,
        time_slot_start=start,
        time_slot_end=end,
    )
    summary = new_order_summary(await state.get_data())
    await state.set_state(NewOrderFSM.confirm)
    await cq.message.edit_text(
        summary,
        reply_markup=new_order_confirm_keyboard(),
        disable_web_page_preview=True,
    )
    await cq.answer()


@router.callback_query(F.data == "adm:new:confirm", StateFilter(NewOrderFSM.confirm))
async def cb_new_order_confirm(cq: CallbackQuery, staff: StaffUser, state: FSMContext) -> None:
    data = await state.get_data()
    try:
        new_order = _build_new_order_data(data, staff)
    except KeyError:
        await state.clear()
        await cq.answer("�� ������� ������, ������� ������", show_alert=True)
        return
    orders_service = _orders_service(cq.message.bot)
    order_id = await orders_service.create_order(new_order)
    await state.clear()
    await cq.answer("�������")
    await _render_order_card(cq.message, order_id, staff)





@router.callback_query(
    F.data == "adm:s",
    StaffRoleFilter({StaffRole.GLOBAL_ADMIN}),
)
async def cb_settings_menu(cq: CallbackQuery, staff: StaffUser) -> None:
    await cq.message.edit_text(
        "<b>��������� �������</b>\n�������� ������ ��� ��������������.",
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
        await cq.answer("������ ����������", show_alert=True)
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
        await cq.answer("������������ ������", show_alert=True)
        return
    _, _, _, group_key, field_key = parts
    try:
        field = _get_setting_field(field_key)
    except KeyError:
        await cq.answer("��������� �� �������", show_alert=True)
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
    await msg.answer("��������� ��������.")


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
            "��������� ��������. �������� ������ �������� ������ ����� ����."
        )
        return

    try:
        field = _get_setting_field(field_key)
    except KeyError:
        await state.clear()
        await msg.answer("��������� �� �������.")
        return

    if not msg.text:
        await msg.answer("��������� ��������� ��������.")
        return

    try:
        value, value_type = _parse_setting_input(field, msg.text)
    except ValueError as exc:
        await msg.answer(str(exc))
        return

    service = _settings_service(msg.bot)
    await service.set_value(field.key, value, value_type=value_type)
    await state.clear()
    await msg.answer("��������� ���������.")

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
    await cq.answer("�������")
