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
