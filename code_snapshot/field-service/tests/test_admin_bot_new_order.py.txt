import asyncio
from dataclasses import dataclass
from datetime import time
from typing import List, Optional
from types import SimpleNamespace

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from field_service.bots.admin_bot import handlers
from field_service.bots.admin_bot.dto import (
    CityRef,
    DistrictRef,
    NewOrderData,
    StaffRole,
    StaffUser,
    StreetRef,
)
from field_service.db.pg_enums import OrderCategory
from field_service.db.models import OrderType


class DummySettingsService:
    async def get_working_window(self):
        return time(10, 0), time(19, 0)


class DummyDocument:
    file_id = "file_1"
    file_unique_id = "uniq_1"
    file_name = "passport.pdf"
    mime_type = "application/pdf"


class DummyMessage:
    def __init__(self, bot, text: Optional[str] = None, document=None, caption: Optional[str] = None) -> None:
        self.bot = bot
        self.text = text
        self.document = document
        self.caption = caption
        self.photo = None
        self.answers: List[tuple[str, Optional[object]]] = []
        self.edits: List[tuple[str, Optional[object]]] = []

    async def edit_text(self, text, reply_markup=None, **kwargs):
        self.edits.append((text, reply_markup, kwargs))

    async def answer(self, text, reply_markup=None, **kwargs):
        self.answers.append((text, reply_markup, kwargs))

    def last_interaction(self):
        if self.edits:
            return self.edits[-1]
        if self.answers:
            return self.answers[-1]
        return None


class DummyCallbackQuery:
    def __init__(self, message: DummyMessage, data: str) -> None:
        self.message = message
        self.data = data
        self._answers: List[tuple[tuple, dict]] = []

    async def answer(self, *args, **kwargs):
        self._answers.append((args, kwargs))


class DummyOrdersService:
    def __init__(self):
        self.cities = {
            1: CityRef(id=1, name="City 1"),
        }
        self.districts = {
            10: DistrictRef(id=10, city_id=1, name="District 10"),
        }
        self.streets = {
            100: StreetRef(id=100, city_id=1, district_id=10, name="Main Street", score=95.0),
        }
        self.search_sequences: List[List[StreetRef]] = []
        self.created_orders: List[NewOrderData] = []
        self.last_card_request = None
        self._last_card_stub: Optional[SimpleNamespace] = None

    async def list_cities(self, *_, **__):
        return list(self.cities.values())

    async def get_city(self, city_id: int):
        return self.cities.get(city_id)

    async def list_districts(self, city_id: int, *, page: int, page_size: int):
        del city_id, page, page_size
        items = list(self.districts.values())
        return items, False

    async def get_district(self, district_id: int):
        return self.districts.get(district_id)

    async def search_streets(self, *_args, **_kwargs):
        if self.search_sequences:
            return self.search_sequences.pop(0)
        return []

    async def get_street(self, street_id: int):
        return self.streets.get(street_id)

    async def get_city_timezone(self, _city_id: int):
        return "Europe/Moscow"

    async def create_order(self, data: NewOrderData) -> int:
        self.created_orders.append(data)
        order_id = len(self.created_orders)
        self._last_card_stub = SimpleNamespace(id=order_id, district_id=data.district_id)
        return order_id

    async def get_card(self, order_id: int, city_ids):
        self.last_card_request = (order_id, city_ids)
        return self._last_card_stub


class DummyBot:
    def __init__(self, orders_service: DummyOrdersService, settings_service: DummySettingsService) -> None:
        self._services = {
            "orders_service": orders_service,
            "settings_service": settings_service,
        }


async def make_context():
    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=100, user_id=200)
    ctx = FSMContext(storage=storage, key=key)
    return ctx, storage


async def run_full_flow(
    monkeypatch,
    *,
    orders_service: DummyOrdersService,
    settings_service: DummySettingsService,
    category_token: str,
    manual_street: Optional[str] = None,
) -> tuple[DummyBot, DummyMessage, FSMContext, DummyOrdersService]:
    bot = DummyBot(orders_service, settings_service)
    ctx, storage = await make_context()
    staff = StaffUser(
        id=1,
        tg_id=200,
        role=StaffRole.GLOBAL_ADMIN,
        is_active=True,
        city_ids=frozenset(),
    )
    base_message = DummyMessage(bot)
    start_cq = DummyCallbackQuery(base_message, "adm:new")
    await handlers._start_new_order(start_cq, staff, ctx)

    await handlers.cb_new_order_city_pick(DummyCallbackQuery(base_message, "adm:new:city:1"), ctx)

    if manual_street is None:
        await handlers.cb_new_order_district_pick(DummyCallbackQuery(base_message, "adm:new:district:10"), ctx)
        await handlers.cb_new_order_street_search(DummyCallbackQuery(base_message, "adm:new:street:search"), ctx)
        await handlers.new_order_street_search_input(DummyMessage(bot, text="Main"), ctx)
        await handlers.cb_new_order_street_pick(DummyCallbackQuery(base_message, "adm:new:street:100"), ctx)
    else:
        await handlers.cb_new_order_district_none(DummyCallbackQuery(base_message, "adm:new:district:none"), ctx)
        await handlers.cb_new_order_street_search(DummyCallbackQuery(base_message, "adm:new:street:search"), ctx)
        await handlers.new_order_street_search_input(DummyMessage(bot, text="no matches"), ctx)
        await handlers.cb_new_order_street_manual(DummyCallbackQuery(base_message, "adm:new:street:manual"), ctx)
        await handlers.new_order_street_manual_input(DummyMessage(bot, text=manual_street), ctx)

    await handlers.new_order_house(DummyMessage(bot, text="12"), ctx)
    await handlers.new_order_apartment(DummyMessage(bot, text="34"), ctx)
    await handlers.new_order_address_comment(DummyMessage(bot, text="Comment"), ctx)
    await handlers.new_order_client_name(DummyMessage(bot, text="Ivan Petrov"), ctx)
    await handlers.new_order_client_phone(DummyMessage(bot, text="+15551234567"), ctx)

    await handlers.cb_new_order_category(DummyCallbackQuery(base_message, f"adm:new:cat:{category_token}"), ctx)
    await handlers.new_order_description(DummyMessage(bot, text="Order description"), ctx)

    # Add an attachment when testing normal flow
    if manual_street is None:
        await handlers.new_order_attach_doc(DummyMessage(bot, document=DummyDocument(), caption="Document"), ctx)

    await handlers.cb_new_order_att_done(DummyCallbackQuery(base_message, "adm:new:att:done"), ctx)
    order_type_token = "NORMAL" if manual_street is None else "GUARANTEE"
    await handlers.cb_new_order_type(DummyCallbackQuery(base_message, f"adm:new:type:{order_type_token}"), ctx)

    data = await ctx.get_data()
    slot_options = data.get("slot_options") or []
    chosen_slot = next(key for key, _ in slot_options if key != "ASAP")
    await handlers.cb_new_order_slot(DummyCallbackQuery(base_message, f"adm:new:slot:{chosen_slot}"), ctx)

    async def fake_render(message, order_id, staff_arg):
        fake_render.calls.append((order_id, staff_arg))
        await message.answer(f"Order {order_id} stub")

    fake_render.calls = []
    monkeypatch.setattr(handlers, "_render_created_order_card", fake_render)

    await handlers.cb_new_order_confirm(DummyCallbackQuery(base_message, "adm:new:confirm"), ctx, staff=staff)

    # ensure storage closed by caller
    return bot, base_message, ctx, storage


@pytest.mark.asyncio
async def test_new_order_flow_with_search_and_attachment(monkeypatch):
    orders_service = DummyOrdersService()
    orders_service.search_sequences = [[orders_service.streets[100]]]
    settings_service = DummySettingsService()

    bot, message, ctx, storage = await run_full_flow(
        monkeypatch,
        orders_service=orders_service,
        settings_service=settings_service,
        category_token="ELECTRICS",
    )

    try:
        assert orders_service.created_orders, "order should be created"
        order = orders_service.created_orders[0]
        assert order.city_id == 1
        assert order.district_id == 10
        assert order.street_id == 100
        assert order.category is OrderCategory.ELECTRICS
        assert order.order_type is OrderType.NORMAL
        assert order.attachments, "attachment expected"
        assert order.no_district is False
        assert await ctx.get_state() is None
        last = message.last_interaction()
        assert last is not None
        text_out, markup, kwargs = last
        assert "Выберите способ распределения" in text_out
        assert markup is not None
        callbacks = [btn.callback_data for row in markup.inline_keyboard for btn in row]
        order_id = len(orders_service.created_orders)
        assert f"adm:q:as:auto:{order_id}" in callbacks
        assert f"adm:q:as:man:{order_id}:1" in callbacks
    finally:
        await storage.close()


@pytest.mark.asyncio
async def test_new_order_flow_manual_street_and_guarantee(monkeypatch):
    orders_service = DummyOrdersService()
    orders_service.districts = {}
    orders_service.search_sequences = [[]]
    settings_service = DummySettingsService()

    bot, message, ctx, storage = await run_full_flow(
        monkeypatch,
        orders_service=orders_service,
        settings_service=settings_service,
        category_token="HANDYMAN",
        manual_street="Custom street",
    )

    try:
        assert orders_service.created_orders, "order should be created"
        order = orders_service.created_orders[0]
        assert order.city_id == 1
        assert order.district_id is None
        assert order.street_id is None
        assert order.no_district is True
        assert order.category is OrderCategory.HANDYMAN
        assert order.order_type is OrderType.GUARANTEE
        assert not order.attachments
        assert await ctx.get_state() is None
        last = message.last_interaction()
        assert last is not None
        text_out, markup, kwargs = last
        assert "Выберите способ распределения" in text_out
        assert markup is not None
        callbacks = [btn.callback_data for row in markup.inline_keyboard for btn in row]
        order_id = len(orders_service.created_orders)
        assert all("adm:q:as:auto" not in cb for cb in callbacks)
        assert f"adm:q:as:man:{order_id}:1" in callbacks
    finally:
        await storage.close()
