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
# TEST PHONE NUMBER
# ==========================================
# Номер телефона для тестового аккаунта
# Формат: +79991234567
TEST_PHONE = os.getenv("TELEGRAM_TEST_PHONE", "")  # Заполнить при первом запуске

# ==========================================
# SESSION FILE
# ==========================================
# Файл с сохраненной сессией (создастся автоматически после авторизации)
SESSION_FILE = Path(__file__).parent / "test_session.session"

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
    
    if not TEST_PHONE:
        errors.append("TEST_PHONE не указан. Укажите в переменной окружения TELEGRAM_TEST_PHONE")
    
    if not MASTER_BOT_USERNAME:
        errors.append("MASTER_BOT_USERNAME не указан. Укажите в переменной окружения MASTER_BOT_USERNAME")
    
    if not ADMIN_BOT_USERNAME:
        errors.append("ADMIN_BOT_USERNAME не указан. Укажите в переменной окружения ADMIN_BOT_USERNAME")
    
    if errors:
        raise ValueError(
            "Ошибки конфигурации:\n" + "\n".join(f"  - {e}" for e in errors)
        )

if __name__ == "__main__":
    print("=== Telegram UI Testing Configuration ===")
    print(f"API ID: {API_ID}")
    print(f"API Hash: {API_HASH[:8]}...")
    print(f"Test Phone: {TEST_PHONE or '❌ НЕ УКАЗАН'}")
    print(f"Session File: {SESSION_FILE}")
    print(f"Master Bot: @{MASTER_BOT_USERNAME or '❌ НЕ УКАЗАН'}")
    print(f"Admin Bot: @{ADMIN_BOT_USERNAME or '❌ НЕ УКАЗАН'}")
    print()
    
    try:
        validate_config()
        print("✅ Конфигурация валидна!")
    except ValueError as e:
        print(f"❌ {e}")
