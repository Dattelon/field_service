"""Legacy queue handlers compatibility exports.

Several unit tests and external scripts still import callbacks directly from
``field_service.bots.admin_bot.queue``.  The production bot migrated to a new
package layout, but we keep the historical implementation in the
``admin_bot.backup`` snapshot.  This module loads that snapshot dynamically so
existing imports continue to work without duplicating the entire legacy
implementation in source control.
"""
from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Dict, Iterable, Optional

from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from .core.dto import (
    OrderDetail,
    OrderStatusHistoryItem,
    StaffRole,
    StaffUser,
)
from .core.states import QueueActionFSM
from .utils.helpers import get_service

# Resolve the legacy file relative to this module.  The ``admin_bot.backup``
# directory sits alongside this package but uses a dot in its name, which
# prevents Python from discovering it as a standard package.  Loading it
# manually keeps the layout intact without altering ``sys.path`` globally.
_BASE_DIR = Path(__file__).resolve().parent
_LEGACY_PATH = _BASE_DIR.parent / "admin_bot.backup" / "queue.py"

if not _LEGACY_PATH.exists():  # pragma: no cover - defensive guard
    raise ImportError(f"Legacy queue module not found at {_LEGACY_PATH}")

_spec = importlib.util.spec_from_file_location(
    "field_service.bots.admin_bot._legacy_queue", _LEGACY_PATH
)
if _spec is None or _spec.loader is None:  # pragma: no cover - defensive guard
    raise ImportError(f"Unable to load legacy queue module from {_LEGACY_PATH}")

_legacy_queue = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_legacy_queue)

# Export every public attribute from the legacy module into this namespace so
# imports behave exactly as before.
_globals: Dict[str, object] = {
    name: value
    for name, value in vars(_legacy_queue).items()
    if not name.startswith("_")
}

globals().update(_globals)

__all__ = list(_globals)

# Keep a reference around for debugging and to avoid garbage collection.
legacy_module: ModuleType = _legacy_queue


# ---------------------------------------------------------------------------
# Compatibility overrides tailored for the lightweight unit-test environment.
# ---------------------------------------------------------------------------
CANCEL_ORDER_KEY = "queue:cancel:order_id"
CANCEL_CHAT_KEY = "queue:cancel:chat_id"
CANCEL_MESSAGE_KEY = "queue:cancel:message_id"

CANCEL_REASON_MIN = 3
CANCEL_REASON_MAX = 200

_ALERT_RETURN_OK = "   "
_ALERT_NO_ACCESS = "   "
_CANCEL_ABORT_TEXT = " ."
_CANCEL_SUCCESS_TEXT = " ."
_CANCEL_FAILURE_TEXT = "   ."
_CANCEL_REASON_TOO_SHORT = "  "


@dataclass(slots=True)
class _CancelState:
    order_id: int
    chat_id: int
    message_id: int


def _has_city_access(staff: StaffUser, city_id: Optional[int]) -> bool:
    if staff.role is StaffRole.GLOBAL_ADMIN:
        return True
    if city_id is None:
        return False
    return int(city_id) in getattr(staff, "city_ids", frozenset())


def _build_card_keyboard(order_id: int) -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()
    builder.button(text="↩️ Обновить", callback_data=f"adm:q:ret:{order_id}")
    builder.button(text="❌ Отменить", callback_data=f"adm:q:cnl:{order_id}")
    builder.adjust(1)
    return builder


def _format_order_card(
    order: OrderDetail, history: Iterable[OrderStatusHistoryItem]
) -> str:
    lines = [
        f"Заявка #{order.id}",
        f"Статус: {order.status}",
    ]
    if order.master_name:
        lines.append(f"Мастер: {order.master_name}")
    elif order.master_id:
        lines.append(f"Мастер: #{order.master_id}")
    else:
        lines.append("Мастер: не назначен")
    if order.timeslot_local:
        lines.append(f"Слот: {order.timeslot_local}")
    if order.city_name:
        lines.append(f"Город: {order.city_name}")
    if order.district_name:
        lines.append(f"Район: {order.district_name}")
    if order.description:
        lines.append("")
        lines.append(order.description)
    if history:
        lines.append("")
        lines.append("История статусов:")
        for item in history:
            lines.append(f"• {item.changed_at_local}: {item.to_status}")
    return "\n".join(lines)


async def _load_cancel_state(state: FSMContext) -> Optional[_CancelState]:
    data = await state.get_data()
    order_id = data.get(CANCEL_ORDER_KEY)
    chat_id = data.get(CANCEL_CHAT_KEY)
    message_id = data.get(CANCEL_MESSAGE_KEY)
    if order_id is None or chat_id is None or message_id is None:
        return None
    try:
        return _CancelState(int(order_id), int(chat_id), int(message_id))
    except (TypeError, ValueError):
        return None


async def _save_cancel_state(state: FSMContext, cancel_state: _CancelState) -> None:
    await state.update_data(
        {
            CANCEL_ORDER_KEY: cancel_state.order_id,
            CANCEL_CHAT_KEY: cancel_state.chat_id,
            CANCEL_MESSAGE_KEY: cancel_state.message_id,
        }
    )


async def _clear_cancel_state(state: FSMContext) -> None:
    data = await state.get_data()
    for key in (CANCEL_ORDER_KEY, CANCEL_CHAT_KEY, CANCEL_MESSAGE_KEY):
        data.pop(key, None)
    await state.set_data(data)
    await state.set_state(None)


async def cb_queue_cancel_start(
    cq: CallbackQuery, staff: StaffUser, state: FSMContext
) -> None:
    parts = cq.data.split(":")
    try:
        order_id = int(parts[3])
    except (IndexError, ValueError):
        await cq.answer(_ALERT_NO_ACCESS, show_alert=True)
        return

    orders_service = get_service(cq.message.bot, "orders_service")
    order = await orders_service.get_card(order_id)
    if not order or not _has_city_access(staff, getattr(order, "city_id", None)):
        await cq.answer(_ALERT_NO_ACCESS, show_alert=True)
        return

    await state.set_state(QueueActionFSM.cancel_reason)
    await _save_cancel_state(
        state,
        _CancelState(order_id=order_id, chat_id=cq.message.chat.id, message_id=cq.message.message_id),
    )

    builder = InlineKeyboardBuilder()
    builder.button(text="↩️ Назад", callback_data=f"adm:q:cnl:bk:{order_id}")
    builder.button(text="🏠 В меню", callback_data="adm:menu")
    builder.adjust(1)

    await cq.message.edit_text(
        "📝 Введите причину отмены заказа\n\n"
        f"Минимум {CANCEL_REASON_MIN} символов. Для выхода отправьте /cancel.",
        reply_markup=builder.as_markup(),
    )
    await cq.answer(_ALERT_RETURN_OK)


async def queue_cancel_reason(
    msg: Message, staff: StaffUser, state: FSMContext
) -> None:
    text_raw = msg.text or ""
    trimmed = text_raw.strip()
    if trimmed and len(trimmed) < CANCEL_REASON_MIN:
        await msg.answer(_CANCEL_REASON_TOO_SHORT)
        return

    cancel_state = await _load_cancel_state(state)
    if not cancel_state:
        await _clear_cancel_state(state)
        await msg.answer(_CANCEL_FAILURE_TEXT)
        return

    orders_service = get_service(msg.bot, "orders_service")
    order = await orders_service.get_card(cancel_state.order_id)
    if not order or not _has_city_access(staff, getattr(order, "city_id", None)):
        await _clear_cancel_state(state)
        await msg.answer(_CANCEL_FAILURE_TEXT)
        return

    ok = await orders_service.cancel(cancel_state.order_id, text_raw, by_staff_id=staff.id)
    await msg.answer(_CANCEL_SUCCESS_TEXT if ok else _CANCEL_FAILURE_TEXT)

    updated = await orders_service.get_card(cancel_state.order_id)
    history = await orders_service.list_status_history(cancel_state.order_id, limit=5)
    if updated:
        text = _format_order_card(updated, history)
        markup = _build_card_keyboard(cancel_state.order_id).as_markup()
        try:
            await msg.bot.edit_message_text(
                chat_id=cancel_state.chat_id,
                message_id=cancel_state.message_id,
                text=text,
                reply_markup=markup,
            )
        except TelegramBadRequest:
            await msg.bot.send_message(cancel_state.chat_id, text, reply_markup=markup)

    await _clear_cancel_state(state)


async def queue_cancel_abort(
    msg: Message, staff: StaffUser, state: FSMContext
) -> None:
    cancel_state = await _load_cancel_state(state)
    await msg.answer(_CANCEL_ABORT_TEXT)

    if not cancel_state:
        await _clear_cancel_state(state)
        return

    orders_service = get_service(msg.bot, "orders_service")
    order = await orders_service.get_card(cancel_state.order_id)
    if order and _has_city_access(staff, getattr(order, "city_id", None)):
        history = await orders_service.list_status_history(cancel_state.order_id, limit=5)
        text = _format_order_card(order, history)
        markup = _build_card_keyboard(cancel_state.order_id).as_markup()
        try:
            await msg.bot.edit_message_text(
                chat_id=cancel_state.chat_id,
                message_id=cancel_state.message_id,
                text=text,
                reply_markup=markup,
            )
        except TelegramBadRequest:
            await msg.bot.send_message(cancel_state.chat_id, text, reply_markup=markup)

    await _clear_cancel_state(state)


__all__.extend(
    [
        "CANCEL_ORDER_KEY",
        "CANCEL_CHAT_KEY",
        "CANCEL_MESSAGE_KEY",
        "CANCEL_REASON_MIN",
        "CANCEL_REASON_MAX",
        "cb_queue_cancel_start",
        "queue_cancel_reason",
        "queue_cancel_abort",
    ]
)
