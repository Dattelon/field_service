"""
Диагностика проблемы с сессией
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from telethon import TelegramClient
from tests.telegram_ui.config import API_ID, API_HASH, SESSION_FILE


async def test_session():
    print("="*60)
    print("  ДИАГНОСТИКА СЕССИИ")
    print("="*60)
    print()
    print(f"API_ID: {API_ID}")
    print(f"API_HASH: {API_HASH[:8]}...")
    print(f"SESSION_FILE: {SESSION_FILE}")
    print(f"Файл существует: {SESSION_FILE.exists()}")
    print()
    
    # Вариант 1: С расширением
    print("Тест 1: Подключение с полным путём (с .session)")
    session_path_full = str(SESSION_FILE)
    print(f"Путь: {session_path_full}")
    
    client1 = TelegramClient(session_path_full, API_ID, API_HASH)
    try:
        await client1.connect()
        is_auth1 = await client1.is_user_authorized()
        print(f"Результат: {'✅ Авторизован' if is_auth1 else '❌ НЕ авторизован'}")
        if is_auth1:
            me = await client1.get_me()
            print(f"Пользователь: {me.first_name} (ID: {me.id})")
    except Exception as e:
        print(f"❌ Ошибка: {e}")
    finally:
        await client1.disconnect()
    
    print()
    
    # Вариант 2: Без расширения
    print("Тест 2: Подключение без расширения (БЕЗ .session)")
    session_path_no_ext = str(SESSION_FILE).replace('.session', '')
    print(f"Путь: {session_path_no_ext}")
    
    client2 = TelegramClient(session_path_no_ext, API_ID, API_HASH)
    try:
        await client2.connect()
        is_auth2 = await client2.is_user_authorized()
        print(f"Результат: {'✅ Авторизован' if is_auth2 else '❌ НЕ авторизован'}")
        if is_auth2:
            me = await client2.get_me()
            print(f"Пользователь: {me.first_name} (ID: {me.id})")
    except Exception as e:
        print(f"❌ Ошибка: {e}")
    finally:
        await client2.disconnect()
    
    print()
    print("="*60)


if __name__ == "__main__":
    asyncio.run(test_session())
