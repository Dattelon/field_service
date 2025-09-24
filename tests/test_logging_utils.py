import asyncio
from contextlib import suppress

import pytest

from field_service.infra import logging_utils


class DummyBot:
    def __init__(self):
        self.calls = []
        self.fail_next = True

    async def send_message(self, chat_id, text, **kwargs):
        self.calls.append((chat_id, text, kwargs))
        if self.fail_next:
            self.fail_next = False
            raise RuntimeError("boom")
        return True


@pytest.mark.asyncio
async def test_heartbeat_survives_send_error(monkeypatch):
    bot = DummyBot()
    original_sleep = logging_utils.asyncio.sleep

    async def fake_sleep(interval):
        await original_sleep(0)

    monkeypatch.setattr(logging_utils.asyncio, "sleep", fake_sleep)

    task = logging_utils.start_heartbeat(bot, bot_name="TEST", interval_seconds=1, chat_id=123)
    try:
        # let a few iterations happen
        for _ in range(3):
            await original_sleep(0)
        assert len(bot.calls) >= 2
        assert bot.calls[0][0] == 123
        assert bot.calls[0][1].startswith("[TEST] Heartbeat OK")
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


@pytest.mark.asyncio
async def test_send_alert_uses_override_chat():
    bot = DummyBot()
    bot.fail_next = False
    await logging_utils.send_alert(bot, "ping", chat_id=999, reply_markup={"stub": True})
    assert bot.calls[0][0] == 999
    assert bot.calls[0][1] == "ping"
    assert bot.calls[0][2]["reply_markup"] == {"stub": True}
