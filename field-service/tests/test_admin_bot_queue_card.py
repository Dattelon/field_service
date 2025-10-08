from decimal import Decimal

import pytest

from field_service.bots.admin_bot import queue
from field_service.bots.admin_bot.dto import (
    OrderAttachment,
    OrderDetail,
    OrderStatusHistoryItem,
    OrderType,
)


class StubMessage:
    def __init__(self) -> None:
        self.text = None
        self.reply_markup = None

    async def edit_text(self, text: str, reply_markup) -> None:
        self.text = text
        self.reply_markup = reply_markup

    async def answer(self, text: str, reply_markup) -> None:
        self.text = text
        self.reply_markup = reply_markup


def make_order(**overrides):
    data = dict(
        id=1,
        city_id=1,
        city_name='City',
        district_id=None,
        district_name=None,
        street_name='Main',
        house='10',
        status='SEARCHING',
        order_type=OrderType.NORMAL,
        category='ELECTRICS',
        created_at_local='01.01 10:00',
        timeslot_local='10-13',
        master_id=None,
        master_name=None,
        master_phone=None,
        has_attachments=False,
        client_name='Client',
        client_phone='+79990000000',
        apartment=None,
        address_comment=None,
        description='Проблема',
        lat=None,
        lon=None,
        company_payment=Decimal('0'),
        total_sum=Decimal('0'),
        attachments=tuple(),
    )
    data.update(overrides)
    return OrderDetail(**data)


@pytest.mark.asyncio
async def test_format_order_card_text_without_master_and_attachments() -> None:
    order = make_order(description=None)
    text = queue._format_order_card_text(order, history=())
    assert 'Вложения: 0' in text
    assert 'Мастер: пока не назначен' in text
    assert 'Описание' in text


@pytest.mark.asyncio
async def test_render_order_card_uses_keyboard_with_attachments() -> None:
    attachment = OrderAttachment(id=5, file_type='DOCUMENT', file_id='file123', file_name='акт.pdf', caption=None)
    order = make_order(attachments=(attachment,), has_attachments=True)
    history = (OrderStatusHistoryItem(
        id=1,
        from_status=None,
        to_status='SEARCHING',
        reason=None,
        changed_by_staff_id=10,
        changed_by_master_id=None,
        changed_at_local='01.01 10:00',
    ),)
    message = StubMessage()
    await queue._render_order_card(message, order, history)
    assert message.text is not None
    assert message.reply_markup is not None
    buttons = [btn for row in message.reply_markup.inline_keyboard for btn in row]
    assert any(btn.callback_data == 'adm:q:att:1:5' for btn in buttons)
    assert any(btn.callback_data == 'adm:q:as:1' for btn in buttons)


@pytest.mark.asyncio
async def test_order_card_keyboard_hides_return_for_final_status() -> None:
    order = make_order(status='CANCELED')
    markup = queue._order_card_markup(order)
    callbacks = [btn.callback_data for row in markup.inline_keyboard for btn in row]
    assert all(item != 'adm:q:ret:1' for item in callbacks)
    assert all(item != 'adm:q:cnl:1' for item in callbacks)


@pytest.mark.asyncio
async def test_order_card_keyboard_shows_guarantee_button() -> None:
    order = make_order(status='CLOSED', master_id=42)
    markup = queue._order_card_markup(order, show_guarantee=True)
    callbacks = [btn.callback_data for row in markup.inline_keyboard for btn in row]
    assert f'adm:q:gar:{order.id}' in callbacks


class _StubOrdersService:
    def __init__(self, has_active: bool) -> None:
        self.has_active = has_active
        self.seen: list[int] = []

    async def has_active_guarantee(self, order_id: int) -> bool:
        self.seen.append(order_id)
        return self.has_active


@pytest.mark.asyncio
async def test_should_show_guarantee_button_true() -> None:
    order = make_order(status='CLOSED', master_id=5)
    service = _StubOrdersService(has_active=False)
    result = await queue._should_show_guarantee_button(order, service)
    assert result is True
    assert service.seen == [order.id]


@pytest.mark.asyncio
async def test_should_show_guarantee_button_false_when_active_exists() -> None:
    order = make_order(status='CLOSED', master_id=5)
    service = _StubOrdersService(has_active=True)
    result = await queue._should_show_guarantee_button(order, service)
    assert result is False


@pytest.mark.asyncio
async def test_should_show_guarantee_button_false_for_non_closed() -> None:
    order = make_order(status='SEARCHING', master_id=5)
    service = _StubOrdersService(has_active=False)
    result = await queue._should_show_guarantee_button(order, service)
    assert result is False


@pytest.mark.asyncio
async def test_should_show_guarantee_button_false_for_guarantee_type() -> None:
    order = make_order(status='CLOSED', master_id=5, order_type=OrderType.GUARANTEE)
    service = _StubOrdersService(has_active=False)
    result = await queue._should_show_guarantee_button(order, service)
    assert result is False
