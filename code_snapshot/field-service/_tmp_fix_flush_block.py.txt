from pathlib import Path

path = Path('field-service/tests/conftest.py')
text = path.read_text(encoding='utf-8')
old = "    async def flush(self, objects=None):\n        if objects is None:\n            orders_to_flush = [\n                obj for obj in self.sync_session.new\n                if isinstance(obj, m.orders)\n            ]\n            if orders_to_flush:\n                await super().flush(orders_to_flush)\n        await super().flush(objects)\n"
new = "    async def flush(self, objects=None):\n        if objects is None:\n            orders_to_flush = [\n                obj for obj in self.sync_session.new\n                if isinstance(obj, m.orders)\n            ]\n            if orders_to_flush:\n                print('pre-flush orders', len(orders_to_flush))\n                await super().flush(orders_to_flush)\n        await super().flush(objects)\n"
if old in text:
    text = text.replace(old, new, 1)
    path.write_text(text, encoding='utf-8')
else:
    raise SystemExit('Old block not found')
