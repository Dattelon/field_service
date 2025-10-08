"""
Скрипт первичной авторизации в Telegram
Запустить ОДИН РАЗ для создания сессии
"""

import asyncio
import sys
from pathlib import Path

# Добавляем путь к проекту
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from telethon import TelegramClient
from tests.telegram_ui.config import API_ID, API_HASH, SESSION_FILE


async def setup_telegram_client():
    """Первичная авторизация в Telegram"""
    
    print("=" * 60)
    print("   TELEGRAM UI TESTING - ПЕРВИЧНАЯ АВТОРИЗАЦИЯ")
    print("=" * 60)
    print()
    print("Этот скрипт нужно запустить ОДИН РАЗ для создания сессии.")
    print("После успешной авторизации файл сессии будет сохранен,")
    print("и повторная авторизация не потребуется.")
    print()
    print("-" * 60)
    print()
    
    # Запрашиваем номер телефона
    phone = input("Введите номер телефона (формат +79991234567): ").strip()
    
    if not phone.startswith("+"):
        print("❌ Номер должен начинаться с +")
        return False
    
    print()
    print(f"📱 Подключаемся к Telegram с номером {phone}...")
    print()
    
    # Создаем клиента (TelegramClient автоматически добавит .session к пути)
    session_name = str(SESSION_FILE).replace('.session', '')
    client = TelegramClient(session_name, API_ID, API_HASH)
    
    try:
        await client.start(
            phone=phone,
            code_callback=lambda: input("Введите код из Telegram: ").strip(),
            password=lambda: input("Введите пароль 2FA (если есть): ").strip()
        )
        
        # Проверяем авторизацию
        me = await client.get_me()
        
        print()
        print("=" * 60)
        print("✅ АВТОРИЗАЦИЯ УСПЕШНА!")
        print("=" * 60)
        print(f"👤 Имя: {me.first_name} {me.last_name or ''}")
        print(f"📞 Телефон: {me.phone}")
        print(f"🆔 User ID: {me.id}")
        print()
        print(f"💾 Файл сессии сохранен: {SESSION_FILE}")
        print()
        print("Теперь можно запускать UI-тесты!")
        print("=" * 60)
        
        return True
        
    except Exception as e:
        print()
        print("=" * 60)
        print("❌ ОШИБКА АВТОРИЗАЦИИ")
        print("=" * 60)
        print(f"Причина: {e}")
        print()
        print("Возможные решения:")
        print("  1. Проверьте правильность номера телефона")
        print("  2. Проверьте код из SMS/Telegram")
        print("  3. Если есть 2FA - введите правильный пароль")
        print("  4. Попробуйте еще раз через несколько минут")
        print("=" * 60)
        return False
        
    finally:
        await client.disconnect()


if __name__ == "__main__":
    success = asyncio.run(setup_telegram_client())
    sys.exit(0 if success else 1)
