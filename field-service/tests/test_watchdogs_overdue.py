import asyncio

import pytest

from field_service.services import watchdogs
from field_service.services.commission_service import CommissionOverdueEvent


class DummyBot:
    def __init__(self) -> None:
        self.calls: list[tuple[int, str, dict]] = []

    async def send_message(self, chat_id, text, **kwargs):
        self.calls.append((chat_id, text, kwargs))
        return True


class DummySession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def commit(self):
        return None


@pytest.mark.asyncio
async def test_watchdog_triggers_alert(monkeypatch):
    bot = DummyBot()

    event = CommissionOverdueEvent(
        commission_id=5,
        order_id=12,
        master_id=77,
        master_full_name="Иван Петров",
    )

    async def fake_apply(session, now):
        return [event]

    monkeypatch.setattr(watchdogs, "SessionLocal", lambda: DummySession())
    monkeypatch.setattr(watchdogs, "apply_overdue_commissions", fake_apply)
    monkeypatch.setattr(watchdogs.live_log, "push", lambda *args, **kwargs: None)

    await watchdogs.watchdog_commissions_overdue(
        bot,
        alerts_chat_id=999,
        interval_seconds=0,
        iterations=1,
    )

    assert bot.calls
    chat_id, text, payload = bot.calls[0]
    assert chat_id == 999
    assert "🚫 Просрочка комиссии #5" in text
    assert payload["reply_markup"].inline_keyboard[0][0].callback_data == "adm:f:cm:5"
