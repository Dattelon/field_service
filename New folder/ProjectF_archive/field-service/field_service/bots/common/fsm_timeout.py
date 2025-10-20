from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Awaitable, Callable, Dict, Optional

from aiogram import BaseMiddleware
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.types import TelegramObject


@dataclass(slots=True)
class FSMTimeoutConfig:
    timeout: timedelta
    callback: Optional[Callable[[FSMContext], Awaitable[None]]] = None


class FSMTimeoutMiddleware(BaseMiddleware):
    """Reset FSM state after a period of inactivity."""

    def __init__(self, config: FSMTimeoutConfig) -> None:
        self._timeout_seconds = max(config.timeout.total_seconds(), 0.0)
        self._callback = config.callback
        self._tasks: Dict[str, asyncio.Task[None]] = {}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        state: Optional[FSMContext] = data.get("state")
        storage_key = self._storage_key(state) if state else None
        try:
            return await handler(event, data)
        finally:
            if not state or not storage_key:
                return
            current_state = await state.get_state()
            if current_state is None:
                self._cancel_task(storage_key)
                return
            self._schedule_cleanup(storage_key, state)

    def _storage_key(self, state: FSMContext) -> str:
        key: StorageKey = state.key
        return f"{key.bot_id}:{key.chat_id}:{key.user_id}"

    def _cancel_task(self, storage_key: str) -> None:
        task = self._tasks.pop(storage_key, None)
        if task:
            task.cancel()

    def _schedule_cleanup(self, storage_key: str, state: FSMContext) -> None:
        self._cancel_task(storage_key)
        self._tasks[storage_key] = asyncio.create_task(
            self._cleanup_later(storage_key, state)
        )

    async def _cleanup_later(self, storage_key: str, state: FSMContext) -> None:
        try:
            await asyncio.sleep(self._timeout_seconds)
            await state.clear()
            if self._callback:
                try:
                    await self._callback(state)
                except Exception:
                    # Callback is best-effort; swallow to avoid breaking polling loops.
                    pass
        except asyncio.CancelledError:
            return
        finally:
            self._tasks.pop(storage_key, None)
