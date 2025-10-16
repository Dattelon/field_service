# field_service/bots/admin_bot/handlers/reports.py
"""   (ReportsExportFSM)."""
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


#   
REPORT_DEFINITIONS: dict[str, tuple[str, Any, str]] = {
    "orders": ("", export_service.export_orders, "Orders"),
    "commissions": ("", export_service.export_commissions, "Commissions"),
    "ref_rewards": (" ", export_service.export_referral_rewards, "Referral rewards"),
}

#   
DATE_INPUT_FORMATS = ("%Y-%m-%d", "%d.%m.%Y")


# ============================================
# 
# ============================================

def _parse_period_input(text: str) -> Optional[tuple[date, date]]:
    """
       .
    
     : "YYYY-MM-DD YYYY-MM-DD"  "DD.MM.YYYY DD.MM.YYYY"
    
    Returns:
        (start_date, end_date)  None    
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
    """
        .
    
    Args:
        key:   (today, yesterday, last7, this_month, prev_month)
        tz:  
    
    Returns:
        (start_date, end_date)  None
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
    """
       .
    
    Args:
        start_dt:  
        end_dt:  
    
    Returns:
          "01.01.2025 - 31.01.2025"
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
    """
       (CSV  XLSX).
    
    Args:
        bot: Bot instance
        bundle: ExportBundle  CSV  XLSX 
        caption:   
        chat_id: ID   
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
# 
# ============================================

@router.callback_query(
    F.data == "adm:r",
    StaffRoleFilter({StaffRole.GLOBAL_ADMIN, StaffRole.CITY_ADMIN}),
)
async def cb_reports(cq: CallbackQuery, staff: StaffUser, state: FSMContext) -> None:
    """  ."""
    await state.clear()
    await cq.message.edit_text(" :", reply_markup=reports_menu_keyboard())
    await cq.answer()


async def _prompt_report_period(cq: CallbackQuery, state: FSMContext, report_kind: str) -> None:
    """
        .
    
    Args:
        cq: CallbackQuery
        state: FSMContext
        report_kind:   (orders, commissions, ref_rewards)
    """
    await state.clear()
    label, _, _ = REPORT_DEFINITIONS[report_kind]
    await state.set_state(ReportsExportFSM.awaiting_period)
    await state.update_data(report_kind=report_kind)
    await cq.message.answer(
        f"    ({label})   :",
        reply_markup=reports_periods_keyboard(),
    )
    await cq.answer()


@router.callback_query(
    F.data == "adm:r:o",
    StaffRoleFilter({StaffRole.GLOBAL_ADMIN, StaffRole.CITY_ADMIN}),
)
async def cb_reports_orders(cq: CallbackQuery, state: FSMContext) -> None:
    """   ."""
    await _prompt_report_period(cq, state, "orders")


@router.callback_query(
    F.data == "adm:r:c",
    StaffRoleFilter({StaffRole.GLOBAL_ADMIN, StaffRole.CITY_ADMIN}),
)
async def cb_reports_commissions(cq: CallbackQuery, state: FSMContext) -> None:
    """   ."""
    await _prompt_report_period(cq, state, "commissions")


@router.callback_query(
    F.data == "adm:r:rr",
    StaffRoleFilter({StaffRole.GLOBAL_ADMIN, StaffRole.CITY_ADMIN}),
)
async def cb_reports_referrals(cq: CallbackQuery, state: FSMContext) -> None:
    """    ."""
    await _prompt_report_period(cq, state, "ref_rewards")


@router.message(StateFilter(ReportsExportFSM.awaiting_period), F.text == "/cancel")
async def reports_cancel(msg: Message, state: FSMContext) -> None:
    """  ."""
    await state.clear()
    await msg.answer(" .")


@router.message(StateFilter(ReportsExportFSM.awaiting_period))
async def reports_period_submit(
    msg: Message,
    staff: StaffUser | None,
    state: FSMContext,
) -> None:
    """
       .
    
     : "YYYY-MM-DD YYYY-MM-DD"  "DD.MM.YYYY DD.MM.YYYY"
    """
    period = _parse_period_input(msg.text or "")
    if not period:
        await msg.answer(
            " .    'YYYY-MM-DD YYYY-MM-DD'   .",
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
            ":    .    :",
            reply_markup=reports_menu_keyboard(),
        )
        return

    label, exporter, caption_prefix = definition
    
    # RBAC:   
    city_ids = visible_city_ids_for(staff) if isinstance(staff, StaffUser) else None

    # P0-8:     
    await msg.answer("  , ...")

    try:
        bundle = await exporter(date_from=start_dt, date_to=end_dt, city_ids=city_ids)
    except Exception as exc:
        await state.clear()
        await msg.answer(
            f"   : {exc}",
            reply_markup=reports_menu_keyboard(),
        )
        return

    period_label = _format_period_label(start_dt, end_dt)
    
    #   
    operator_chat_id = None
    if msg.chat:
        operator_chat_id = msg.chat.id
    elif msg.from_user:
        operator_chat_id = msg.from_user.id
    
    #    
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
            "    .",
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
            await msg.answer("    , ..  .")
        else:
            await state.clear()
            await msg.answer("   .")
            return
    else:
        await msg.answer("  .")
    
    await state.clear()


@router.callback_query(F.data.regexp(r"^adm:r:pd:(today|yesterday|last7|this_month|prev_month|custom)$"))
async def reports_quick_period_choice(
    cq: CallbackQuery,
    state: FSMContext,
    staff: StaffUser | None = None,
) -> None:
    """
       .
    
    :
    - today: 
    - yesterday: 
    - last7:  7 
    - this_month:  
    - prev_month:  
    - custom:  
    """
    key = (cq.data or "").rsplit(":", 1)[-1]
    data = await state.get_data()
    report_kind = data.get("report_kind")
    definition = REPORT_DEFINITIONS.get(report_kind or "")
    if not definition:
        await state.clear()
        if cq.message:
            await cq.message.edit_text(" :", reply_markup=reports_menu_keyboard())
        await cq.answer()
        return
    
    if key == "custom":
        if cq.message:
            await cq.message.answer(
                "   : YYYY-MM-DD YYYY-MM-DD\n  /cancel  ."
            )
        await cq.answer()
        return
    
    period = _compute_quick_period(key, tz=env_settings.timezone)
    if not period:
        await cq.answer(" ", show_alert=True)
        return
    
    start_dt, end_dt = period
    label, exporter, caption_prefix = definition
    
    # RBAC:   
    city_ids = visible_city_ids_for(staff) if isinstance(staff, StaffUser) else None
    
    # P0-8:    callback query
    await cq.answer("  ...", show_alert=False)
    if cq.message:
        await cq.message.answer("  , ...")
    
    try:
        bundle = await exporter(date_from=start_dt, date_to=end_dt, city_ids=city_ids)
    except Exception as exc:
        if cq.message:
            await cq.message.answer(
                f"   : {exc}",
                reply_markup=reports_menu_keyboard(),
            )
        await cq.answer()
        return
    
    period_label = _format_period_label(start_dt, end_dt)
    
    #   
    target_chat_id = env_settings.reports_channel_id or (cq.message.chat.id if cq.message else None)
    if target_chat_id is None and cq.from_user:
        target_chat_id = cq.from_user.id
    if target_chat_id is None:
        if cq.message:
            await cq.message.answer("    .", reply_markup=reports_menu_keyboard())
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
                await cq.message.answer("     ( ).")
        else:
            if cq.message:
                await cq.message.answer("   .")
            await cq.answer()
            return
    else:
        if cq.message:
            await cq.message.answer("  .")
    
    await state.clear()
    # P0-8: cq.answer()        


__all__ = [
    "router",
    "REPORT_DEFINITIONS",
]
