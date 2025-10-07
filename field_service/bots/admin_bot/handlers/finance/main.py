from __future__ import annotations

import html
import re
from typing import Any, Iterable, Optional

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramNotFound
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from field_service.services import live_log, owner_requisites_service

from ...core.dto import StaffRole, StaffUser, WaitPayRecipient, CommissionListItem, CommissionDetail
from ...core.filters import StaffRoleFilter
from ...ui.keyboards import finance_menu, owner_pay_actions_keyboard, owner_pay_edit_keyboard, finance_segment_keyboard, finance_card_actions, finance_reject_cancel_keyboard
from ...core.states import OwnerPayEditFSM, FinanceActionFSM
from ...utils.helpers import get_service


router = Router(name="admin_finance")


# CR-2025-10-03-012: Safe callback answer wrapper
async def _safe_answer(cq: CallbackQuery, text: str = "", show_alert: bool = False) -> None:
    """Safely answer callback query, ignoring 'query is too old' errors."""
    try:
        await cq.answer(text, show_alert=show_alert)
    except TelegramBadRequest as exc:
        if "query is too old" not in str(exc).lower():
            raise

PAYMENT_METHOD_LABELS = {
    "card": "💳 Карта",
    "sbp": "СБП",
    "cash": "Наличные",
}

_METHOD_ALIASES = {
    # Карта
    "card": "card",
    "карта": "card",
    "банковская карта": "card",
    "банк карта": "card",
    "visa": "card",
    "mastercard": "card",
    "мир": "card",
    # СБП
    "sbp": "sbp",
    "сбп": "sbp",
    "система быстрых платежей": "sbp",
    "qr": "sbp",
    "кьюар": "sbp",
    "кью-ар": "sbp",
    # Наличные
    "cash": "cash",
    "наличные": "cash",
    "нал": "cash",
    "наличными": "cash",
}

_OWNER_FIELDS = {
    "methods": "Способы оплаты",
    "card_number": "Номер карты",
    "card_holder": "Держатель карты",
    "card_bank": "Банк карты",
    "sbp_phone": "Телефон для СБП",
    "sbp_bank": "Банк для СБП",
    "sbp_qr_file_id": "QR-код СБП",
    "other_text": "Дополнительная информация",
    "comment_template": "Шаблон комментария",
}


def _settings_service(bot: Any):
    return get_service(bot, "settings_service")


def _finance_service(bot: Any):
    return get_service(bot, "finance_service")


async def _render_owner_snapshot(
    bot_message: Message,
    staff: StaffUser,
    *,
    notify_empty: bool = False,
) -> Optional[tuple[int, int]]:
    if bot_message is None:
        return None
    settings_service = _settings_service(bot_message.bot)
    snapshot = await settings_service.get_owner_pay_snapshot()
    text = _format_snapshot_text(snapshot, for_staff=True)
    markup = owner_pay_actions_keyboard()
    try:
        await bot_message.edit_text(text, reply_markup=markup)
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            await bot_message.answer(text, reply_markup=markup)
    if notify_empty:
        await bot_message.answer("Заполните реквизиты для приема платежей.")
    return (bot_message.chat.id, bot_message.message_id)


def _format_snapshot_text(snapshot: dict[str, Any], *, for_staff: bool) -> str:
    data = owner_requisites_service.ensure_schema(snapshot)
    methods = _format_methods(data.get("methods") or [])
    lines: list[str] = []
    if for_staff:
        lines.append("<b>Реквизиты владельца</b>")
    else:
        lines.append("<b>Оплата комиссии</b>")
    lines.append(f"Способы оплаты: {methods}")

    card_block = _format_card_block(data)
    sbp_block = _format_sbp_block(data, include_qr=for_staff)
    other_text = data.get("other_text") or ""
    comment_template = data.get("comment_template") or ""

    if card_block:
        lines.append("")
        lines.extend(card_block)
    if sbp_block:
        lines.append("")
        lines.extend(sbp_block)
    if other_text:
        lines.append("")
        lines.append("<b>Дополнительно</b>")
        lines.append(html.escape(other_text))
    if comment_template:
        lines.append("")
        lines.append("<b>Шаблон комментария</b>")
        lines.append(html.escape(comment_template))

    if not for_staff:
        lines.append("")
        lines.append(
            "Оплата по реквизитам выше. При прикреплении чека укажите комментарий к оплате."
        )

    return "\n".join(lines)


def _format_methods(methods: Iterable[str]) -> str:
    items: list[str] = []
    for raw in methods:
        key = str(raw).strip().lower()
        if not key:
            continue
        label = PAYMENT_METHOD_LABELS.get(key, key.upper())
        items.append(label)
    return ", ".join(items) if items else ""


def _format_card_block(data: dict[str, Any]) -> list[str]:
    card_number = data.get("card_number") or ""
    card_holder = data.get("card_holder") or ""
    card_bank = data.get("card_bank") or ""
    block: list[str] = []
    if card_number or card_holder or card_bank:
        block.append("<b>Банковская карта</b>")
        if card_number:
            block.append(f"Номер: {html.escape(card_number)}")
        if card_holder:
            block.append(f"Держатель: {html.escape(card_holder)}")
        if card_bank:
            block.append(f"Банк: {html.escape(card_bank)}")
    return block


def _format_sbp_block(data: dict[str, Any], *, include_qr: bool) -> list[str]:
    phone = data.get("sbp_phone") or ""
    bank = data.get("sbp_bank") or ""
    qr = data.get("sbp_qr_file_id") or ""
    block: list[str] = []
    if phone or bank or (include_qr and qr):
        block.append("<b>СБП</b>")
        if phone:
            block.append(f"Телефон: {html.escape(phone)}")
        if bank:
            block.append(f"Банк: {html.escape(bank)}")
        if include_qr:
            block.append("QR-код: " + ("прикреплён" if qr else "отсутствует"))
    return block


def _parse_methods_payload(text: str) -> list[str]:
    cleaned = text.strip()
    if not cleaned or cleaned in {"-", "", "none", "нет"}:
        return []
    result: list[str] = []
    pieces = re.split(r"[\n;,]+", cleaned)
    for piece in pieces:
        piece = piece.strip().lower()
        if not piece:
            continue
        alias = _METHOD_ALIASES.get(piece)
        if not alias and " " in piece:
            for token in piece.split():
                alias = _METHOD_ALIASES.get(token)
                if alias:
                    break
        if not alias:
            raise ValueError(f"Неизвестный способ оплаты: {piece}")
        if alias not in owner_requisites_service.ALLOWED_METHODS:
            raise ValueError(f"Недопустимый способ оплаты: {piece}")
        if alias not in result:
            result.append(alias)
    return result


def _extract_field_value(field: str, message: Message) -> Any:
    if field == "methods":
        if not message.text:
            raise ValueError("Нужно прислать список способов оплаты.")
        return _parse_methods_payload(message.text)

    if field == "sbp_qr_file_id":
        if message.photo:
            return message.photo[-1].file_id
        if message.document:
            return message.document.file_id
        text = (message.caption or message.text or "").strip()
        if not text or text == "-":
            return ""
        return text

    text = (message.text or message.caption or "").strip()
    if not text or text == "-":
        return ""
    return text


async def _update_owner_snapshot(bot, field: str, value: Any) -> dict[str, Any]:
    settings_service = _settings_service(bot)
    snapshot = await settings_service.get_owner_pay_snapshot()
    snapshot[field] = value
    await settings_service.update_owner_pay_snapshot(**snapshot)
    return snapshot


def _get_origin(data: dict[str, Any]) -> Optional[tuple[int, int]]:
    origin = data.get("owner_pay_origin")
    if isinstance(origin, (list, tuple)) and len(origin) == 2:
        try:
            return int(origin[0]), int(origin[1])
        except (TypeError, ValueError):
            return None
    return None


async def _rerender_origin(bot, staff: StaffUser, origin: Optional[tuple[int, int]]) -> None:
    if not origin:
        return
    chat_id, message_id = origin
    settings_service = _settings_service(bot)
    snapshot = await settings_service.get_owner_pay_snapshot()
    text = _format_snapshot_text(snapshot, for_staff=True)
    markup = owner_pay_actions_keyboard()
    try:
        await bot.edit_message_text(text, chat_id=chat_id, message_id=message_id, reply_markup=markup)
    except TelegramBadRequest:
        await bot.send_message(chat_id, text, reply_markup=markup)


async def _broadcast_owner_requisites(
    bot,
    recipients: Iterable[WaitPayRecipient],
    snapshot: dict[str, Any],
) -> tuple[int, int]:
    sent = 0
    failed = 0
    text = _format_snapshot_text(snapshot, for_staff=False)
    qr = (snapshot.get("sbp_qr_file_id") or "").strip()
    for recipient in recipients:
        if recipient.tg_user_id is None:
            continue
        try:
            if qr:
                await bot.send_photo(recipient.tg_user_id, qr, caption=text)
            else:
                await bot.send_message(recipient.tg_user_id, text)
        except (TelegramForbiddenError, TelegramNotFound):
            failed += 1
        except TelegramBadRequest:
            failed += 1
        else:
            sent += 1
    return sent, failed


@router.callback_query(
    F.data == "adm:f:set",
    StaffRoleFilter({StaffRole.GLOBAL_ADMIN}),
)
async def on_owner_requisites_show(
    cq: CallbackQuery,
    staff: StaffUser,
    state: FSMContext,
) -> None:
    if not cq.message:
        await _safe_answer(cq)
        return
    origin = await _render_owner_snapshot(cq.message, staff)
    if origin:
        await state.update_data(owner_pay_origin=origin)
    await _safe_answer(cq)


@router.callback_query(
    F.data == "adm:f:set:edit",
    StaffRoleFilter({StaffRole.GLOBAL_ADMIN}),
)
async def on_owner_requisites_edit_menu(
    cq: CallbackQuery,
    staff: StaffUser,
    state: FSMContext,
) -> None:
    if not cq.message:
        await _safe_answer(cq)
        return
    settings_service = _settings_service(cq.message.bot)
    snapshot = await settings_service.get_owner_pay_snapshot()
    lines = ["<b> </b>", "   :"]
    for field, label in _OWNER_FIELDS.items():
        current = snapshot.get(field)
        if field == "methods":
            rendered = _format_methods(current or [])
        elif isinstance(current, str):
            rendered = current or ""
        else:
            rendered = ""
        lines.append(f" {label}: {html.escape(rendered)}")
    try:
        await cq.message.edit_text("\n".join(lines), reply_markup=owner_pay_edit_keyboard())
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            await cq.message.answer("\n".join(lines), reply_markup=owner_pay_edit_keyboard())
    await state.update_data(owner_pay_origin=(cq.message.chat.id, cq.message.message_id))
    await _safe_answer(cq)


@router.callback_query(
    F.data.startswith("adm:f:set:field:"),
    StaffRoleFilter({StaffRole.GLOBAL_ADMIN}),
)
async def on_owner_requisites_field_select(
    cq: CallbackQuery,
    staff: StaffUser,
    state: FSMContext,
) -> None:
    if not cq.message or not cq.data:
        await _safe_answer(cq)
        return
    field = cq.data.split(":", maxsplit=3)[-1]
    if field not in _OWNER_FIELDS:
        await _safe_answer(cq, " ", show_alert=True)
        return
    settings_service = _settings_service(cq.message.bot)
    snapshot = await settings_service.get_owner_pay_snapshot()
    current = snapshot.get(field)
    if field == "methods":
        rendered = _format_methods(current or [])
        prompt = (
            "     (card, sbp, cash).\n"
            "   ,  ."
        )
    elif field == "sbp_qr_file_id":
        rendered = "" if current else " "
        prompt = " /  QR-   file_id.    ."
    else:
        rendered = current or ""
        prompt = "  .    ."
    await state.set_state(OwnerPayEditFSM.value)
    await state.update_data(
        owner_pay_field=field,
        owner_pay_origin=(cq.message.chat.id, cq.message.message_id),
    )
    await cq.message.answer(
        f"<b>{_OWNER_FIELDS[field]}</b>\n : {html.escape(str(rendered))}\n\n{prompt}"
    )
    await _safe_answer(cq)


@router.message(StateFilter(OwnerPayEditFSM.value), F.text == "/cancel")
async def on_owner_requisites_edit_cancel(
    msg: Message,
    staff: StaffUser,
    state: FSMContext,
) -> None:
    data = await state.get_data()
    origin = _get_origin(data)
    await state.set_state(None)
    await state.update_data(owner_pay_field=None, owner_pay_origin=origin)
    await msg.answer(" .")
    await _rerender_origin(msg.bot, staff, origin)


# ============================================
# P2-11: МАССОВОЕ ОДОБРЕНИЕ КОМИССИЙ
# ============================================

@router.callback_query(
    F.data == "adm:f:bulk",
    StaffRoleFilter({StaffRole.GLOBAL_ADMIN}),
)
async def on_finance_bulk_approve_start(
    cq: CallbackQuery,
    staff: StaffUser,
    state: FSMContext,
) -> None:
    """Начать массовое одобрение комиссий."""
    if not cq.message:
        await _safe_answer(cq)
        return
    
    builder = InlineKeyboardBuilder()
    builder.button(text="📅 За сегодня", callback_data="adm:f:bulk:1")
    builder.button(text="📅 За 3 дня", callback_data="adm:f:bulk:3")
    builder.button(text="📅 За неделю", callback_data="adm:f:bulk:7")
    builder.button(text="❌ Отмена", callback_data="adm:f")
    builder.adjust(1)
    
    try:
        await cq.message.edit_text(
            "<b>⚡ Массовое одобрение комиссий</b>\n\n"
            "Выберите период для одобрения всех комиссий в статусе WAIT_PAY:",
            reply_markup=builder.as_markup(),
            parse_mode="HTML",
        )
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            await cq.message.answer(
                "<b>⚡ Массовое одобрение комиссий</b>\n\n"
                "Выберите период:",
                reply_markup=builder.as_markup(),
                parse_mode="HTML",
            )
    await _safe_answer(cq)


@router.callback_query(
    F.data.regexp(r"^adm:f:bulk:(\d+)$"),
    StaffRoleFilter({StaffRole.GLOBAL_ADMIN}),
)
async def on_finance_bulk_approve_confirm(
    cq: CallbackQuery,
    staff: StaffUser,
    state: FSMContext,
) -> None:
    """Подтверждение массового одобрения."""
    if not cq.message or not cq.data:
        await _safe_answer(cq)
        return
    
    parts = cq.data.split(":")
    try:
        days = int(parts[-1])
    except (ValueError, IndexError):
        await _safe_answer(cq, "Некорректный период", show_alert=True)
        return
    
    # Сохранить период в состояние
    await state.update_data(bulk_days=days, bulk_chat_id=cq.message.chat.id)
    
    # Показать подтверждение
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Подтвердить", callback_data=f"adm:f:bulk:exec:{days}")
    builder.button(text="❌ Отмена", callback_data="adm:f")
    builder.adjust(1)
    
    period_label = {
        1: "сегодня",
        3: "последние 3 дня",
        7: "последнюю неделю",
    }.get(days, f"последние {days} дней")
    
    try:
        await cq.message.edit_text(
            f"<b>⚠️ Подтвердите массовое одобрение</b>\n\n"
            f"Будут одобрены ВСЕ комиссии за {period_label} в статусе WAIT_PAY.\n\n"
            f"Вы уверены?",
            reply_markup=builder.as_markup(),
            parse_mode="HTML",
        )
    except TelegramBadRequest:
        await cq.message.answer(
            f"<b>⚠️ Подтвердите массовое одобрение</b>\n\n"
            f"Будут одобрены ВСЕ комиссии за {period_label}.\n\nВы уверены?",
            reply_markup=builder.as_markup(),
            parse_mode="HTML",
        )
    await _safe_answer(cq)


@router.callback_query(
    F.data.regexp(r"^adm:f:bulk:exec:(\d+)$"),
    StaffRoleFilter({StaffRole.GLOBAL_ADMIN}),
)
async def on_finance_bulk_approve_execute(
    cq: CallbackQuery,
    staff: StaffUser,
    state: FSMContext,
) -> None:
    """Выполнить массовое одобрение."""
    if not cq.message or not cq.data:
        await _safe_answer(cq)
        return
    
    parts = cq.data.split(":")
    try:
        days = int(parts[-1])
    except (ValueError, IndexError):
        await _safe_answer(cq, "Некорректный период", show_alert=True)
        return
    
    await _safe_answer(cq, "Обработка... Пожалуйста, подождите.")
    
    # Выполнить массовое одобрение
    finance_service = _finance_service(cq.message.bot)
    
    try:
        # Получить city_ids для RBAC
        city_ids = None
        if staff.role != StaffRole.GLOBAL_ADMIN:
            city_ids = staff.city_ids
        
        # Вычисляем start_date и end_date
        from datetime import date, timedelta
        end_date = date.today()
        start_date = end_date - timedelta(days=days - 1)
        
        approved_count, errors = await finance_service.bulk_approve_commissions(
            start_date=start_date,
            end_date=end_date,
            city_ids=city_ids,
            by_staff_id=staff.id,
        )
        
        approved = approved_count
        failed = len(errors)
        
        period_label = {
            1: "сегодня",
            3: "последние 3 дня",
            7: "последнюю неделю",
        }.get(days, f"последние {days} дней")
        
        builder = InlineKeyboardBuilder()
        builder.button(text="🔙 К финансам", callback_data="adm:f")
        builder.adjust(1)
        
        result_text = (
            f"<b>✅ Массовое одобрение завершено</b>\n\n"
            f"📅 Период: {period_label}\n"
            f"✅ Одобрено: {approved}\n"
        )
        
        if failed > 0:
            result_text += f"⚠️ Ошибок: {failed}\n"
        
        await cq.message.edit_text(
            result_text,
            reply_markup=builder.as_markup(),
            parse_mode="HTML",
        )
        
    except Exception as exc:
        from field_service.services import live_log as log_service
        log_service.push("finance", f"bulk_approve error: {exc}", level="ERROR")
        
        try:
            await cq.message.edit_text(
                f"<b>❌ Ошибка при массовом одобрении</b>\n\n"
                f"{html.escape(str(exc))}",
                parse_mode="HTML",
            )
        except TelegramBadRequest:
            await cq.message.answer(
                f"<b>❌ Ошибка</b>\n\n{html.escape(str(exc))}",
                parse_mode="HTML",
            )
    
    await state.clear()


@router.message(StateFilter(OwnerPayEditFSM.value))
async def on_owner_requisites_edit_value(
    msg: Message,
    staff: StaffUser,
    state: FSMContext,
) -> None:
    data = await state.get_data()
    field = data.get("owner_pay_field")
    if not field or field not in _OWNER_FIELDS:
        await state.set_state(None)
        await msg.answer("  ,     .")
        return
    origin = _get_origin(data)
    try:
        value = _extract_field_value(field, msg)
    except ValueError as exc:
        await msg.answer(str(exc))
        return
    snapshot = await _update_owner_snapshot(msg.bot, field, value)
    await state.set_state(None)
    await state.update_data(owner_pay_field=None, owner_pay_origin=origin)
    await msg.answer(" .")
    live_log.push("finance", f"owner_pay:{field} updated by staff {staff.id}")
    await _rerender_origin(msg.bot, staff, origin)


@router.callback_query(
    F.data == "adm:f:set:bc",
    StaffRoleFilter({StaffRole.GLOBAL_ADMIN}),
)
async def on_owner_requisites_broadcast(
    cq: CallbackQuery,
    staff: StaffUser,
    state: FSMContext,
) -> None:
    if not cq.message:
        await _safe_answer(cq)
        return
    finance_service = _finance_service(cq.message.bot)
    settings_service = _settings_service(cq.message.bot)
    snapshot = await settings_service.get_owner_pay_snapshot()
    recipients = await finance_service.list_wait_pay_recipients()
    if not recipients:
        await _safe_answer(cq, "    ", show_alert=True)
        return
    sent, failed = await _broadcast_owner_requisites(cq.message.bot, recipients, snapshot)
    live_log.push(
        "finance",
        f"owner_pay broadcast by staff {staff.id}: sent={sent} failed={failed}",
    )
    await _safe_answer(cq, " ")
    summary = f"  {sent} ."
    if failed:
        summary += f"   : {failed}."
    await cq.message.answer(summary, reply_markup=finance_menu(staff))
    await _rerender_origin(cq.message.bot, staff, (cq.message.chat.id, cq.message.message_id))


# ============================================
# P2-07: ОБРАБОТЧИКИ СПИСКОВ КОМИССИЙ
# ============================================

FINANCE_SEGMENT_TITLES = {
    "aw": "Ожидают оплаты",
    "pd": "Оплаченные",
    "ov": "Просроченные",
}

from ...core.access import visible_city_ids_for
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def finance_list_line(item: CommissionListItem) -> str:
    """Format commission list item."""
    return f"#{item.id} | {item.amount:.0f} ₽ | {item.master_name or 'N/A'}"


def format_commission_detail(detail: CommissionDetail) -> str:
    """Format commission detail card."""
    lines = [
        f"<b>Комиссия #{detail.id}</b>",
        f"Заказ: #{detail.order_id}",
        f"Мастер: {html.escape(detail.master_name or 'N/A')}",
        f"Сумма: {detail.amount:.2f} ₽",
        f"Статус: {detail.status}",
    ]
    if detail.deadline_at_local:
        lines.append(f"Дедлайн: {detail.deadline_at_local}")
    if detail.paid_amount:
        lines.append(f"Оплачено: {detail.paid_amount:.2f} ₽")
    return "\n".join(lines)


class _MessageEditProxy:
    """Proxy to make callback message editable like a regular message."""
    def __init__(self, bot, chat_id: int, message_id: int):
        self.bot = bot
        self.chat = type('obj', (object,), {'id': chat_id})()
        self.message_id = message_id

    async def edit_text(self, text: str, reply_markup=None, **kwargs):
        await self.bot.edit_message_text(
            text,
            chat_id=self.chat.id,
            message_id=self.message_id,
            reply_markup=reply_markup,
            **kwargs
        )


async def _render_finance_segment(
    message,
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
        text = f"<b>{title}</b>\n  ."
    else:
        lines = [f"<b>{title}</b>", ""]
        for row in rows:
            if isinstance(row, CommissionListItem):
                lines.append(f" {html.escape(finance_list_line(row))}")
            else:
                lines.append(f" {html.escape(str(row))}")
        text = "\n".join(lines)

    button_rows: list[list[InlineKeyboardButton]] = []
    for row in rows:
        if isinstance(row, CommissionListItem):
            label = f"#{row.id}  {row.amount:.0f} "
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
        await _safe_answer(cq)
        return
    await _render_finance_segment(cq.message, staff, "aw", page, state)
    await _safe_answer(cq)


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
        await _safe_answer(cq)
        return
    await _render_finance_segment(cq.message, staff, "pd", page, state)
    await _safe_answer(cq)


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
        await _safe_answer(cq)
        return
    await _render_finance_segment(cq.message, staff, "ov", page, state)
    await _safe_answer(cq)


# CR-2025-10-03-013: СПЕЦИФИЧНЫЕ обработчики ВЫШЕ общего!
# CR-2025-10-03-011: Обработчик быстрого одобрения
@router.callback_query(
    F.data.startswith("adm:f:cm:approve:"),
    StaffRoleFilter({StaffRole.GLOBAL_ADMIN, StaffRole.CITY_ADMIN}),
)
async def cb_finance_approve_instant(cq: CallbackQuery, staff: StaffUser, state: FSMContext) -> None:
    """Fast-track approval with default amount."""
    from decimal import Decimal
    
    parts = cq.data.split(":")
    commission_id = int(parts[4])
    
    # CR-2025-10-03-FIX: Validate staff.id before database operations
    if not staff or staff.id is None or staff.id <= 0:
        await _safe_answer(cq, "❌ Ошибка: некорректный ID персонала", show_alert=True)
        return
    
    data = await state.get_data()
    default_amount = Decimal(data.get("default_amount", "0"))
    segment = data.get("segment", "aw")
    page = int(data.get("page", 1))
    source_chat_id = data.get("source_chat_id")
    source_message_id = data.get("source_message_id")
    
    finance_service = _finance_service(cq.message.bot)
    ok = await finance_service.approve(commission_id, paid_amount=default_amount, by_staff_id=staff.id)
    await state.clear()
    
    if ok:
        live_log.push("finance", f"commission#{commission_id} approved by staff {staff.id} amount={default_amount}")
        
        # CR-2025-10-03-014: Красивое сообщение об успехе
        builder = InlineKeyboardBuilder()
        builder.button(text="📋 К списку ожидающих", callback_data="adm:f:aw:1")
        builder.button(text="💰 Все финансы", callback_data="adm:f")
        builder.adjust(1)
        
        success_text = (
            "✅ <b>Комиссия одобрена!</b>\n\n"
            f"🆔 Комиссия #{commission_id}\n"
            f"💵 Сумма: {default_amount} ₽\n"
            f"👤 Одобрил: {staff.full_name or 'Администратор'}\n\n"
            "Что дальше?"
        )
        
        await cq.message.edit_text(
            success_text,
            reply_markup=builder.as_markup(),
            parse_mode="HTML",
        )
        await _safe_answer(cq, "✅ Готово!")
    else:
        await _safe_answer(cq, "❌ Ошибка при одобрении", show_alert=True)


# CR-2025-10-03-011: Переход к ручному вводу суммы
@router.callback_query(
    F.data.startswith("adm:f:cm:editamt:"),
    StaffRoleFilter({StaffRole.GLOBAL_ADMIN, StaffRole.CITY_ADMIN}),
)
async def cb_finance_edit_amount(cq: CallbackQuery, staff: StaffUser, state: FSMContext) -> None:
    """Enter custom amount for approval."""
    parts = cq.data.split(":")
    commission_id = int(parts[4])
    
    data = await state.get_data()
    default_amount = data.get("default_amount", "0")
    
    await state.set_state(FinanceActionFSM.approve_amount)
    
    kb = InlineKeyboardBuilder()
    kb.button(text="❌ Отмена", callback_data=f"adm:f:cm:card:{commission_id}")
    
    await cq.message.edit_text(
        f"<b>Введите сумму оплаты:</b>\n"
        f"По умолчанию: {default_amount} ₽\n\n"
        f"Например: <code>3000</code> или <code>3250.50</code>",
        reply_markup=kb.as_markup(),
    )
    await _safe_answer(cq)


@router.callback_query(
    F.data.startswith("adm:f:cm"),
    StaffRoleFilter({StaffRole.GLOBAL_ADMIN, StaffRole.CITY_ADMIN}),
)
async def cb_finance_card(cq: CallbackQuery, staff: StaffUser, state: FSMContext) -> None:
    from decimal import Decimal
    parts = cq.data.split(":")
    # parts = ['adm', 'f', 'cm', 'card', '14'] для adm:f:cm:card:14
    if len(parts) < 5:
        await _safe_answer(cq, "Некорректный callback", show_alert=True)
        return
    action = parts[3]  # 'card', 'open', 'ok', 'rej', 'blk'
    commission_id = int(parts[4])  # ID комиссии
    finance_service = _finance_service(cq.message.bot)
    detail = await finance_service.get_commission_detail(commission_id)
    if not detail:
        await _safe_answer(cq, "  .", show_alert=True)
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
        await _safe_answer(cq)
        return

    if action == "open":
        if not detail.attachments:
            await _safe_answer(cq, " .", show_alert=True)
            return
        for attachment in detail.attachments:
            try:
                file_type = (attachment.file_type or "").upper()
                if file_type == "PHOTO":
                    await cq.message.answer_photo(attachment.file_id, caption=attachment.caption)
                else:
                    await cq.message.answer_document(attachment.file_id, caption=attachment.caption)
            except TelegramBadRequest:
                await cq.message.answer("    .")
        await _safe_answer(cq)
        return

    if action == "ok":
        # CR-2025-10-03-011: Красивый UI для подтверждения оплаты
        await state.update_data(
            commission_id=commission_id,
            segment=segment,
            page=page,
            default_amount=f"{detail.amount:.2f}",
            source_chat_id=cq.message.chat.id,
            source_message_id=cq.message.message_id,
        )
        
        # Показываем кнопки для быстрого одобрения
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        kb = InlineKeyboardBuilder()
        kb.button(text=f"✅ Подтвердить {detail.amount:.2f} ₽", callback_data=f"adm:f:cm:approve:{commission_id}")
        kb.button(text="📝 Изменить сумму", callback_data=f"adm:f:cm:editamt:{commission_id}")
        kb.button(text="❌ Отмена", callback_data=f"adm:f:cm:card:{commission_id}")
        kb.adjust(1)
        
        await cq.message.edit_text(
            f"{text_body}\n\n<b>Подтвердить оплату?</b>",
            reply_markup=kb.as_markup(),
            disable_web_page_preview=True,
        )
        await _safe_answer(cq)
        return

    if action == "blk":
        ok = await finance_service.block_master_for_overdue(
            detail.master_id or 0,
            by_staff_id=staff.id,
        )
        await _safe_answer(
            cq,
            " ." if ok else "   .",
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
        
        # CR-2025-10-03-011: Красивый UI для отклонения
        kb = InlineKeyboardBuilder()
        kb.button(text="❌ Отмена", callback_data=f"adm:f:cm:card:{commission_id}")
        
        await cq.message.edit_text(
            f"{text_body}\n\n"
            f"<b>❌ Отклонить комиссию</b>\n\n"
            f"Укажите причину отклонения (минимум 3 символа):",
            reply_markup=kb.as_markup(),
        )
        await _safe_answer(cq)
        return

    await _safe_answer(cq)


@router.message(StateFilter(FinanceActionFSM.reject_reason))
async def finance_reject_reason(msg: Message, staff: StaffUser, state: FSMContext) -> None:
    reason = (msg.text or "").strip()
    
    # Обработка отмены
    if reason.lower() == "/cancel":
        await state.clear()
        await msg.answer("❌ Отменено.")
        return
    
    # CR-2025-10-03-FIX: Validate staff.id before database operations
    if not staff or staff.id is None or staff.id <= 0:
        await state.clear()
        await msg.answer("❌ Ошибка: некорректный ID персонала")
        return
    
    if len(reason) < 3:
        await msg.answer("❌ Причина слишком короткая (минимум 3 символа).")
        return

    data = await state.get_data()
    commission_id = data.get("commission_id")
    segment = data.get("segment", "aw")
    page = int(data.get("page", 1))
    source_chat_id = data.get("source_chat_id")
    source_message_id = data.get("source_message_id")

    if not commission_id:
        await state.clear()
        await msg.answer("❌ Ошибка: комиссия не найдена.")
        return

    finance_service = _finance_service(msg.bot)
    ok = await finance_service.reject(int(commission_id), reason=reason, by_staff_id=staff.id)
    await state.clear()
    
    if ok:
        live_log.push("finance", f"commission#{commission_id} rejected by staff {staff.id}")
        
        # CR-2025-10-03-014: Красивое сообщение об отклонении
        builder = InlineKeyboardBuilder()
        builder.button(text="📋 К списку ожидающих", callback_data="adm:f:aw:1")
        builder.button(text="💰 Все финансы", callback_data="adm:f")
        builder.adjust(1)
        
        reject_text = (
            "❌ <b>Комиссия отклонена</b>\n\n"
            f"🆔 Комиссия #{commission_id}\n"
            f"📝 Причина: {html.escape(reason)}\n"
            f"👤 Отклонил: {staff.full_name or 'Администратор'}\n\n"
            "Что дальше?"
        )
        
        await msg.answer(
            reject_text,
            reply_markup=builder.as_markup(),
            parse_mode="HTML",
        )
    else:
        await msg.answer("❌ Ошибка при отклонении комиссии.")


@router.message(StateFilter(FinanceActionFSM.approve_amount))
async def finance_approve_amount(msg: Message, staff: StaffUser, state: FSMContext) -> None:
    from decimal import Decimal
    
    # CR-2025-10-03-FIX: Validate staff.id before database operations
    if not staff or staff.id is None or staff.id <= 0:
        await state.clear()
        await msg.answer("❌ Ошибка: некорректный ID персонала")
        return
    
    data = await state.get_data()
    commission_id = data.get("commission_id")
    if not commission_id:
        await state.clear()
        await msg.answer("❌ Ошибка: комиссия не найдена.")
        return

    segment = data.get("segment", "aw")
    page = int(data.get("page", 1))
    source_chat_id = data.get("source_chat_id")
    source_message_id = data.get("source_message_id")

    text_value = (msg.text or "").strip()
    if text_value.lower() == "/cancel":
        await state.clear()
        if source_chat_id and source_message_id:
            proxy = _MessageEditProxy(msg.bot, source_chat_id, source_message_id)
            await _render_finance_segment(proxy, staff, segment, page, state)
        await msg.answer("❌ Отменено.")
        return

    # Парсим сумму
    normalized = text_value.replace(",", ".").replace("₽", "").replace(" ", "").strip()
    if not re.fullmatch(r"^\d{1,7}(?:\.\d{1,2})?$", normalized):
        await msg.answer(
            "❌ Неверный формат суммы.\n"
            "Пример: <code>3000</code> или <code>3250.50</code>"
        )
        return
    amount = Decimal(normalized)

    finance_service = _finance_service(msg.bot)
    ok = await finance_service.approve(int(commission_id), paid_amount=amount, by_staff_id=staff.id)
    await state.clear()
    
    if ok:
        live_log.push("finance", f"commission#{commission_id} approved by staff {staff.id} amount={amount}")
        
        # CR-2025-10-03-014: Красивое сообщение об успехе
        builder = InlineKeyboardBuilder()
        builder.button(text="📋 К списку ожидающих", callback_data="adm:f:aw:1")
        builder.button(text="💰 Все финансы", callback_data="adm:f")
        builder.adjust(1)
        
        success_text = (
            "✅ <b>Комиссия одобрена!</b>\n\n"
            f"🆔 Комиссия #{commission_id}\n"
            f"💵 Сумма: {amount} ₽\n"
            f"👤 Одобрил: {staff.full_name or 'Администратор'}\n\n"
            "Что дальше?"
        )
        
        await msg.answer(
            success_text,
            reply_markup=builder.as_markup(),
            parse_mode="HTML",
        )
    else:
        await msg.answer("❌ Ошибка при одобрении комиссии.")
