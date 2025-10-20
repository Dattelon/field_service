from __future__ import annotations

import asyncio
from datetime import timedelta

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from field_service.bots.common import FSMTimeoutConfig, FSMTimeoutMiddleware


class _DummyEvent:
    pass


@pytest.mark.asyncio
async def test_fsm_timeout_clears_state_and_calls_callback():
    storage = MemoryStorage()
    state = FSMContext(storage=storage, key=StorageKey(bot_id=1, chat_id=1, user_id=1))
    await state.set_state(State('test'))

    triggered = asyncio.Event()

    async def _on_timeout(ctx: FSMContext) -> None:
        triggered.set()

    middleware = FSMTimeoutMiddleware(
        FSMTimeoutConfig(timeout=timedelta(milliseconds=20), callback=_on_timeout)
    )

    async def handler(event, data):
        return None

    await middleware(handler, _DummyEvent(), {"state": state})
    await asyncio.sleep(0.05)

    assert await state.get_state() is None
    assert triggered.is_set()


@pytest.mark.asyncio
async def test_fsm_timeout_resets_on_activity():
    storage = MemoryStorage()
    state = FSMContext(storage=storage, key=StorageKey(bot_id=1, chat_id=1, user_id=1))
    await state.set_state(State('test'))

    counter = 0

    async def _on_timeout(ctx: FSMContext) -> None:
        nonlocal counter
        counter += 1

    middleware = FSMTimeoutMiddleware(
        FSMTimeoutConfig(timeout=timedelta(milliseconds=40), callback=_on_timeout)
    )

    async def handler(event, data):
        return None

    # First activity schedules timer
    await middleware(handler, _DummyEvent(), {"state": state})
    await asyncio.sleep(0.02)

    # Another activity should reset the timer
    await middleware(handler, _DummyEvent(), {"state": state})
    await asyncio.sleep(0.03)

    assert counter == 0

    await asyncio.sleep(0.05)
    assert counter == 1
    assert await state.get_state() is None
