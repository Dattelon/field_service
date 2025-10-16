"""
      .

       
      .
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from aiogram.fsm.context import FSMContext


@dataclass
class RetryContext:
    """   """

    callback_data: str
    timestamp: datetime
    attempt: int
    user_id: int
    chat_id: int
    message_id: int

    MAX_ATTEMPTS = 3

    def can_retry(self) -> bool:
        """  """
        return self.attempt < self.MAX_ATTEMPTS

    def to_dict(self) -> dict:
        """      FSM"""
        return {
            "callback_data": self.callback_data,
            "timestamp": self.timestamp.isoformat(),
            "attempt": self.attempt,
            "user_id": self.user_id,
            "chat_id": self.chat_id,
            "message_id": self.message_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> RetryContext:
        """  """
        return cls(
            callback_data=data["callback_data"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            attempt=data["attempt"],
            user_id=data["user_id"],
            chat_id=data["chat_id"],
            message_id=data["message_id"],
        )


async def save_retry_context(
    state: FSMContext,
    callback_data: str,
    user_id: int,
    chat_id: int,
    message_id: int,
    attempt: int = 1,
) -> None:
    """
        .

    Args:
        state: FSM 
        callback_data:  callback'  
        user_id: ID 
        chat_id: ID 
        message_id: ID 
        attempt:   (  1)
    """
    ctx = RetryContext(
        callback_data=callback_data,
        timestamp=datetime.now(timezone.utc),
        attempt=attempt,
        user_id=user_id,
        chat_id=chat_id,
        message_id=message_id,
    )
    await state.update_data(retry_context=ctx.to_dict())


async def load_retry_context(state: FSMContext) -> Optional[RetryContext]:
    """
        FSM.

    Args:
        state: FSM 

    Returns:
        RetryContext  None    
    """
    data = await state.get_data()
    retry_data = data.get("retry_context")
    if not retry_data:
        return None
    return RetryContext.from_dict(retry_data)


async def clear_retry_context(state: FSMContext) -> None:
    """
        FSM.

    Args:
        state: FSM 
    """
    data = await state.get_data()
    if "retry_context" in data:
        data.pop("retry_context")
        await state.set_data(data)
