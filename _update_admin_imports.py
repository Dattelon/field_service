from pathlib import Path

path = Path('field-service/field_service/bots/admin_bot/handlers.py')
text = path.read_text(encoding='utf-8')
replacements = [
    ("from dataclasses import dataclass", "import csv\nimport io\nfrom dataclasses import dataclass"),
    ("from enum import Enum", "from datetime import datetime, timezone, timedelta\nfrom enum import Enum"),
    ("from typing import Protocol, Optional, Sequence, Iterable, Any, Mapping", "from typing import Protocol, Optional, Sequence, Iterable, Any, Mapping")
]
for old, new in replacements:
    if old in text and new not in text:
        text = text.replace(old, new, 1)
if 'from aiogram.fsm.context import FSMContext\n' not in text:
    text = text.replace('from aiogram import Router, F\n', 'from aiogram import Router, F\nfrom aiogram.fsm.context import FSMContext\nfrom aiogram.fsm.state import State, StatesGroup\n')
if 'from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup\nfrom aiogram.utils.keyboard import InlineKeyboardBuilder\nfrom aiogram.types import ReplyKeyboardRemove' in text:
    text = text.replace(
        'from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup\nfrom aiogram.utils.keyboard import InlineKeyboardBuilder\nfrom aiogram.types import ReplyKeyboardRemove',
        'from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup\nfrom aiogram.types import BufferedInputFile, ReplyKeyboardRemove\nfrom aiogram.utils.keyboard import InlineKeyboardBuilder'
    )
if 'from sqlalchemy import' in text:
    pass
else:
    text = text.replace('\n\n# === \u0414\u0435\u041d\u0443\u0452\u0431\u0435\u043b\u044c\u043d", '# ???',) # placeholder to avoid messing??
# Instead ensure select/func import appended
if 'from sqlalchemy import func, select\n' not in text:
    text = text.replace('from aiogram.types import BufferedInputFile, ReplyKeyboardRemove\nfrom aiogram.utils.keyboard import InlineKeyboardBuilder\n', 'from aiogram.types import BufferedInputFile, ReplyKeyboardRemove\nfrom aiogram.utils.keyboard import InlineKeyboardBuilder\n\nfrom sqlalchemy import func, select\n')
path.write_text(text, encoding='utf-8')
