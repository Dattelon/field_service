import asyncio
from contextlib import suppress

import pytest

from field_service.services import heartbeat


class DummyBot:
    def __init__(self) -> None:
        self.calls: list[tuple[int, str, dict]] = []

    async def send_message(self, chat_id, text, **kwargs):
        self.calls.append((chat_id, text, kwargs))
        return True


@pytest.mark.asyncio
async def test_run_heartbeat_sends_messages(monkeypatch):
    bot = DummyBot()

    original_sleep = asyncio.sleep

    async def fast_sleep(interval):
        await original_sleep(0)

    monkeypatch.setattr(heartbeat.asyncio, "sleep", fast_sleep)

    task = asyncio.create_task(
        heartbeat.run_heartbeat(bot, name="admin", chat_id=42, interval=1)
    )
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task

    assert bot.calls
    assert bot.calls[0][0] == 42
    assert bot.calls[0][1] == "heartbeat: admin alive"
