from aiogram.types import Message

message = Message.model_validate({
    'message_id': 1,
    'date': 0,
    'chat': {'id': 1, 'type': 'private'},
    'from': {'id': 1, 'is_bot': False, 'first_name': 'Test'},
    'text': 'hi',
})
try:
    message.answer('test')
except Exception as exc:
    print('error:', exc)
