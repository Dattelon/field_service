"""
Telegram UI Testing Configuration
Настройки для автоматизированного тестирования Telegram-ботов
"""

import os
from pathlib import Path

# ==========================================
# TELEGRAM API CREDENTIALS
# ==========================================
# Получены с https://my.telegram.org/auth
API_ID = 25078350
API_HASH = "f544a1a967172e8cc8a05a0115b98b69"

# ==========================================
# SESSION CONFIGURATION
# ==========================================
# StringSession для надежного подключения (более стабильно чем файловая сессия)
SESSION_STRING = "1ApWapzMBu2k9f1PKZu0sdT3q06Oa35jBdE5w6SjD6MFZAReNr0irKbYqw0nF-vqb6k67tLiap7I6W-evugFk5YKUShS9SftGOcDjxKi08jyVXNN1HI5fhsS7XTZJS7FcSOruSofx65vi-hVMGtJE-PJPLt5fzvsTzPW2y2Q2oxkwgyF8-Sk379NUKIwOuCvGZmJLi3YeB6MsoQ6hQNRUwHeltB-ajKxjeI_CeZcbFFSaMA3UPlkVN0UkpsRMe3BS86ZfTN3aVk1BgJ3KTZlIMs7rAZQbs-BaplTwFiNJSVlZh950kX6WG93yciOnUswYXsBEESy0QKGT2kVW274spEKKzOlYdls="

# Старая файловая сессия (оставлено для совместимости, но не используется)
SESSION_FILE = Path(__file__).parent / "test_session.session"

# ==========================================
# TEST PHONE NUMBER
# ==========================================
# Номер телефона для тестового аккаунта
# Формат: +79991234567
TEST_PHONE = os.getenv("TELEGRAM_TEST_PHONE", "+79031751130")

# ==========================================
# BOT USERNAMES
# ==========================================
# Username ботов для тестирования (БЕЗ @)
MASTER_BOT_USERNAME = os.getenv("MASTER_BOT_USERNAME", "BotZaMaster_bot")
ADMIN_BOT_USERNAME = os.getenv("ADMIN_BOT_USERNAME", "sportsforecastbot_bot")

# ==========================================
# TEST TIMEOUTS
# ==========================================
# Таймауты для ожидания ответов от ботов
MESSAGE_TIMEOUT = 10  # секунд на ожидание сообщения от бота
BUTTON_CLICK_DELAY = 1  # секунд задержки после клика по кнопке

# ==========================================
# TEST DATA
# ==========================================
# Тестовые данные для заполнения форм
TEST_MASTER_PHONE = "+79991234567"
TEST_MASTER_NAME = "Тест Мастеров"
TEST_CITY = "Москва"
TEST_DISTRICT = "ЦАО"  # Центральный административный округ

# ==========================================
# VALIDATION
# ==========================================
def validate_config():
    """Проверка наличия всех необходимых настроек"""
    errors = []
    
    if not SESSION_STRING:
        errors.append("SESSION_STRING не указан")
    
    if not MASTER_BOT_USERNAME:
        errors.append("MASTER_BOT_USERNAME не указан")
    
    if not ADMIN_BOT_USERNAME:
        errors.append("ADMIN_BOT_USERNAME не указан")
    
    if errors:
        raise ValueError(
            "Ошибки конфигурации:\n" + "\n".join(f"  - {e}" for e in errors)
        )

if __name__ == "__main__":
    print("=== Telegram UI Testing Configuration ===")
    print(f"API ID: {API_ID}")
    print(f"API Hash: {API_HASH[:8]}...")
    print(f"Session String: {SESSION_STRING[:20]}...")
    print(f"Master Bot: @{MASTER_BOT_USERNAME}")
    print(f"Admin Bot: @{ADMIN_BOT_USERNAME}")
    print()
    
    try:
        validate_config()
        print("OK - Configuration valid!")
    except ValueError as e:
        print(f"ERROR: {e}")
