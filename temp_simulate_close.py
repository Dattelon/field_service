import sys
sys.path.append('c:/ProjectF/field-service')
import asyncio
from types import SimpleNamespace
from unittest.mock import patch
from field_service.bots.master_bot.handlers import orders
from field_service.db import models as m

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

class FakeMessage:
    def __init__(self):
        self.sent = []
    async def answer(self, text):
        self.sent.append(text)

class FakeCallback:
    def __init__(self, order_id, message):
        self.data = f"m:act:cls:{order_id}"
        self.message = message
        self.from_user = SimpleNamespace(id=123)
        self.bot = SimpleNamespace()

async def main():
    fake_order = SimpleNamespace(id=1, assigned_master_id=10, status=m.OrderStatus.WORKING, order_type=m.OrderType.NORMAL)
    class FakeSession:
        async def get(self, model, order_id):
            return fake_order
    session = FakeSession()
    state = FakeState()
    message = FakeMessage()
    callback = FakeCallback(1, message)
    master = SimpleNamespace(id=10)

    async def fake_safe_answer(*args, **kwargs):
        pass

    with patch.object(orders, 'safe_answer_callback', fake_safe_answer):
        await orders.active_close_start(callback=callback, state=state, session=session, master=master)
    print('messages:', message.sent)
    print('state:', state.state)
    print('data:', state.data)

asyncio.run(main())
