from __future__ import annotations

import types
from decimal import Decimal

import pytest
from typing import Iterable, Optional

from field_service.bots.admin_bot import queue
from field_service.bots.admin_bot.dto import MasterBrief, OrderDetail, OrderType, StaffRole, StaffUser


class StubOrdersService:
    def __init__(self, order: OrderDetail, masters: list[MasterBrief]) -> None:
        self.order = order
        self._masters = masters
        self.calls: list[tuple[int, int, int]] = []

    async def get_card(
        self, order_id: int, *, city_ids: Optional[Iterable[int]] | None = None
    ) -> OrderDetail | None:
        return self.order if order_id == self.order.id else None

    async def manual_candidates(
        self,
        order_id: int,
        *,
        page: int,
        page_size: int,
        city_ids: Optional[Iterable[int]] = None,
    ) -> tuple[list[MasterBrief], bool]:
        self.calls.append((order_id, page, page_size))
        return list(self._masters), False


class StubDistributionService:
    def __init__(self) -> None:
        self.calls: list[tuple[int, int, int]] = []

    async def send_manual_offer(
        self,
        order_id: int,
        master_id: int,
        by_staff_id: int,
    ) -> tuple[bool, str]:
        self.calls.append((order_id, master_id, by_staff_id))
        return True, " "


class StubMessage:
    def __init__(self, bot) -> None:
        self.bot = bot
        self.text: str | None = None
        self.reply_markup = None

    async def edit_text(self, text: str, reply_markup=None, disable_web_page_preview: bool = False) -> None:
        self.text = text
        self.reply_markup = reply_markup

    async def answer(self, text: str, reply_markup=None, disable_web_page_preview: bool = False):
        self.text = text
        self.reply_markup = reply_markup
        return self


class StubCallback:
    def __init__(self, data: str, message: StubMessage) -> None:
        self.data = data
        self.message = message
        self.bot = message.bot
        self.answers: list[tuple[str | None, bool]] = []

    async def answer(self, text: str | None = None, show_alert: bool = False) -> None:
        self.answers.append((text, show_alert))


def make_order(**overrides) -> OrderDetail:
    base = dict(
        id=1,
        city_id=1,
        city_name="",
        district_id=10,
        district_name="",
        street_name="",
        house="10",
        status="SEARCHING",
        order_type=OrderType.NORMAL,
        category="ELECTRICS",
        created_at_local="01.01 10:00",
        timeslot_local="10-13",
        master_id=None,
        master_name=None,
        master_phone=None,
        has_attachments=False,
        client_name="",
        client_phone="+79990000000",
        apartment=None,
        address_comment=None,
        description="",
        lat=None,
        lon=None,
        company_payment=None,
        total_sum=Decimal("0"),
        attachments=tuple(),
    )
    base.update(overrides)
    return OrderDetail(**base)


def make_master(**overrides) -> MasterBrief:
    base = dict(
        id=101,
        full_name=" ",
        city_id=1,
        has_car=False,
        avg_week_check=2500.0,
        rating_avg=4.5,
        is_on_shift=True,
        is_active=True,
        verified=True,
        in_district=True,
        active_orders=0,
        max_active_orders=5,
        on_break=False,
    )
    base.update(overrides)
    return MasterBrief(**base)


@pytest.mark.asyncio
async def test_manual_check_requires_confirmation_off_shift() -> None:
    order = make_order()
    master = make_master(is_on_shift=False)
    orders_service = StubOrdersService(order, [master])
    dist_service = StubDistributionService()
    bot = types.SimpleNamespace(_services={
        "orders_service": orders_service,
        "distribution_service": dist_service,
    })
    message = StubMessage(bot)
    callback = StubCallback("adm:q:as:check:1:1:101", message)
    staff = StaffUser(
        id=1,
        tg_id=1,
        role=StaffRole.GLOBAL_ADMIN,
        is_active=True,
        city_ids=frozenset({order.city_id}),
    )

    await queue.cb_queue_assign_manual_check(callback, staff)

    assert not dist_service.calls
    assert message.text is not None and " " in message.text
    buttons = [btn for row in message.reply_markup.inline_keyboard for btn in row]
    assert any(btn.callback_data == "adm:q:as:pick:1:1:101" for btn in buttons)


@pytest.mark.asyncio
async def test_manual_check_requires_confirmation_at_limit() -> None:
    order = make_order()
    master = make_master(active_orders=5, max_active_orders=5)
    orders_service = StubOrdersService(order, [master])
    dist_service = StubDistributionService()
    bot = types.SimpleNamespace(_services={
        "orders_service": orders_service,
        "distribution_service": dist_service,
    })
    message = StubMessage(bot)
    callback = StubCallback("adm:q:as:check:1:1:101", message)
    staff = StaffUser(
        id=1,
        tg_id=1,
        role=StaffRole.GLOBAL_ADMIN,
        is_active=True,
        city_ids=frozenset({order.city_id}),
    )

    await queue.cb_queue_assign_manual_check(callback, staff)

    assert not dist_service.calls
    assert message.text is not None and "" in message.text
    buttons = [btn for row in message.reply_markup.inline_keyboard for btn in row]
    assert any(btn.callback_data == "adm:q:as:pick:1:1:101" for btn in buttons)


@pytest.mark.asyncio
async def test_manual_check_sends_offer_without_confirmation() -> None:
    order = make_order()
    master = make_master()
    orders_service = StubOrdersService(order, [master])
    dist_service = StubDistributionService()
    bot = types.SimpleNamespace(_services={
        "orders_service": orders_service,
        "distribution_service": dist_service,
    })
    message = StubMessage(bot)
    callback = StubCallback("adm:q:as:check:1:1:101", message)
    staff = StaffUser(
        id=1,
        tg_id=1,
        role=StaffRole.GLOBAL_ADMIN,
        is_active=True,
        city_ids=frozenset({order.city_id}),
    )

    await queue.cb_queue_assign_manual_check(callback, staff)

    assert dist_service.calls == [(1, 101, staff.id)]
    assert message.text is not None and " " in message.text
    assert callback.answers and callback.answers[-1][0] == " "


@pytest.mark.asyncio
async def test_manual_pick_confirms_and_sends_offer() -> None:
    order = make_order()
    master = make_master()
    orders_service = StubOrdersService(order, [master])
    dist_service = StubDistributionService()
    bot = types.SimpleNamespace(_services={
        "orders_service": orders_service,
        "distribution_service": dist_service,
    })
    message = StubMessage(bot)
    callback = StubCallback("adm:q:as:pick:1:1:101", message)
    staff = StaffUser(
        id=1,
        tg_id=1,
        role=StaffRole.GLOBAL_ADMIN,
        is_active=True,
        city_ids=frozenset({order.city_id}),
    )

    await queue.cb_queue_assign_manual_pick(callback, staff)

    assert dist_service.calls == [(1, 101, staff.id)]
    assert message.text is not None and " " in message.text
    buttons = [btn for row in message.reply_markup.inline_keyboard for btn in row]
    assert any(btn.callback_data == "adm:q:card:1" for btn in buttons)
    assert any(btn.callback_data == "adm:q:as:man:1:1" for btn in buttons)
    assert callback.answers and callback.answers[-1][0] == " "
