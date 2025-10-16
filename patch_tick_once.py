# -*- coding: utf-8 -*-
"""Патч для tick_once: делаем все параметры опциональными"""

import re
import sys

# Для Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

def patch_file():
    file_path = r"C:\ProjectF\field-service\field_service\services\distribution_scheduler.py"
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Простой поиск и замена по уникальной строке
    old_signature = "async def tick_once(\n    cfg: DistConfig, \n    *, \n    bot: Bot | None, \n    alerts_chat_id: Optional[int],"
    new_signature = "async def tick_once(\n    cfg: DistConfig, \n    *, \n    bot=None, \n    alerts_chat_id: Optional[int] = None,"
    
    if old_signature not in content:
        print("ОШИБКА: Старая сигнатура не найдена!")
        print("Возможно файл уже изменён или формат не совпадает")
        return False
    
    # Заменяем только сигнатуру
    content_new = content.replace(old_signature, new_signature)
    
    # Также заменим комментарии внутри docstring
    old_doc = '    """\n    Один тик автораспределения.\n    \n    Args:\n        cfg: Конфигурация распределения\n        bot: Telegram bot для уведомлений (опционально)\n        alerts_chat_id: ID канала для алертов (опционально)\n        session: Опциональная сессия БД (для тестов)'
    
    new_doc = '    """\n    Один тик автораспределения.\n    \n    ВАЖНО: Все параметры кроме cfg - опциональные.\n    \n    Args:\n        cfg: Конфигурация распределения\n        bot: Telegram bot для уведомлений (опционально, default=None)\n        alerts_chat_id: ID канала для алертов (опционально, default=None)\n        session: Опциональная сессия БД (для тестов, default=None)'
    
    content_new = content_new.replace(old_doc, new_doc)
    
    # Заменим также реализацию на использование context manager
    old_impl = '''    # Если session передан (фикстура) - работаем напрямую,
    # чтобы не нарушить (вложенный SAVEPOINT) - создаём временную.
    if session is not None:
        # Используем переданную сессию без bind, чтобы не нарушить
        # её identity map и nested SAVEPOINT.
        await _tick_once_impl(session, cfg, bot, alerts_chat_id)
    else:
        async with SessionLocal() as session:
            await _tick_once_impl(session, cfg, bot, alerts_chat_id)'''
    
    new_impl = '''    # Используем context manager для работы с опциональной сессией
    async with _maybe_session(session) as s:
        await _tick_once_impl(s, cfg, bot, alerts_chat_id)'''
    
    content_new = content_new.replace(old_impl, new_impl)
    
    # Сохраняем
    with open(file_path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(content_new)
    
    print("Файл успешно обновлён!")
    print(f"Изменён: {file_path}")
    return True

if __name__ == "__main__":
    success = patch_file()
    sys.exit(0 if success else 1)
