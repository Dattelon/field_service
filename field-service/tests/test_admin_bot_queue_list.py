from __future__ import annotations

import types

import pytest

from field_service.bots.admin_bot import queue
from field_service.bots.admin_bot.dto import CityRef, OrderListItem, OrderType, StaffRole, StaffUser


class StubState:
    def __init__(self, data: dict | None = None) -> None:
        self._data = data or {}

    async def get_data(self) -> dict:
        return dict(self._data)

    async def update_data(self, values: dict) -> None:
        self._data.update(values)

    async def set_state(self, value) -> None:  # pragma: no cover - not used in tests
        self._data["state"] = value

    async def clear(self) -> None:
        self._data.clear()


class StubMessage:
    def __init__(self, bot) -> None:
        self.bot = bot
        self.chat = types.SimpleNamespace(id=100)
        self.message_id = 555
        self.text = None
        self.reply_markup = None

    async def edit_text(self, text: str, reply_markup) -> None:
        self.text = text
        self.reply_markup = reply_markup

    async def answer(self, text: str, reply_markup) -> "StubMessage":  # pragma: no cover
        self.text = text
        self.reply_markup = reply_markup
        return self


class CaptureOrdersService:
    def __init__(self, items: list[OrderListItem], *, has_next: bool = False) -> None:
        self._items = items
        self._has_next = has_next
        self.calls: list[dict] = []

    async def list_queue(
        self,
        *,
        city_ids,
        page: int,
        page_size: int,
        status_filter=None,
        category=None,
        master_id=None,
        timeslot_date=None,
    ) -> tuple[list[OrderListItem], bool]:
        self.calls.append(
            {
                "city_ids": city_ids,
                "page": page,
                "page_size": page_size,
                "status_filter": status_filter,
                "category": category,
                "master_id": master_id,
                "timeslot_date": timeslot_date,
            }
        )
        return self._items, self._has_next

    async def get_city(self, city_id: int) -> CityRef | None:
        return CityRef(id=city_id, name=f"City #{city_id}")

    async def list_cities(self, *, query: str | None = None, limit: int = 20):  # pragma: no cover
        return []


@pytest.fixture()
def sample_order() -> OrderListItem:
    return OrderListItem(
        id=1,
        city_id=2,
        city_name="City #2",
        district_id=None,
        district_name=None,
        street_name="Main",
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
    )


@pytest.mark.asyncio
async def test_queue_list_uses_staff_city_scope(sample_order: OrderListItem) -> None:
    service = CaptureOrdersService([sample_order])
    bot = types.SimpleNamespace(_services={"orders_service": service})
    message = StubMessage(bot)
    staff = StaffUser(
        id=10,
        tg_id=10,
        role=StaffRole.CITY_ADMIN,
        is_active=True,
        city_ids=frozenset({sample_order.city_id}),
    )
    state = StubState({queue.FILTER_DATA_KEY: queue._default_filters()})

    await queue._render_queue_list(message, staff, state, page=1)

    assert service.calls, "list_queue was not called"
    assert service.calls[0]["city_ids"] == [sample_order.city_id]


@pytest.mark.asyncio
async def test_queue_list_empty_renders_placeholder() -> None:
    service = CaptureOrdersService([])
    bot = types.SimpleNamespace(_services={"orders_service": service})
    message = StubMessage(bot)
    staff = StaffUser(
        id=1,
        tg_id=1,
        role=StaffRole.GLOBAL_ADMIN,
        is_active=True,
        city_ids=frozenset(),
    )
    state = StubState({queue.FILTER_DATA_KEY: queue._default_filters()})

    await queue._render_queue_list(message, staff, state, page=2)

    assert "Список пуст" in message.text
    assert message.reply_markup is not None
    buttons = [btn for row in message.reply_markup.inline_keyboard for btn in row]
    assert any(btn.callback_data == "adm:q:flt" for btn in buttons)
