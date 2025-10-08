"""
Быстрая проверка работоспособности Telegram UI Testing
"""

import asyncio
from tests.telegram_ui.bot_client import BotTestClient
from tests.telegram_ui.config import MASTER_BOT_USERNAME, ADMIN_BOT_USERNAME


async def test_master_bot_connection():
    """Простая проверка связи с мастер-ботом"""
    print("\n" + "="*60)
    print("  ПРОВЕРКА СВЯЗИ С МАСТЕР-БОТОМ")
    print("="*60)
    
    async with BotTestClient() as client:
        print(f"\n📤 Отправляем /start боту @{MASTER_BOT_USERNAME}...")
        
        try:
            message = await client.send_command(MASTER_BOT_USERNAME, "/start")
            
            print(f"\n✅ Получен ответ от бота!")
            print(f"\n📩 Текст ответа (первые 200 символов):")
            print("-" * 60)
            print(message.text[:200])
            print("-" * 60)
            
            if message.buttons:
                print(f"\n🔘 Найдено кнопок: {sum(len(row) for row in message.buttons)}")
                print("\nСписок кнопок:")
                for i, row in enumerate(message.buttons):
                    for j, button in enumerate(row):
                        print(f"  [{i},{j}] {button.text}")
            else:
                print("\n⚠️ Кнопок в сообщении не обнаружено")
            
            print("\n" + "="*60)
            print("✅ ПРОВЕРКА ПРОЙДЕНА УСПЕШНО!")
            print("="*60)
            return True
            
        except Exception as e:
            print(f"\n❌ ОШИБКА: {e}")
            print("\nВозможные причины:")
            print("  1. Бот не запущен")
            print("  2. Username бота указан неправильно")
            print("  3. Бот не отвечает на команды")
            print("="*60)
            return False


async def test_admin_bot_connection():
    """Простая проверка связи с админ-ботом"""
    print("\n" + "="*60)
    print("  ПРОВЕРКА СВЯЗИ С АДМИН-БОТОМ")
    print("="*60)
    
    async with BotTestClient() as client:
        print(f"\n📤 Отправляем /start боту @{ADMIN_BOT_USERNAME}...")
        
        try:
            message = await client.send_command(ADMIN_BOT_USERNAME, "/start")
            
            print(f"\n✅ Получен ответ от бота!")
            print(f"\n📩 Текст ответа (первые 200 символов):")
            print("-" * 60)
            print(message.text[:200])
            print("-" * 60)
            
            if message.buttons:
                print(f"\n🔘 Найдено кнопок: {sum(len(row) for row in message.buttons)}")
                print("\nСписок кнопок:")
                for i, row in enumerate(message.buttons):
                    for j, button in enumerate(row):
                        print(f"  [{i},{j}] {button.text}")
            else:
                print("\n⚠️ Кнопок в сообщении не обнаружено")
            
            print("\n" + "="*60)
            print("✅ ПРОВЕРКА ПРОЙДЕНА УСПЕШНО!")
            print("="*60)
            return True
            
        except Exception as e:
            print(f"\n❌ ОШИБКА: {e}")
            print("\nВозможные причины:")
            print("  1. Бот не запущен")
            print("  2. Username бота указан неправильно")
            print("  3. Бот не отвечает на команды")
            print("="*60)
            return False


if __name__ == "__main__":
    print("\n╔═══════════════════════════════════════════════════════════╗")
    print("║     TELEGRAM UI TESTING - ПРОВЕРКА РАБОТОСПОСОБНОСТИ      ║")
    print("╚═══════════════════════════════════════════════════════════╝")
    
    # Проверяем мастер-бота
    success1 = asyncio.run(test_master_bot_connection())
    
    # Проверяем админ-бота
    success2 = asyncio.run(test_admin_bot_connection())
    
    print("\n" + "="*60)
    print("  ИТОГОВЫЙ РЕЗУЛЬТАТ")
    print("="*60)
    print(f"Мастер-бот: {'✅ OK' if success1 else '❌ FAIL'}")
    print(f"Админ-бот: {'✅ OK' if success2 else '❌ FAIL'}")
    print("="*60)
