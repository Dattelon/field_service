from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from field_service.db import models as m
from field_service.services import notifications_watcher


class _FailingBot:
    def __init__(self, message: str = "boom") -> None:
        self.message = message
        self.calls = 0

    async def send_message(self, *args, **kwargs):  # type: ignore[override]
        self.calls += 1
        raise RuntimeError(self.message)


class _AlwaysFailingBot(_FailingBot):
    pass


class _SuccessfulBot:
    def __init__(self) -> None:
        self.calls = 0

    async def send_message(self, *args, **kwargs):  # type: ignore[override]
        self.calls += 1
        return None


@pytest.mark.asyncio
async def test_notification_failure_keeps_record_unprocessed(async_session: AsyncSession, monkeypatch):
    master = m.masters(full_name="Test Master", tg_user_id=123456)
    async_session.add(master)
    await async_session.commit()

    notification = m.notifications_outbox(
        master_id=master.id,
        event="test",
        payload={"message": "hello"},
    )
    async_session.add(notification)
    await async_session.commit()

    session_factory = async_sessionmaker(
        bind=async_session.bind,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    monkeypatch.setattr(notifications_watcher, "SessionLocal", session_factory)

    bot = _FailingBot()
    await notifications_watcher._drain_outbox_once(bot)

    refreshed = await async_session.get(m.notifications_outbox, notification.id)
    assert refreshed is not None
    assert refreshed.processed_at is None
    assert refreshed.attempt_count == 1
    assert refreshed.last_error is not None and "boom" in refreshed.last_error
    assert bot.calls == 1


@pytest.mark.asyncio
async def test_notification_reaches_max_attempts(async_session: AsyncSession, monkeypatch):
    master = m.masters(full_name="Test Master", tg_user_id=123456)
    async_session.add(master)
    await async_session.commit()

    notification = m.notifications_outbox(
        master_id=master.id,
        event="test",
        payload={"message": "hello"},
    )
    async_session.add(notification)
    await async_session.commit()

    session_factory = async_sessionmaker(
        bind=async_session.bind,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    monkeypatch.setattr(notifications_watcher, "SessionLocal", session_factory)

    bot = _AlwaysFailingBot()
    for _ in range(notifications_watcher.MAX_SEND_ATTEMPTS):
        await notifications_watcher._drain_outbox_once(bot)

    refreshed = await async_session.get(m.notifications_outbox, notification.id)
    assert refreshed is not None
    assert refreshed.processed_at is not None
    assert refreshed.attempt_count == notifications_watcher.MAX_SEND_ATTEMPTS
    assert refreshed.last_error is not None


@pytest.mark.asyncio
async def test_notification_success_clears_error(async_session: AsyncSession, monkeypatch):
    master = m.masters(full_name="Test Master", tg_user_id=123456)
    async_session.add(master)
    await async_session.commit()

    notification = m.notifications_outbox(
        master_id=master.id,
        event="test",
        payload={"message": "hello"},
        attempt_count=2,
        last_error="boom",
    )
    async_session.add(notification)
    await async_session.commit()

    session_factory = async_sessionmaker(
        bind=async_session.bind,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    monkeypatch.setattr(notifications_watcher, "SessionLocal", session_factory)

    bot = _SuccessfulBot()
    await notifications_watcher._drain_outbox_once(bot)

    refreshed = await async_session.get(m.notifications_outbox, notification.id)
    assert refreshed is not None
    assert refreshed.processed_at is not None
    assert refreshed.attempt_count == 3
    assert refreshed.last_error is None
