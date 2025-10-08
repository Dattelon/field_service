# field_service/bots/admin_bot/handlers/settings.py
"""Обработчики настроек системы (SettingsEditFSM)."""
from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import time
from typing import Any, Optional

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from field_service.config import settings as env_settings

from ...core.dto import StaffRole, StaffUser
from ...core.filters import StaffRoleFilter
from ...ui.keyboards import settings_menu_keyboard, settings_group_keyboard
from ...core.states import SettingsEditFSM
from ..common.helpers import _settings_service, EMPTY_PLACEHOLDER


router = Router(name="admin_settings")


# ============================================
# ОПРЕДЕЛЕНИЯ НАСТРОЕК
# ============================================

@dataclass(frozen=True)
class SettingFieldDef:
    """Определение одного поля настройки."""
    key: str
    label: str
    schema: str
    value_type: str = "STR"
    choices: tuple[tuple[str, str], ...] | None = None
    help_text: str = ""
    default: object | None = None


@dataclass(frozen=True)
class SettingGroupDef:
    """Определение группы настроек."""
    key: str
    title: str
    fields: tuple[SettingFieldDef, ...]
    description: str = ""


# Группы настроек
SETTING_GROUPS: dict[str, SettingGroupDef] = {
    "workday": SettingGroupDef(
        key="workday",
        title="Рабочий день",
        description="Рабочий интервал сервиса. В это время назначаются визиты мастеров.",
        fields=(
            SettingFieldDef(
                key="working_hours_start",
                label="Начало рабочего дня",
                schema="time",
                value_type="TIME",
                default=env_settings.working_hours_start,
                help_text="Формат ЧЧ:ММ, по умолчанию 10:00.",
            ),
            SettingFieldDef(
                key="working_hours_end",
                label="Конец рабочего дня",
                schema="time",
                value_type="TIME",
                default=env_settings.working_hours_end,
                help_text="Формат ЧЧ:ММ, по умолчанию 20:00.",
            ),
        ),
    ),
    "distribution": SettingGroupDef(
        key="distribution",
        title="Распределение",
        description="Настройки автораспределения заявок (частота, SLA, раунды).",
        fields=(
            SettingFieldDef(
                key="distribution_tick_seconds",
                label="Шаг цикла (сек.)",
                schema="int",
                value_type="INT",
                default=30,
            ),
            SettingFieldDef(
                key="distribution_sla_seconds",
                label="SLA ответа мастера (сек.)",
                schema="int",
                value_type="INT",
                default=env_settings.distribution_sla_seconds,
            ),
            SettingFieldDef(
                key="distribution_rounds",
                label="Количество раундов",
                schema="int",
                value_type="INT",
                default=env_settings.distribution_rounds,
            ),
            SettingFieldDef(
                key="escalate_to_admin_after_min",
                label="Эскалация к админу через (мин.)",
                schema="int_non_negative",
                value_type="INT",
                default=10,
            ),
            SettingFieldDef(
                key="distribution_log_topn",
                label="Логировать topN кандидатов",
                schema="int",
                value_type="INT",
                default=10,
            ),
        ),
    ),
    "limits": SettingGroupDef(
        key="limits",
        title="Лимиты",
        description="Ограничения сервиса для мастеров и процессов.",
        fields=(
            SettingFieldDef(
                key="max_active_orders",
                label="Макс. активных заказов на мастера",
                schema="int",
                value_type="INT",
                default=1,
            ),
        ),
    ),
    "support": SettingGroupDef(
        key="support",
        title="Поддержка",
        description="Контакты поддержки и материалы.",
        fields=(
            SettingFieldDef(
                key="support_contact",
                label="Контакт поддержки",
                schema="string",
                value_type="STR",
                help_text="Например, @username, если доступно.",
            ),
            SettingFieldDef(
                key="support_faq_url",
                label="Ссылка на FAQ",
                schema="string_optional",
                value_type="STR",
                help_text="Укажите URL или '-' чтобы очистить.",
            ),
        ),
    ),
    "geo": SettingGroupDef(
        key="geo",
        title="Гео",
        description="Режим и лимиты геокодера.",
        fields=(
            SettingFieldDef(
                key="geo_mode",
                label="Режим геокодера",
                schema="choice",
                value_type="STR",
                choices=(
                    ("local_centroids", "Локальные центроиды"),
                    ("yandex", "Яндекс"),
                ),
                default="local_centroids",
                help_text="1 — локально, 2 — через API.",
            ),
            SettingFieldDef(
                key="yandex_geocoder_key",
                label="API‑ключ Яндекс",
                schema="string_optional",
                value_type="STR",
                help_text="Оставьте '-' чтобы очистить.",
            ),
            SettingFieldDef(
                key="yandex_throttle_rps",
                label="RPS ограничение",
                schema="int_non_negative",
                value_type="INT",
                default=1,
            ),
            SettingFieldDef(
                key="yandex_daily_limit",
                label="Суточный лимит запросов",
                schema="int_non_negative",
                value_type="INT",
                default=1000,
            ),
        ),
    ),
    "channels": SettingGroupDef(
        key="channels",
        title="Каналы",
        description="ID каналов Telegram для уведомлений и отчётов.",
        fields=(
            SettingFieldDef(
                key="alerts_channel_id",
                label="Канал алертов (ID)",
                schema="int_optional",
                value_type="STR",
                help_text="ID или '-' чтобы очистить.",
            ),
            SettingFieldDef(
                key="logs_channel_id",
                label="Канал логов (ID)",
                schema="int_optional",
                value_type="STR",
                help_text="ID или '-' чтобы очистить.",
            ),
            SettingFieldDef(
                key="reports_channel_id",
                label="Канал отчётов (ID)",
                schema="int_optional",
                value_type="STR",
                help_text="ID или '-' чтобы очистить.",
            ),
        ),
    ),
}

# Индексы для быстрого доступа
SETTING_FIELD_BY_KEY: dict[str, SettingFieldDef] = {
    field.key: field
    for group in SETTING_GROUPS.values()
    for field in group.fields
}

SETTING_FIELD_GROUP: dict[str, str] = {
    field.key: group.key
    for group in SETTING_GROUPS.values()
    for field in group.fields
}

# Хелпы по умолчанию для схем
SCHEMA_DEFAULT_HELP = {
    "time": "Формат ЧЧ:ММ, по умолчанию 10:00.",
    "int": "Введите положительное целое число.",
    "int_non_negative": "Введите целое число 0 или больше.",
    "string": "Введите текстовое значение.",
    "string_optional": "Введите текст или '-' чтобы очистить значение.",
    "int_optional": "Введите число или '-' чтобы очистить значение.",
    "choice": "Выберите один из предложенных вариантов.",
}


# ============================================
# ХЕЛПЕРЫ
# ============================================

def _get_setting_group(group_key: str) -> SettingGroupDef:
    """Получить определение группы по ключу."""
    group = SETTING_GROUPS.get(group_key)
    if group is None:
        raise KeyError(f"Unknown settings group: {group_key}")
    return group


def _get_setting_field(field_key: str) -> SettingFieldDef:
    """Получить определение поля по ключу."""
    field = SETTING_FIELD_BY_KEY.get(field_key)
    if field is None:
        raise KeyError(f"Unknown setting field: {field_key}")
    return field


def _format_setting_value(field: SettingFieldDef, raw_value: Optional[str]) -> tuple[str, bool]:
    """
    Форматировать значение настройки для отображения.
    
    Returns:
        (formatted_value, from_default)
    """
    value = raw_value
    from_default = False
    if value in (None, ""):
        value = field.default
        from_default = raw_value in (None, "") and value not in (None, "")
    if value in (None, ""):
        return EMPTY_PLACEHOLDER, False
    if field.schema == "choice" and field.choices:
        text_value = str(value)
        for code, label in field.choices:
            if text_value == code:
                return f"{label} ({code})", from_default
    return str(value), from_default


def _choice_help(field: SettingFieldDef) -> str:
    """Сгенерировать текст помощи для choice-поля."""
    if not field.choices:
        return ""
    lines = []
    for idx, (code, label) in enumerate(field.choices, 1):
        lines.append(f"{idx}. {label} ({code})")
    return "\n".join(lines)


def _build_setting_prompt(field: SettingFieldDef, current_display: str) -> str:
    """Построить prompt для редактирования настройки."""
    lines = [f"<b>{field.label}</b>"]
    if current_display and current_display != EMPTY_PLACEHOLDER:
        lines.append(f"Текущее: <code>{html.escape(current_display, quote=False)}</code>")
    base_help = SCHEMA_DEFAULT_HELP.get(field.schema, "Введите новое значение.")
    if field.schema == "choice":
        options = _choice_help(field)
        if options:
            lines.append(base_help)
            lines.append(options)
        else:
            lines.append(base_help)
    else:
        lines.append(field.help_text or base_help)
    lines.append("\nОтправьте /cancel для отмены.")
    return "\n".join(lines)


def _parse_setting_input(field: SettingFieldDef, user_input: str) -> tuple[str, str]:
    """
    Парсинг и валидация ввода пользователя.
    
    Returns:
        (parsed_value, value_type)
    
    Raises:
        ValueError: если ввод невалидный
    """
    text = (user_input or "").strip()
    
    if field.schema in {"string_optional", "int_optional"} and text in {"", "-"}:
        return "", field.value_type
    
    if field.schema == "time":
        if not re.fullmatch(r"^\d{1,2}:\d{2}$", text):
            raise ValueError("Неверный формат. Ожидается ЧЧ:ММ.")
        hh, mm = map(int, text.split(":"))
        if not (0 <= hh < 24 and 0 <= mm < 60):
            raise ValueError("Часы: 0-23, минуты: 0-59.")
        return text, field.value_type
    
    if field.schema == "int":
        try:
            value = int(text)
        except ValueError:
            raise ValueError("Ожидается целое число.")
        if value <= 0:
            raise ValueError("Число должно быть больше 0.")
        return str(value), field.value_type
    
    if field.schema == "int_non_negative":
        try:
            value = int(text)
        except ValueError:
            raise ValueError("Ожидается целое число.")
        if value < 0:
            raise ValueError("Число должно быть 0 или больше.")
        return str(value), field.value_type
    
    if field.schema == "int_optional":
        try:
            value = int(text)
        except ValueError:
            raise ValueError("Ожидается число или '-' для очистки.")
        return str(value), field.value_type
    
    if field.schema == "choice":
        normalized = text.lower()
        if field.choices:
            for idx, (code, label) in enumerate(field.choices, 1):
                if normalized in {code.lower(), label.lower(), str(idx)}:
                    return code, field.value_type
        raise ValueError("Выберите один из предложенных вариантов.")
    
    if field.schema == "string_optional":
        return text, field.value_type
    
    if field.schema == "string":
        if not text:
            raise ValueError("Поле не может быть пустым.")
        return text, field.value_type
    
    raise ValueError("Неизвестная схема валидации.")


async def _build_settings_view(bot, group_key: str) -> tuple[str, Any]:
    """Построить представление группы настроек."""
    group = _get_setting_group(group_key)
    service = _settings_service(bot)
    raw_map = await service.get_values([field.key for field in group.fields])
    
    title = group.title
    desc = group.description
    
    lines: list[str] = [f"<b>{title}</b>"]
    if desc:
        lines.append(desc)
    
    for field in group.fields:
        raw_value = raw_map.get(field.key, (None, None))[0]
        display, from_default = _format_setting_value(field, raw_value)
        label = field.label
        
        if display == EMPTY_PLACEHOLDER:
            value_line = f"• {label}: {EMPTY_PLACEHOLDER}"
        else:
            value_line = f"• {label}: <code>{html.escape(display, quote=False)}</code>"
        
        if from_default and field.default not in (None, ""):
            value_line += " <i>(по умолчанию)</i>"
        
        lines.append(value_line)
    
    lines.append("\nВыберите поле ниже, чтобы отредактировать значение.")
    
    keyboard = settings_group_keyboard(
        group_key,
        [(field.key, field.label) for field in group.fields],
    )
    return "\n".join(lines), keyboard


# ============================================
# ОБРАБОТЧИКИ
# ============================================

@router.callback_query(
    F.data == "adm:s",
    StaffRoleFilter({StaffRole.GLOBAL_ADMIN}),
)
async def cb_settings_menu(cq: CallbackQuery, staff: StaffUser) -> None:
    """Показать главное меню настроек."""
    await cq.message.edit_text(
        "<b>⚙️ Настройки</b>\n\nВыберите группу настроек для редактирования.",
        reply_markup=settings_menu_keyboard(),
    )
    await cq.answer()


@router.callback_query(
    F.data.startswith("adm:s:group:"),
    StaffRoleFilter({StaffRole.GLOBAL_ADMIN}),
)
async def cb_settings_group(cq: CallbackQuery, staff: StaffUser) -> None:
    """Показать группу настроек."""
    group_key = cq.data.split(":")[3]
    try:
        view_text, keyboard = await _build_settings_view(cq.message.bot, group_key)
    except KeyError:
        await cq.answer("Группа не найдена", show_alert=True)
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
    """Начать редактирование настройки."""
    parts = cq.data.split(":")
    if len(parts) != 5:
        await cq.answer("Неверный формат", show_alert=True)
        return
    _, _, _, group_key, field_key = parts
    
    try:
        field = _get_setting_field(field_key)
    except KeyError:
        await cq.answer("Поле не найдено", show_alert=True)
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
    """Отменить редактирование настройки."""
    await state.clear()
    await msg.answer("Редактирование отменено.")


@router.message(
    StateFilter(SettingsEditFSM.awaiting_value),
    StaffRoleFilter({StaffRole.GLOBAL_ADMIN}),
)
async def settings_edit_value(
    msg: Message, staff: StaffUser, state: FSMContext
) -> None:
    """Обработать ввод нового значения настройки."""
    data = await state.get_data()
    field_key = data.get("edit_key")
    group_key = data.get("group_key")
    source_chat_id = data.get("source_chat_id")
    source_message_id = data.get("source_message_id")

    if not field_key or not group_key or source_chat_id is None or source_message_id is None:
        await state.clear()
        await msg.answer("Ошибка: данные сессии потеряны.")
        return

    try:
        field = _get_setting_field(field_key)
    except KeyError:
        await state.clear()
        await msg.answer("Ошибка: поле не найдено.")
        return

    if not msg.text:
        await msg.answer("Пожалуйста, отправьте текстовое значение.")
        return

    try:
        value, value_type = _parse_setting_input(field, msg.text)
    except ValueError as exc:
        await msg.answer(str(exc))
        return

    service = _settings_service(msg.bot)
    await service.set_value(field.key, value, value_type=value_type)
    await state.clear()
    await msg.answer("✅ Значение сохранено.")

    # Обновить исходное сообщение с группой настроек
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


__all__ = [
    "router",
    "SETTING_GROUPS",
    "SettingFieldDef",
    "SettingGroupDef",
]
