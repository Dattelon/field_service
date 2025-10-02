import sys
sys.path.append('c:/ProjectF/field-service')
import asyncio
from types import SimpleNamespace
from unittest.mock import patch
from field_service.bots.master_bot.handlers import orders
from field_service.db import models as m
from aiogram.types import CallbackQuery, Message

class FakeState:
    def __init__(self):
        self.data = {}
        self.state = None
    async def update_data(self, **kwargs):
        self.data.update(kwargs)
    async def set_state(self, value):
        self.state = value
    async def clear(self):
        self.data.clear()
        self.state = None

async def main():
    fake_order = SimpleNamespace(id=1, assigned_master_id=10, status=m.OrderStatus.WORKING, order_type=m.OrderType.NORMAL)
    class FakeSession:
        async def get(self, model, order_id):
            return fake_order
    session = FakeSession()
    state = FakeState()
    message = Message.model_validate({
        'message_id': 101,
        'date': 0,
        'chat': {'id': 555, 'type': 'private'},
        'from': {'id': 555, 'is_bot': False, 'first_name': 'Test'},
        'text': 'dummy',
    })
    async def answer(text, **kwargs):
        print('message.answer', text)
        return None
    object.__setattr__(message, 'answer', answer)
    callback = CallbackQuery.model_validate({
        'id': 'abc',
        'from': {'id': 555, 'is_bot': False, 'first_name': 'Test'},
        'chat_instance': 'inst',
        'data': 'm:act:cls:1',
        'message': message.model_copy(),
    })
    master = SimpleNamespace(id=10)

    async def fake_safe_answer(*args, **kwargs):
        print('safe_answer_callback called')

    with patch.object(orders, 'safe_answer_callback', fake_safe_answer):
        await orders.active_close_start(callback=callback, state=state, session=session, master=master)
    print('state:', state.state)
    print('data:', state.data)

asyncio.run(main())
