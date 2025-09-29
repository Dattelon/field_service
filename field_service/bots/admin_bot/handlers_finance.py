from __future__ import annotations

import html
import re
from typing import Any, Iterable, Optional

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramNotFound
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from field_service.services import live_log, owner_requisites_service

from .dto import StaffRole, StaffUser, WaitPayRecipient
from .filters import StaffRoleFilter
from .keyboards import finance_menu, owner_pay_actions_keyboard, owner_pay_edit_keyboard
from .states import OwnerPayEditFSM
from .utils import get_service


router = Router(name="admin_finance")

PAYMENT_METHOD_LABELS = {
    "card": "",
    "sbp": "",
    "cash": "",
}

_METHOD_ALIASES = {
    "card": "card",
    "": "card",
    "": "card",
    "": "card",
    "": "card",
    "sbp": "sbp",
    "": "sbp",
    "  ": "sbp",
    "qr": "sbp",
    "": "cash",
    "": "cash",
    "": "cash",
    "cash": "cash",
}

_OWNER_FIELDS = {
    "methods": " ",
    "card_number": " ",
    "card_holder": "",
    "card_bank": " ",
    "sbp_phone": "  ",
    "sbp_bank": "  ",
    "sbp_qr_file_id": "QR- ",
    "other_text": " ",
    "comment_template": " ",
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
        await bot_message.answer("  .")
    return (bot_message.chat.id, bot_message.message_id)


def _format_snapshot_text(snapshot: dict[str, Any], *, for_staff: bool) -> str:
    data = owner_requisites_service.ensure_schema(snapshot)
    methods = _format_methods(data.get("methods") or [])
    lines: list[str] = []
    if for_staff:
        lines.append("<b>  </b>")
    else:
        lines.append("<b>   </b>")
    lines.append(f" : {methods}")

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
        lines.append("<b></b>")
        lines.append(html.escape(other_text))
    if comment_template:
        lines.append("")
        lines.append("<b>  </b>")
        lines.append(html.escape(comment_template))

    if not for_staff:
        lines.append("")
        lines.append(
            "      , , , ."
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
        block.append("<b>  </b>")
        if card_number:
            block.append(f": {html.escape(card_number)}")
        if card_holder:
            block.append(f": {html.escape(card_holder)}")
        if card_bank:
            block.append(f": {html.escape(card_bank)}")
    return block


def _format_sbp_block(data: dict[str, Any], *, include_qr: bool) -> list[str]:
    phone = data.get("sbp_phone") or ""
    bank = data.get("sbp_bank") or ""
    qr = data.get("sbp_qr_file_id") or ""
    block: list[str] = []
    if phone or bank or (include_qr and qr):
        block.append("<b>  </b>")
        if phone:
            block.append(f": {html.escape(phone)}")
        if bank:
            block.append(f": {html.escape(bank)}")
        if include_qr:
            block.append("QR-: " + ("" if qr else " "))
    return block


def _parse_methods_payload(text: str) -> list[str]:
    cleaned = text.strip()
    if not cleaned or cleaned in {"-", "", "none", ""}:
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
            raise ValueError(f"  : {piece}")
        if alias not in owner_requisites_service.ALLOWED_METHODS:
            raise ValueError(f"   : {piece}")
        if alias not in result:
            result.append(alias)
    return result


def _extract_field_value(field: str, message: Message) -> Any:
    if field == "methods":
        if not message.text:
            raise ValueError("    .")
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
        await cq.answer()
        return
    origin = await _render_owner_snapshot(cq.message, staff)
    if origin:
        await state.update_data(owner_pay_origin=origin)
    await cq.answer()


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
        await cq.answer()
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
    await cq.answer()


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
        await cq.answer()
        return
    field = cq.data.split(":", maxsplit=3)[-1]
    if field not in _OWNER_FIELDS:
        await cq.answer(" ", show_alert=True)
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
    await cq.answer()


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
        await cq.answer()
        return
    finance_service = _finance_service(cq.message.bot)
    settings_service = _settings_service(cq.message.bot)
    snapshot = await settings_service.get_owner_pay_snapshot()
    recipients = await finance_service.list_wait_pay_recipients()
    if not recipients:
        await cq.answer("    ", show_alert=True)
        return
    sent, failed = await _broadcast_owner_requisites(cq.message.bot, recipients, snapshot)
    live_log.push(
        "finance",
        f"owner_pay broadcast by staff {staff.id}: sent={sent} failed={failed}",
    )
    await cq.answer(" ")
    summary = f"  {sent} ."
    if failed:
        summary += f"   : {failed}."
    await cq.message.answer(summary, reply_markup=finance_menu(staff))
    await _rerender_origin(cq.message.bot, staff, (cq.message.chat.id, cq.message.message_id))

