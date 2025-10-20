"""
Прямой тест подключения к боту БЕЗ класса-обёртки
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from telethon import TelegramClient
from tests.telegram_ui.config import API_ID, API_HASH, SESSION_FILE, MASTER_BOT_USERNAME


async def direct_test():
    print("="*60)
    print("  ПРЯМОЙ ТЕСТ ПОДКЛЮЧЕНИЯ К БОТУ")
    print("="*60)
    print()
    
    # Путь БЕЗ расширения .session
    session_name = str(SESSION_FILE).replace('.session', '')
    print(f"Session path: {session_name}")
    print(f"File exists: {SESSION_FILE.exists()}")
    print()
    
    # Создаём клиента
    client = TelegramClient(session_name, API_ID, API_HASH)
    
    try:
        print("Подключаемся...")
        await client.connect()
        
        print("Проверяем авторизацию...")
        if not await client.is_user_authorized():
            print("❌ НЕ авторизован!")
            return
        
        print("✅ Авторизован!")
        
        me = await client.get_me()
        print(f"Пользователь: {me.first_name} (@{me.username})")
        print()
        
        # Отправляем /start мастер-боту
        print(f"Отправляем /start боту @{MASTER_BOT_USERNAME}...")
        await client.send_message(MASTER_BOT_USERNAME, "/start")
        
        print("Ждём ответ (10 секунд)...")
        await asyncio.sleep(10)
        
        # Получаем последнее сообщение от бота
        async for message in client.iter_messages(MASTER_BOT_USERNAME, limit=1):
            print()
            print("="*60)
            print("ОТВЕТ ОТ БОТА:")
            print("="*60)
            print(message.text)
            print("="*60)
            
            if message.buttons:
                print(f"\nКнопок: {len(message.buttons)}")
                for i, row in enumerate(message.buttons):
                    for button in row:
                        print(f"  [{i}] {button.text}")
        
        print("\n✅ ТЕСТ ЗАВЕРШЁН!")
        
    except Exception as e:
        print(f"\n❌ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(direct_test())
