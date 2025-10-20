# field_service/bots/admin_bot/handlers/reports.py
"""📊 Модуль экспорта отчётов (ReportsExportFSM).

Обрабатывает генерацию и экспорт отчётов по заказам, комиссиям и реферальным
начислениям в форматах CSV и XLSX.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Optional

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message

from field_service.config import settings as env_settings
from field_service.services import export_service, time_service

from ...core.dto import StaffRole, StaffUser
from ...core.filters import StaffRoleFilter
from ...ui.keyboards import reports_menu_keyboard, reports_periods_keyboard
from ...core.states import ReportsExportFSM
from ...core.access import visible_city_ids_for
from ..common.helpers import _settings_service


router = Router(name="admin_reports")


# Определения отчётов: (русское название, функция экспорта, префикс для caption)
REPORT_DEFINITIONS: dict[str, tuple[str, Any, str]] = {
    "orders": ("заказы", export_service.export_orders, "Заказы"),
    "commissions": ("комиссии", export_service.export_commissions, "Комиссии"),
    "ref_rewards": ("реферальные начисления", export_service.export_referral_rewards, "Реферальные начисления"),
}

# Поддерживаемые форматы дат: ISO (YYYY-MM-DD) и русский (DD.MM.YYYY)
DATE_INPUT_FORMATS = ("%Y-%m-%d", "%d.%m.%Y")


# ============================================
# 🛠️ Вспомогательные функции
# ============================================

def _parse_period_input(text: str) -> Optional[tuple[date, date]]:
    """📅 Парсинг периода из текстового ввода.
    
    Ожидаемые форматы:
    - "YYYY-MM-DD YYYY-MM-DD" (ISO)
    - "DD.MM.YYYY DD.MM.YYYY" (русский)
    
    Returns:
        (start_date, end_date) или None если формат неверен
    """
    if not text:
        return None
    
    parts = text.strip().split()
    if len(parts) != 2:
        return None
    
    start_str, end_str = parts
    
    for fmt in DATE_INPUT_FORMATS:
        try:
            start_dt = datetime.strptime(start_str, fmt).date()
            end_dt = datetime.strptime(end_str, fmt).date()
            if start_dt <= end_dt:
                return start_dt, end_dt
        except ValueError:
            continue
    
    return None


def _compute_quick_period(key: str, *, tz: str) -> Optional[tuple[date, date]]:
    """⏱️ Вычисление быстрого периода.
    
    Args:
        key: Ключ периода (today, yesterday, last7, this_month, prev_month)
        tz: Часовой пояс
    
    Returns:
        (start_date, end_date) или None
    """
    now = time_service.now_in_city(tz)
    today = now.date()
    
    if key == "today":
        return today, today
    
    if key == "yesterday":
        y = today - timedelta(days=1)
        return y, y
    
    if key == "last7":
        return today - timedelta(days=6), today
    
    if key == "this_month":
        start = today.replace(day=1)
        return start, today
    
    if key == "prev_month":
        first_this = today.replace(day=1)
        prev_last = first_this - timedelta(days=1)
        start = prev_last.replace(day=1)
        end = prev_last
        return start, end
    
    return None


def _format_period_label(start_dt: date, end_dt: date) -> str:
    """📝 Форматирование периода для отображения.
    
    Args:
        start_dt: Дата начала
        end_dt: Дата окончания
    
    Returns:
        Строка вида "01.01.2025 - 31.01.2025" или "01.01.2025" для одного дня
    """
    if start_dt == end_dt:
        return start_dt.strftime("%d.%m.%Y")
    return f"{start_dt.strftime('%d.%m.%Y')} - {end_dt.strftime('%d.%m.%Y')}"


async def _send_export_documents(
    bot,
    bundle: export_service.ExportBundle,
    caption: str,
    *,
    chat_id: int,
) -> None:
    """📤 Отправка файлов отчёта (CSV и XLSX).
    
    Args:
        bot: Экземпляр бота
        bundle: ExportBundle с данными CSV и XLSX
        caption: Подпись к файлам
        chat_id: ID чата для отправки
    """
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


# ============================================
# 🎯 Обработчики callback-кнопок и сообщений
# ============================================

@router.callback_query(
    F.data == "adm:r",
    StaffRoleFilter({StaffRole.GLOBAL_ADMIN, StaffRole.CITY_ADMIN}),
)
async def cb_reports(cq: CallbackQuery, staff: StaffUser, state: FSMContext) -> None:
    """<b>📊 Главное меню отчётов</b>

    Выберите тип отчёта для экспорта."""
    await state.clear()
    await cq.message.edit_text(
        "<b>📊 Отчёты</b>\n\nВыберите тип отчёта:",
        reply_markup=reports_menu_keyboard()
    )
    await cq.answer()


async def _prompt_report_period(cq: CallbackQuery, state: FSMContext, report_kind: str) -> None:
    """🕒 Запрос периода для отчёта.
    
    Args:
        cq: CallbackQuery
        state: FSMContext
        report_kind: Тип отчёта (orders, commissions, ref_rewards)
    """
    await state.clear()
    label, _, _ = REPORT_DEFINITIONS[report_kind]
    await state.set_state(ReportsExportFSM.awaiting_period)
    await state.update_data(report_kind=report_kind)
    await cq.message.answer(
        f"📅 <b>Выберите период</b>\n\n"
        f"Отчёт: <i>{label}</i>\n\n"
        f"Используйте кнопки или введите период вручную:",
        reply_markup=reports_periods_keyboard(),
    )
    await cq.answer()


@router.callback_query(
    F.data == "adm:r:o",
    StaffRoleFilter({StaffRole.GLOBAL_ADMIN, StaffRole.CITY_ADMIN}),
)
async def cb_reports_orders(cq: CallbackQuery, state: FSMContext) -> None:
    """📋 Экспорт отчёта по заказам.
    
    Запускает FSM для выбора периода и генерации CSV/XLSX с данными о заказах."""
    await _prompt_report_period(cq, state, "orders")


@router.callback_query(
    F.data == "adm:r:c",
    StaffRoleFilter({StaffRole.GLOBAL_ADMIN, StaffRole.CITY_ADMIN}),
)
async def cb_reports_commissions(cq: CallbackQuery, state: FSMContext) -> None:
    """💳 Экспорт отчёта по комиссиям.
    
    Запускает FSM для выбора периода и генерации CSV/XLSX с данными о комиссиях."""
    await _prompt_report_period(cq, state, "commissions")


@router.callback_query(
    F.data == "adm:r:rr",
    StaffRoleFilter({StaffRole.GLOBAL_ADMIN, StaffRole.CITY_ADMIN}),
)
async def cb_reports_referrals(cq: CallbackQuery, state: FSMContext) -> None:
    """🤝 Экспорт отчёта по реферальным начислениям.
    
    Запускает FSM для выбора периода и генерации CSV/XLSX с данными о реферальных выплатах."""
    await _prompt_report_period(cq, state, "ref_rewards")


@router.message(StateFilter(ReportsExportFSM.awaiting_period), F.text == "/cancel")
async def reports_cancel(msg: Message, state: FSMContext) -> None:
    """❌ Отмена экспорта отчёта.
    
    Пользователь может отменить выбор периода командой /cancel."""
    await state.clear()
    await msg.answer("❌ Экспорт отменён.")


@router.message(StateFilter(ReportsExportFSM.awaiting_period))
async def reports_period_submit(
    msg: Message,
    staff: StaffUser | None,
    state: FSMContext,
) -> None:
    """📊 Обработка ввода периода и генерация отчёта.
    
    Ожидаемые форматы:
    - "YYYY-MM-DD YYYY-MM-DD" (ISO)
    - "DD.MM.YYYY DD.MM.YYYY" (русский)
    """
    period = _parse_period_input(msg.text or "")
    if not period:
        await msg.answer(
            "⚠️ <b>Неверный формат дат</b>\n\n"
            "Укажите период в формате: <code>YYYY-MM-DD YYYY-MM-DD</code>\n"
            "Пример: <code>2025-01-01 2025-01-31</code>\n\n"
            "Или используйте кнопки ниже для быстрого выбора.",
            reply_markup=reports_periods_keyboard(),
        )
        return

    start_dt, end_dt = period
    data = await state.get_data()
    report_kind = data.get("report_kind")
    definition = REPORT_DEFINITIONS.get(report_kind or "")
    if not definition:
        await state.clear()
        await msg.answer(
            "❌ <b>Ошибка</b>\n\n"
            "Неизвестный тип отчёта.\n"
            "Пожалуйста, выберите отчёт из меню:",
            reply_markup=reports_menu_keyboard(),
        )
        return

    label, exporter, caption_prefix = definition
    
    # RBAC:   
    city_ids = visible_city_ids_for(staff) if isinstance(staff, StaffUser) else None

    # P0-8: Показываем статус прогресса
    await msg.answer("🔄 <b>Генерация отчёта</b>\n\nПодождите, обрабатываем данные...")

    try:
        bundle = await exporter(date_from=start_dt, date_to=end_dt, city_ids=city_ids)
    except Exception as exc:
        await state.clear()
        await msg.answer(
            f"❌ Ошибка при генерации: {exc}",
            reply_markup=reports_menu_keyboard(),
        )
        return

    period_label = _format_period_label(start_dt, end_dt)
    
    operator_chat_id = None
    if msg.chat:
        operator_chat_id = msg.chat.id
    elif msg.from_user:
        operator_chat_id = msg.from_user.id
    
    configured_chat_id: Optional[int] = None
    try:
        settings_service = _settings_service(msg.bot)
        raw_channel_id = await settings_service.get_value("reports_channel_id")
    except Exception:
        raw_channel_id = None
    
    if raw_channel_id:
        candidate = raw_channel_id.strip()
        if candidate and candidate != "-":
            try:
                configured_chat_id = int(candidate)
            except ValueError:
                configured_chat_id = None
    
    target_chat_id = configured_chat_id or env_settings.reports_channel_id or operator_chat_id
    if target_chat_id is None:
        await state.clear()
        await msg.answer(
            "❌ <b>Ошибка конфигурации</b>\n\n"
            "Не указан канал для отправки отчётов.\n"
            "Обратитесь к глобальному администратору.",
            reply_markup=reports_menu_keyboard(),
        )
        return

    try:
        await _send_export_documents(
            msg.bot,
            bundle,
            f"{caption_prefix} {period_label}",
            chat_id=target_chat_id,
        )
    except TelegramBadRequest:
        #       -  
        if operator_chat_id is not None and target_chat_id != operator_chat_id:
            await _send_export_documents(
                msg.bot,
                bundle,
                f"{caption_prefix} {period_label}",
                chat_id=operator_chat_id,
            )
            await msg.answer(
                "ℹ️ <b>Отчёт отправлен в личные сообщения</b>\n\n"
                "Не удалось отправить в настроенный канал.\n"
                "Отчёт отправлен вам напрямую."
            )
        else:
            await state.clear()
            await msg.answer(
                "❌ <b>Ошибка отправки</b>\n\n"
                "Не удалось отправить отчёт. Попробуйте позже."
            )
            return
    else:
        await msg.answer("✅ <b>Отчёт успешно сформирован</b>\n\nФайлы CSV и XLSX отправлены.")
    
    await state.clear()


@router.callback_query(F.data.regexp(r"^adm:r:pd:(today|yesterday|last7|this_month|prev_month|custom)$"))
async def reports_quick_period_choice(
    cq: CallbackQuery,
    state: FSMContext,
    staff: StaffUser | None = None,
) -> None:
    """⏱️ Быстрый выбор периода и генерация отчёта.
    
    Доступные периоды:
    - today: Сегодня
    - yesterday: Вчера
    - last7: Последние 7 дней
    - this_month: Текущий месяц
    - prev_month: Предыдущий месяц
    - custom: Ввод вручную
    """
    key = (cq.data or "").rsplit(":", 1)[-1]
    data = await state.get_data()
    report_kind = data.get("report_kind")
    definition = REPORT_DEFINITIONS.get(report_kind or "")
    if not definition:
        await state.clear()
        if cq.message:
            await cq.message.edit_text(
                "<b>📊 Отчёты</b>\n\nВыберите тип отчёта:",
                reply_markup=reports_menu_keyboard()
            )
        await cq.answer()
        return
    
    if key == "custom":
        if cq.message:
            await cq.message.answer(
                "📅 <b>Введите период</b>\n\n"
                "Формат: <code>YYYY-MM-DD YYYY-MM-DD</code>\n"
                "Пример: <code>2025-01-01 2025-01-31</code>\n\n"
                "Для отмены нажмите /cancel"
            )
        await cq.answer()
        return
    
    period = _compute_quick_period(key, tz=env_settings.timezone)
    if not period:
        await cq.answer("❌ Неверный период", show_alert=True)
        return
    
    start_dt, end_dt = period
    label, exporter, caption_prefix = definition
    
    # RBAC:   
    city_ids = visible_city_ids_for(staff) if isinstance(staff, StaffUser) else None
    
    # P0-8: Показываем статус прогресса в callback query
    await cq.answer("🔄 Генерируем отчёт...", show_alert=False)
    if cq.message:
        await cq.message.answer("🔄 <b>Генерация отчёта</b>\n\nПодождите, обрабатываем данные...")
    
    try:
        bundle = await exporter(date_from=start_dt, date_to=end_dt, city_ids=city_ids)
    except Exception as exc:
        if cq.message:
            await cq.message.answer(
                f"❌ <b>Ошибка экспорта</b>\n\n{exc}",
                reply_markup=reports_menu_keyboard(),
            )
        await cq.answer()
        return
    
    period_label = _format_period_label(start_dt, end_dt)
    
    target_chat_id = env_settings.reports_channel_id or (cq.message.chat.id if cq.message else None)
    if target_chat_id is None and cq.from_user:
        target_chat_id = cq.from_user.id
    if target_chat_id is None:
        if cq.message:
            await cq.message.answer(
                "❌ <b>Ошибка конфигурации</b>\n\n"
                "Не указан канал для отправки отчётов.",
                reply_markup=reports_menu_keyboard()
            )
        await cq.answer()
        return
    
    try:
        await _send_export_documents(
            cq.bot,
            bundle,
            f"{caption_prefix} {period_label}",
            chat_id=target_chat_id,
        )
    except TelegramBadRequest:
        # Fallback   
        if cq.from_user:
            await _send_export_documents(
                cq.bot,
                bundle,
                f"{caption_prefix} {period_label}",
                chat_id=cq.from_user.id,
            )
            if cq.message:
                await cq.message.answer(
                    "ℹ️ <b>Отчёт отправлен в личные сообщения</b>\n\n"
                    "Не удалось отправить в настроенный канал."
                )
        else:
            if cq.message:
                await cq.message.answer(
                    "❌ <b>Ошибка отправки</b>\n\n"
                    "Не удалось отправить отчёт."
                )
            await cq.answer()
            return
    else:
        if cq.message:
            await cq.message.answer(
                "✅ <b>Отчёт успешно сформирован</b>\n\n"
                "Файлы CSV и XLSX отправлены."
            )
    
    await state.clear()
    # P0-8: cq.answer()        


__all__ = [
    "router",
    "REPORT_DEFINITIONS",
]
