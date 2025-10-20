import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from field_service.bots.master_bot.handlers import orders
from field_service.bots.master_bot.states import CloseOrderStates
from field_service.db import models as m


def test_parse_offer_callback_payload_basic() -> None:
    assert orders._parse_offer_callback_payload("m:new:card:42", "card") == (42, 1)


def test_parse_offer_callback_payload_with_page() -> None:
    assert orders._parse_offer_callback_payload("m:new:acc:10:3", "acc") == (10, 3)


def test_parse_offer_callback_payload_invalid_page_defaults_to_one() -> None:
    assert orders._parse_offer_callback_payload("m:new:dec:77:0", "dec") == (77, 1)
    assert orders._parse_offer_callback_payload("m:new:dec:77:notanint", "dec") == (77, 1)


def test_parse_offer_callback_payload_rejects_wrong_action() -> None:
    with pytest.raises(ValueError):
        orders._parse_offer_callback_payload("m:new:card:5:2", "acc")


def test_parse_offer_callback_payload_rejects_bad_prefix() -> None:
    with pytest.raises(ValueError):
        orders._parse_offer_callback_payload("m:other:card:5", "card")


def test_parse_offer_callback_payload_rejects_non_numeric_order() -> None:
    with pytest.raises(ValueError):
        orders._parse_offer_callback_payload("m:new:card:abc", "card")



class _DummyState:
    def __init__(self):
        self.data: dict[str, object] = {}
        self.state = None

    async def update_data(self, **kwargs):
        self.data.update(kwargs)

    async def set_state(self, value):
        self.state = value

    async def clear(self):
        self.data.clear()
        self.state = None

    async def get_data(self):
        return dict(self.data)


@pytest.mark.asyncio
async def test_active_close_start_without_message(monkeypatch):
    order = SimpleNamespace(
        id=1,
        assigned_master_id=77,
        status=m.OrderStatus.WORKING,
        order_type=m.OrderType.NORMAL,
    )

    class _Session:
        async def get(self, model, order_id):
            assert model is m.orders
            assert order_id == 1
            return order

    state = _DummyState()
    session = _Session()
    bot = SimpleNamespace()
    callback = SimpleNamespace(
        data='m:act:cls:1',
        message=None,
        from_user=SimpleNamespace(id=501),
        bot=bot,
        id='cb-test',
    )
    master = SimpleNamespace(id=77)

    safe_answer = AsyncMock(return_value=None)
    safe_send = AsyncMock(return_value=None)
    monkeypatch.setattr(orders, 'safe_answer_callback', safe_answer)
    monkeypatch.setattr(orders, 'safe_send_message', safe_send)

    await orders.active_close_start(callback, state, session, master, bot)

    assert state.state == CloseOrderStates.amount
    assert state.data == {'close_order_id': 1, 'close_order_amount': None}
    safe_send.assert_awaited_once()
    args, kwargs = safe_send.await_args
    assert args == (callback.bot, 501, orders.CLOSE_AMOUNT_PROMPT)
    assert "reply_markup" in kwargs
    safe_answer.assert_awaited()


@pytest.mark.asyncio
async def test_active_close_start_fallback_to_master(monkeypatch):
    order = SimpleNamespace(
        id=2,
        assigned_master_id=88,
        status=m.OrderStatus.WORKING,
        order_type=m.OrderType.NORMAL,
    )

    class _Session:
        async def get(self, model, order_id):
            assert model is m.orders
            assert order_id == 2
            return order

    state = _DummyState()
    session = _Session()
    bot = SimpleNamespace()
    callback = SimpleNamespace(
        data='m:act:cls:2',
        message=None,
        from_user=None,
        bot=bot,
        id='cb-fallback',
    )
    master = SimpleNamespace(id=88, tg_user_id=777)

    safe_answer = AsyncMock(return_value=None)
    safe_send = AsyncMock(return_value=None)
    monkeypatch.setattr(orders, 'safe_answer_callback', safe_answer)
    monkeypatch.setattr(orders, 'safe_send_message', safe_send)

    await orders.active_close_start(callback, state, session, master, bot)

    assert state.state == CloseOrderStates.amount
    assert state.data == {'close_order_id': 2, 'close_order_amount': None}
    safe_send.assert_awaited_once()
    args, kwargs = safe_send.await_args
    assert args == (bot, 777, orders.CLOSE_AMOUNT_PROMPT)
    assert "reply_markup" in kwargs
    safe_answer.assert_awaited()
