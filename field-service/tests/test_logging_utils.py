import pytest

from field_service.infra import notify


class DummyBot:
    def __init__(self) -> None:
        self.calls: list[tuple[int, str, dict]] = []

    async def send_message(self, chat_id, text, **kwargs):
        self.calls.append((chat_id, text, kwargs))
        return True


@pytest.mark.asyncio
async def test_send_log_trims_long_messages():
    bot = DummyBot()
    await notify.send_log(bot, "x" * 5000, chat_id=123)
    assert bot.calls
    chat_id, text, _ = bot.calls[0]
    assert chat_id == 123
    assert len(text) == 4096
    assert text.endswith("...")


@pytest.mark.asyncio
async def test_send_alert_appends_exception_details():
    bot = DummyBot()
    try:
        raise RuntimeError("boom")
    except RuntimeError as exc:
        await notify.send_alert(bot, "alert", chat_id=77, exc=exc)

    assert bot.calls
    _, text, _ = bot.calls[0]
    assert "RuntimeError: boom" in text
    assert "Traceback:" in text
