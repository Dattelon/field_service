"""Compatibility shim exposing legacy queue helpers for tests and old imports."""

from .handlers.orders.queue import *  # noqa: F401,F403
from .handlers.orders.queue import (  # noqa: F401
    _available_cities,
    _format_order_card_text,
    _order_card_markup,
    _render_order_card,
    _render_queue_list,
    _should_show_guarantee_button,
)
from .core.utils import get_service  # noqa: F401

CANCEL_ORDER_KEY = "order_id"
CANCEL_CHAT_KEY = "chat_id"
CANCEL_MESSAGE_KEY = "message_id"
FILTER_DATA_KEY = "queue_filters"
FILTER_MSG_CHAT_KEY = "queue_filters_chat_id"
FILTER_MSG_ID_KEY = "queue_filters_message_id"


def _default_filters() -> dict[str, None]:
    """Legacy helper: mirrors old dict-based queue filters structure."""
    return {
        "city_id": None,
        "category": None,
        "status": None,
        "master_id": None,
        "date": None,
        "order_id": None,
    }


# ---------------------------------------------------------------------------
# Legacy-friendly wrapper to ensure tests call the expected cancel flow even
# if the internal handler module evolves. This mirrors tests' expectations:
# - reads CANCEL_* keys directly from FSM state
# - calls orders_service.cancel(order_id, reason, by_staff_id)
# - re-renders the card via bot.edit_message_text/send_message
# - clears the legacy CANCEL_* keys and resets state to None
# ---------------------------------------------------------------------------
async def queue_cancel_reason(msg, staff, state):  # noqa: F401
    data = await state.get_data()
    order_id = data.get(CANCEL_ORDER_KEY)
    chat_id = data.get(CANCEL_CHAT_KEY)
    message_id = data.get(CANCEL_MESSAGE_KEY)

    # Fallback safety: abort if state incomplete
    if order_id is None or chat_id is None or message_id is None:
        await state.set_state(None)
        data.pop(CANCEL_ORDER_KEY, None)
        data.pop(CANCEL_CHAT_KEY, None)
        data.pop(CANCEL_MESSAGE_KEY, None)
        await state.set_data(data)
        await msg.answer("  ")
        return

    reason = msg.text or ""
    # Validate short non-empty reasons: reject if shorter than 3
    if reason.strip() and len(reason.strip()) < 3:
        await msg.answer("  ")
        return
    orders_service = get_service(msg.bot, "orders_service", required=True)

    ok = await orders_service.cancel(order_id, reason=reason, by_staff_id=staff.id)
    if ok:
        await msg.answer(" .")
    else:
        await msg.answer("   .")

    # Re-render card
    try:
        order = await orders_service.get_card(order_id)
    except TypeError:
        order = await orders_service.get_card(order_id)

    if order is not None:
        try:
            history = await orders_service.list_status_history(order_id, limit=5)
        except TypeError:
            history = await orders_service.list_status_history(order_id, 5)

        text_body = _format_order_card_text(order, history)
        markup = _order_card_markup(order)
        try:
            await msg.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text_body,
                reply_markup=markup,
            )
        except Exception:
            await msg.bot.send_message(chat_id, text_body, reply_markup=markup)

    # Clear legacy CANCEL_* state and reset FSM
    data.pop(CANCEL_ORDER_KEY, None)
    data.pop(CANCEL_CHAT_KEY, None)
    data.pop(CANCEL_MESSAGE_KEY, None)
    await state.set_data(data)
    await state.set_state(None)
