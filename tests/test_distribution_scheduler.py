from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo
from unittest.mock import AsyncMock

import pytest

from field_service.db import models as m
from field_service.services import distribution_scheduler as sched


@pytest.mark.asyncio
async def test_wake_deferred_orders_promotes_at_start(async_session, monkeypatch):
    await async_session.execute(
        m.cities.__table__.insert().values(id=1, name="Test City", is_active=True)
    )
    await async_session.execute(
        m.orders.__table__.insert().values(
            id=100,
            city_id=1,
            status=m.OrderStatus.DEFERRED,
            scheduled_date=datetime(2025, 9, 15, tzinfo=timezone.utc).date(),
        )
    )
    await async_session.commit()

    monkeypatch.setattr(
        sched,
        "_workday_window",
        AsyncMock(return_value=(time(10, 0), time(20, 0))),
    )
    monkeypatch.setattr(
        sched,
        "_city_timezone",
        AsyncMock(return_value=ZoneInfo("UTC")),
    )
    messages: list[str] = []
    monkeypatch.setattr(sched, "_dist_log", lambda msg, level='INFO': messages.append(msg))
    sched.DEFERRED_LOGGED.clear()

    now_utc = datetime(2025, 9, 15, 10, 0, tzinfo=timezone.utc)
    awakened = await sched._wake_deferred_orders(async_session, now_utc=now_utc)

    assert awakened == [(100, datetime(2025, 9, 15, 10, 0, tzinfo=ZoneInfo("UTC")))]
    order = await async_session.get(m.orders, 100)
    assert order.status == m.OrderStatus.SEARCHING

    history_rows = await async_session.execute(
        m.order_status_history.__table__.select().where(
            m.order_status_history.order_id == 100
        )
    )
    history = history_rows.mappings().all()
    assert history and history[-1]["to_status"] == m.OrderStatus.SEARCHING
    assert 100 not in sched.DEFERRED_LOGGED
    assert messages == []


@pytest.mark.asyncio
async def test_wake_deferred_orders_logs_until_start_once(async_session, monkeypatch):
    await async_session.execute(
        m.cities.__table__.insert().values(id=2, name="Another City", is_active=True)
    )
    await async_session.execute(
        m.orders.__table__.insert().values(
            id=200,
            city_id=2,
            status=m.OrderStatus.DEFERRED,
            scheduled_date=datetime(2025, 9, 15, tzinfo=timezone.utc).date(),
        )
    )
    await async_session.commit()

    monkeypatch.setattr(
        sched,
        "_workday_window",
        AsyncMock(return_value=(time(10, 0), time(20, 0))),
    )
    monkeypatch.setattr(
        sched,
        "_city_timezone",
        AsyncMock(return_value=ZoneInfo("UTC")),
    )
    log_messages: list[str] = []
    monkeypatch.setattr(sched, "_dist_log", lambda msg, level='INFO': log_messages.append(msg))
    sched.DEFERRED_LOGGED.clear()

    before_start = datetime(2025, 9, 15, 8, 0, tzinfo=timezone.utc)
    awakened = await sched._wake_deferred_orders(async_session, now_utc=before_start)
    assert awakened == []
    assert log_messages and "deferred until" in log_messages[-1]
    assert 200 in sched.DEFERRED_LOGGED

    log_messages.clear()
    awakened = await sched._wake_deferred_orders(async_session, now_utc=before_start)
    assert awakened == []
    assert log_messages == []

    at_start = datetime(2025, 9, 15, 10, 0, tzinfo=timezone.utc)
    awakened = await sched._wake_deferred_orders(async_session, now_utc=at_start)
    assert awakened
    assert 200 not in sched.DEFERRED_LOGGED


class _DummySessionContext:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_tick_once_logs_awakened(monkeypatch, async_session):
    log_messages: list[str] = []
    monkeypatch.setattr(sched, "_dist_log", lambda msg, level='INFO': log_messages.append(msg))

    monkeypatch.setattr(sched, "_try_advisory_lock", AsyncMock(return_value=True))
    monkeypatch.setattr(sched, "_db_now", AsyncMock(return_value=datetime(2025, 9, 15, 10, 0, tzinfo=timezone.utc)))
    monkeypatch.setattr(
        sched,
        "_wake_deferred_orders",
        AsyncMock(return_value=[(321, datetime(2025, 9, 15, 10, 0, tzinfo=timezone.utc))]),
    )
    monkeypatch.setattr(sched, "_fetch_orders_for_distribution", AsyncMock(return_value=[]))
    monkeypatch.setattr(sched, "SessionLocal", lambda: _DummySessionContext(async_session))

    cfg = sched.DistConfig(tick_seconds=30, sla_seconds=120, rounds=2, top_log_n=5, to_admin_after_min=10)
    await sched.tick_once(cfg, bot=None, alerts_chat_id=None)

    assert any("deferred->searching order=321" in msg for msg in log_messages)
