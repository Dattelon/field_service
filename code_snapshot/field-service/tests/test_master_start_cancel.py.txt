from __future__ import annotations

import types

import pytest

from field_service.bots.master_bot.handlers import start as master_start


class _StubState:
    def __init__(self) -> None:
        self.cleared = False

    async def clear(self) -> None:
        self.cleared = True


@pytest.mark.asyncio
async def test_master_cancel_clears_state(monkeypatch):
    state = _StubState()
    called = types.SimpleNamespace(flag=False)

    async def fake_render(message, master):
        called.flag = True

    monkeypatch.setattr(master_start, "_render_start", fake_render)

    message = object()
    master = object()

    await master_start.handle_cancel(message, state, master)

    assert state.cleared is True
    assert called.flag is True
