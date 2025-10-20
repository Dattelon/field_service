
import dataclasses
import types
from decimal import Decimal

import pytest

from field_service.bots.admin_bot import queue
from field_service.bots.admin_bot.dto import (
    OrderDetail,
    OrderStatusHistoryItem,
    OrderType,
    StaffRole,
    StaffUser,
)
from field_service.bots.admin_bot.states import QueueActionFSM


def make_order(order_id: int = 1, *, status: str = "ASSIGNED", master_id: int | None = 101, **overrides):
    base = dict(
        id=order_id,
        city_id=1,
        city_name="City",
        district_id=None,
        district_name=None,
        street_name="Main",
        house="1",
        status=status,
        order_type=OrderType.NORMAL,
        category="ELECTRICS",
        created_at_local="01.01 10:00",
        timeslot_local="10-13",
        master_id=master_id,
        master_name="Master" if master_id else None,
        master_phone="+79990000001" if master_id else None,
        has_attachments=False,
        client_name="Client",
        client_phone="+79990000000",
        apartment=None,
        address_comment=None,
        description="Description",
        lat=None,
        lon=None,
        company_payment=None,
        total_sum=Decimal("0"),
        attachments=tuple(),
    )
    base.update(overrides)
    return OrderDetail(**base)


def make_history(order_id: int, *, to_status: str) -> tuple[OrderStatusHistoryItem, ...]:
    item = OrderStatusHistoryItem(
        id=1,
        from_status=None,
        to_status=to_status,
        reason=None,
        changed_by_staff_id=10,
        changed_by_master_id=None,
        changed_at_local="01.01 10:00",
    )
    return (item,)


class StubOrdersServiceReturn:
    def __init__(self, order: OrderDetail, history: tuple[OrderStatusHistoryItem, ...]) -> None:
        self.order = order
        self.history = history
        self.return_calls: list[tuple[int, int]] = []
        self.history_calls: list[tuple[int, int]] = []

    async def get_card(self, order_id: int) -> OrderDetail | None:
        return self.order if order_id == self.order.id else None

    async def list_status_history(self, order_id: int, limit: int) -> tuple[OrderStatusHistoryItem, ...]:
        self.history_calls.append((order_id, limit))
        return self.history

    async def return_to_search(self, order_id: int, staff_id: int) -> bool:
        self.return_calls.append((order_id, staff_id))
        if order_id != self.order.id:
            return False
        self.order = dataclasses.replace(self.order, status="SEARCHING", master_id=None, master_name=None)
        self.history = make_history(order_id, to_status="SEARCHING")
        return True


class StubOrdersServiceCancel:
    def __init__(self, order: OrderDetail, history: tuple[OrderStatusHistoryItem, ...]) -> None:
        self.order = order
        self.history = history
        self.cancel_calls: list[tuple[int, str, int]] = []
        self.history_calls: list[tuple[int, int]] = []
        self.cancel_result = True

    async def get_card(self, order_id: int) -> OrderDetail | None:
        return self.order if order_id == self.order.id else None

    async def list_status_history(self, order_id: int, limit: int) -> tuple[OrderStatusHistoryItem, ...]:
        self.history_calls.append((order_id, limit))
        return self.history

    async def cancel(self, order_id: int, reason: str, by_staff_id: int) -> bool:
        self.cancel_calls.append((order_id, reason, by_staff_id))
        if order_id != self.order.id or not self.cancel_result:
            return False
        self.order = dataclasses.replace(self.order, status="CANCELED", master_id=None, master_name=None)
        self.history = make_history(order_id, to_status="CANCELED")
        return True


class StubBot:
    def __init__(self, services: dict[str, object]) -> None:
        self._services = services
        self.edited: list[tuple[int, int, str, object]] = []
        self.sent: list[tuple[int, str, object]] = []

    async def edit_message_text(self, *, chat_id: int, message_id: int, text: str, reply_markup) -> None:
        self.edited.append((chat_id, message_id, text, reply_markup))

    async def send_message(self, chat_id: int, text: str, reply_markup=None):
        self.sent.append((chat_id, text, reply_markup))
        return types.SimpleNamespace(chat=types.SimpleNamespace(id=chat_id), message_id=999)


class StubMessage:
    def __init__(self, bot, *, chat_id: int = 100, message_id: int = 555, text: str | None = None) -> None:
        self.bot = bot
        self.chat = types.SimpleNamespace(id=chat_id)
        self.message_id = message_id
        self.text = text
        self.reply_markup = None
        self.edited: list[tuple[str, object]] = []
        self.answered: list[tuple[str | None, object | None]] = []

    async def edit_text(self, text: str, reply_markup=None, disable_web_page_preview: bool = False) -> None:
        self.text = text
        self.reply_markup = reply_markup
        self.edited.append((text, reply_markup))

    async def answer(self, text: str, reply_markup=None):
        self.answered.append((text, reply_markup))
        return self


class StubCallback:
    def __init__(self, data: str, message: StubMessage) -> None:
        self.data = data
        self.message = message
        self.bot = message.bot
        self.answers: list[tuple[str | None, bool]] = []

    async def answer(self, text: str | None = None, show_alert: bool = False) -> None:
        self.answers.append((text, show_alert))


class StubState:
    def __init__(self, data: dict | None = None, state: str | None = None) -> None:
        self._data = dict(data or {})
        self._state = state

    async def get_data(self) -> dict:
        return dict(self._data)

    async def set_data(self, data: dict) -> None:
        self._data = dict(data)

    async def update_data(self, values: dict) -> None:
        self._data.update(values)

    async def set_state(self, value) -> None:
        self._state = value

    async def get_state(self):
        return self._state


@pytest.mark.asyncio
async def test_cb_queue_return_success() -> None:
    order = make_order(status="ASSIGNED")
    service = StubOrdersServiceReturn(order, make_history(order.id, to_status="ASSIGNED"))
    bot = StubBot({"orders_service": service})
    message = StubMessage(bot)
    callback = StubCallback("adm:q:ret:1", message)
    staff = StaffUser(id=1, tg_id=1, role=StaffRole.GLOBAL_ADMIN, is_active=True, city_ids=frozenset({1}))

    await queue.cb_queue_return(callback, staff)

    assert service.return_calls == [(1, staff.id)]
    assert message.edited, "order card was not re-rendered"
    assert callback.answers[-1] == ("   ", False)
    assert any(btn.callback_data == "adm:q:cnl:1" for row in message.reply_markup.inline_keyboard for btn in row)


@pytest.mark.asyncio
async def test_cb_queue_return_denied_for_city() -> None:
    order = make_order(status="ASSIGNED")
    service = StubOrdersServiceReturn(order, make_history(order.id, to_status="ASSIGNED"))
    bot = StubBot({"orders_service": service})
    message = StubMessage(bot)
    callback = StubCallback("adm:q:ret:1", message)
    staff = StaffUser(id=2, tg_id=2, role=StaffRole.CITY_ADMIN, is_active=True, city_ids=frozenset({2}))

    await queue.cb_queue_return(callback, staff)

    assert service.return_calls == []
    assert callback.answers[-1] == ("   ", True)
    assert not message.edited


@pytest.mark.asyncio
async def test_cb_queue_cancel_start_sets_state_and_keyboard() -> None:
    order = make_order(status="SEARCHING")
    service = StubOrdersServiceReturn(order, make_history(order.id, to_status="SEARCHING"))
    bot = StubBot({"orders_service": service})
    message = StubMessage(bot)
    callback = StubCallback("adm:q:cnl:1", message)
    state = StubState({"queue_filters": {"city_id": 1}})
    staff = StaffUser(id=3, tg_id=3, role=StaffRole.GLOBAL_ADMIN, is_active=True, city_ids=frozenset({1}))

    await queue.cb_queue_cancel_start(callback, staff, state)

    assert state._state == QueueActionFSM.cancel_reason.state
    data = state._data
    assert data[queue.CANCEL_ORDER_KEY] == 1
    assert data[queue.CANCEL_CHAT_KEY] == message.chat.id
    assert data[queue.CANCEL_MESSAGE_KEY] == message.message_id
    assert message.edited, "prompt was not shown"
    buttons = [btn for row in message.reply_markup.inline_keyboard for btn in row]
    assert any(btn.callback_data == "adm:q:cnl:bk:1" for btn in buttons)


@pytest.mark.asyncio
async def test_queue_cancel_reason_success_updates_card() -> None:
    order = make_order(status="ASSIGNED")
    service = StubOrdersServiceCancel(order, make_history(order.id, to_status="ASSIGNED"))
    bot = StubBot({"orders_service": service})
    state = StubState({
        "queue_filters": {"city_id": 1},
        queue.CANCEL_ORDER_KEY: 1,
        queue.CANCEL_CHAT_KEY: 100,
        queue.CANCEL_MESSAGE_KEY: 555,
    }, state=QueueActionFSM.cancel_reason.state)
    message = StubMessage(bot, text=" ")
    staff = StaffUser(id=5, tg_id=5, role=StaffRole.GLOBAL_ADMIN, is_active=True, city_ids=frozenset({1}))

    await queue.queue_cancel_reason(message, staff, state)

    assert service.cancel_calls == [(1, " ", staff.id)]
    assert state._state is None
    assert queue.CANCEL_ORDER_KEY not in state._data
    assert bot.edited, "card was not re-rendered"
    assert message.answered[-1][0] == " ."


@pytest.mark.asyncio
async def test_queue_cancel_reason_rejects_short_text() -> None:
    order = make_order(status="ASSIGNED")
    service = StubOrdersServiceCancel(order, make_history(order.id, to_status="ASSIGNED"))
    bot = StubBot({"orders_service": service})
    state = StubState({
        queue.CANCEL_ORDER_KEY: 1,
        queue.CANCEL_CHAT_KEY: 100,
        queue.CANCEL_MESSAGE_KEY: 555,
    }, state=QueueActionFSM.cancel_reason.state)
    message = StubMessage(bot, text="ok")
    staff = StaffUser(id=6, tg_id=6, role=StaffRole.GLOBAL_ADMIN, is_active=True, city_ids=frozenset({1}))

    await queue.queue_cancel_reason(message, staff, state)

    assert service.cancel_calls == []
    assert state._state == QueueActionFSM.cancel_reason.state
    assert message.answered[-1][0].startswith("  ")
    assert not bot.edited


@pytest.mark.asyncio
async def test_queue_cancel_abort_restores_card() -> None:
    order = make_order(status="ASSIGNED")
    history = make_history(order.id, to_status="ASSIGNED")
    service = StubOrdersServiceCancel(order, history)
    bot = StubBot({"orders_service": service})
    state = StubState({
        queue.CANCEL_ORDER_KEY: 1,
        queue.CANCEL_CHAT_KEY: 100,
        queue.CANCEL_MESSAGE_KEY: 555,
    }, state=QueueActionFSM.cancel_reason.state)
    message = StubMessage(bot, text="/cancel")
    staff = StaffUser(id=7, tg_id=7, role=StaffRole.GLOBAL_ADMIN, is_active=True, city_ids=frozenset({1}))

    await queue.queue_cancel_abort(message, staff, state)

    assert state._state is None
    assert queue.CANCEL_ORDER_KEY not in state._data
    assert bot.edited, "Card was not restored"
    assert message.answered[-1][0] == " ."


@pytest.mark.asyncio
async def test_queue_cancel_reason_service_failure() -> None:
    order = make_order(status="ASSIGNED")
    service = StubOrdersServiceCancel(order, make_history(order.id, to_status="ASSIGNED"))
    service.cancel_result = False
    bot = StubBot({"orders_service": service})
    state = StubState({
        queue.CANCEL_ORDER_KEY: 1,
        queue.CANCEL_CHAT_KEY: 100,
        queue.CANCEL_MESSAGE_KEY: 555,
    }, state=QueueActionFSM.cancel_reason.state)
    message = StubMessage(bot, text="")
    staff = StaffUser(id=8, tg_id=8, role=StaffRole.GLOBAL_ADMIN, is_active=True, city_ids=frozenset({1}))

    await queue.queue_cancel_reason(message, staff, state)

    assert service.cancel_calls == [(1, "", staff.id)]
    assert message.answered[-1][0] == "   ."
    assert bot.edited, "   "
    assert state._state is None
