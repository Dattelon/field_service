"""
P2.2: Typed state management for admin queue filters and actions.

 dataclasses  type-safe  FSM state   .
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import date
from typing import Optional

from aiogram.fsm.context import FSMContext

from ..core.dto import OrderCategory, OrderStatus


# =============================================================================
# DATACLASSES
# =============================================================================

@dataclass
class QueueFilters:
    """     ."""
    
    city_id: Optional[int] = None
    category: Optional[OrderCategory] = None
    status: Optional[OrderStatus] = None
    master_id: Optional[int] = None
    date: Optional[date] = None
    order_id: Optional[int] = None  # P1:   ID 
    
    def to_dict(self) -> dict[str, Optional[str | int]]:
        """    FSM state."""
        return {
            "city_id": self.city_id,
            "category": self.category.value if self.category else None,
            "status": self.status.value if self.status else None,
            "master_id": self.master_id,
            "date": self.date.isoformat() if self.date else None,
            "order_id": self.order_id,  # P1:   ID
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Optional[str | int]]) -> QueueFilters:
        """  FSM state."""
        city_id = data.get("city_id")
        category_value = data.get("category")
        status_value = data.get("status")
        master_id = data.get("master_id")
        date_value = data.get("date")
        order_id = data.get("order_id")  # P1:   ID
        
        # Parse enums
        category = None
        if category_value:
            try:
                category = OrderCategory(category_value)
            except ValueError:
                pass
        
        status = None
        if status_value:
            try:
                status = OrderStatus(status_value)
            except ValueError:
                pass
        
        # Parse date
        parsed_date = None
        if date_value:
            try:
                parsed_date = date.fromisoformat(str(date_value))
            except (ValueError, TypeError):
                pass
        
        return cls(
            city_id=int(city_id) if city_id else None,
            category=category,
            status=status,
            master_id=int(master_id) if master_id else None,
            date=parsed_date,
            order_id=int(order_id) if order_id else None,  # P1:   ID
        )


@dataclass
class QueueFiltersMessage:
    """     ( )."""
    
    chat_id: int
    message_id: int
    
    def to_dict(self) -> dict[str, int]:
        return {"chat_id": self.chat_id, "message_id": self.message_id}
    
    @classmethod
    def from_dict(cls, data: dict[str, int]) -> Optional[QueueFiltersMessage]:
        chat_id = data.get("chat_id")
        message_id = data.get("message_id")
        if chat_id is None or message_id is None:
            return None
        return cls(chat_id=chat_id, message_id=message_id)


@dataclass
class CancelOrderState:
    """State    ."""
    
    order_id: int
    chat_id: int
    message_id: int
    
    def to_dict(self) -> dict[str, int]:
        return {
            "order_id": self.order_id,
            "chat_id": self.chat_id,
            "message_id": self.message_id,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, int]) -> Optional[CancelOrderState]:
        order_id = data.get("order_id")
        chat_id = data.get("chat_id")
        message_id = data.get("message_id")
        if order_id is None or chat_id is None or message_id is None:
            return None
        return cls(order_id=order_id, chat_id=chat_id, message_id=message_id)


# =============================================================================
# STATE KEYS (    FSM)
# =============================================================================

_QUEUE_FILTERS_KEY = "queue:filters"
_QUEUE_FILTERS_MSG_KEY = "queue:filters:msg"
_QUEUE_CANCEL_KEY = "queue:cancel"


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

async def load_queue_filters(state: FSMContext) -> QueueFilters:
    """    FSM state."""
    data = await state.get_data()
    stored = data.get(_QUEUE_FILTERS_KEY)
    if not stored:
        # Default filters
        filters = QueueFilters()
        await save_queue_filters(state, filters)
        return filters
    return QueueFilters.from_dict(stored)


async def save_queue_filters(state: FSMContext, filters: QueueFilters) -> None:
    """    FSM state."""
    await state.update_data({_QUEUE_FILTERS_KEY: filters.to_dict()})


async def load_filters_message(state: FSMContext) -> Optional[QueueFiltersMessage]:
    """     ."""
    data = await state.get_data()
    stored = data.get(_QUEUE_FILTERS_MSG_KEY)
    if not stored:
        return None
    return QueueFiltersMessage.from_dict(stored)


async def save_filters_message(state: FSMContext, chat_id: int, message_id: int) -> None:
    """     ."""
    msg = QueueFiltersMessage(chat_id=chat_id, message_id=message_id)
    await state.update_data({_QUEUE_FILTERS_MSG_KEY: msg.to_dict()})


async def load_cancel_state(state: FSMContext) -> Optional[CancelOrderState]:
    """ state  ."""
    data = await state.get_data()
    stored = data.get(_QUEUE_CANCEL_KEY)
    if stored:
        return CancelOrderState.from_dict(stored)
    # legacy fallback
    order_id = data.get("order_id")
    chat_id = data.get("chat_id")
    message_id = data.get("message_id")
    if order_id is None or chat_id is None or message_id is None:
        return None
    return CancelOrderState(order_id=order_id, chat_id=chat_id, message_id=message_id)


async def save_cancel_state(
    state: FSMContext,
    order_id: int,
    chat_id: int,
    message_id: int
) -> None:
    """ state  ."""
    cancel_state = CancelOrderState(
        order_id=order_id,
        chat_id=chat_id,
        message_id=message_id
    )
    await state.update_data({_QUEUE_CANCEL_KEY: cancel_state.to_dict()})
    # legacy compatibility keys
    await state.update_data(
        {
            "order_id": order_id,
            "chat_id": chat_id,
            "message_id": message_id,
        }
    )


async def clear_cancel_state(state: FSMContext) -> None:
    """ state  ."""
    current = await state.get_state()
    if current and current.startswith("QueueActionFSM:cancel_reason"):
        await state.set_state(None)
    
    data = await state.get_data()
    if _QUEUE_CANCEL_KEY in data:
        data.pop(_QUEUE_CANCEL_KEY)
    # remove legacy keys if present
    data.pop("order_id", None)
    data.pop("chat_id", None)
    data.pop("message_id", None)
    await state.set_data(data)
