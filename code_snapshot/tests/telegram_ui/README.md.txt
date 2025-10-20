# Telegram UI Testing

Автоматизированное тестирование Telegram-ботов через пользовательский клиент.

## 🎯 Что это дает

- ✅ **Автоматическое тестирование** ботов без ручного клика
- ✅ **Проверка реального UI** (кнопки, сообщения, переходы)
- ✅ **Интеграция с CI/CD** (можно запускать автоматически)
- ✅ **Быстрая регрессия** всех сценариев

## 📋 Первоначальная настройка

### 1. Получение API credentials

✅ **УЖЕ СДЕЛАНО!** Ваши credentials:
- `api_id`: 25078350
- `api_hash`: f544a1a9571728cc8a05a0113898e69

### 2. Первичная авторизация

Запустите **ОДИН РАЗ** скрипт авторизации:

```powershell
cd C:\ProjectF
python tests\telegram_ui\setup_client.py
```

**Что произойдет:**
1. Скрипт запросит ваш номер телефона (формат: +79991234567)
2. Telegram отправит код подтверждения
3. Введете код из SMS/Telegram
4. Если есть 2FA - введете пароль
5. Создастся файл `test_session.session` с сохраненной сессией

**После этого повторная авторизация НЕ требуется!**

### 3. Настройка переменных окружения

Создайте файл `.env` в корне проекта:

```env
# Телефон тестового аккаунта
TELEGRAM_TEST_PHONE=+79991234567

# Username ботов (без @)
MASTER_BOT_USERNAME=your_master_bot
ADMIN_BOT_USERNAME=your_admin_bot
```

## 🚀 Запуск тестов

### Все тесты онбординга мастера
```powershell
cd C:\ProjectF
pytest tests\telegram_ui\test_master_onboarding.py -v
```

### Конкретный тест
```powershell
pytest tests\telegram_ui\test_master_onboarding.py::test_master_start_command -v
```

### С выводом логов
```powershell
pytest tests\telegram_ui\test_master_onboarding.py -v -s
```

## 📝 Написание тестов

### Базовый шаблон

```python
import pytest
from tests.telegram_ui.bot_client import BotTestClient
from tests.telegram_ui.config import MASTER_BOT_USERNAME

@pytest.mark.asyncio
async def test_my_scenario():
    async with BotTestClient() as client:
        # Отправить команду
        message = await client.send_command(MASTER_BOT_USERNAME, "/start")
        
        # Проверить текст
        client.assert_text_in_message("Ожидаемый текст", message)
        
        # Проверить кнопки
        client.assert_has_buttons(["Кнопка 1", "Кнопка 2"], message)
        
        # Нажать кнопку
        message = await client.click_button("Кнопка 1", MASTER_BOT_USERNAME)
```


### Доступные методы BotTestClient

```python
# Отправка команд
await client.send_command(bot_username, "/start")
await client.send_command(bot_username, "Любой текст")

# Клик по кнопкам
await client.click_button("Текст кнопки", bot_username)

# Получение последнего сообщения
message = await client.get_last_message(bot_username)

# Проверки
client.assert_text_in_message("Искомый текст")
client.assert_has_buttons(["Кнопка 1", "Кнопка 2"])
```

## 🛠 Troubleshooting

### "Файл сессии не найден"
**Решение:** Запустите `python tests\telegram_ui\setup_client.py`

### "Кнопка не найдена"
**Причина:** Текст кнопки указан неправильно (учитывается регистр и эмодзи)
**Решение:** Проверьте точный текст кнопки в боте, включая эмодзи

### "Timeout при ожидании сообщения"
**Причина:** Бот не ответил за 10 секунд
**Решение:** 
- Проверьте, запущен ли бот
- Увеличьте `MESSAGE_TIMEOUT` в `config.py`

### "FloodWaitError"
**Причина:** Слишком много запросов к Telegram API
**Решение:** Подождите указанное время или увеличьте задержки между запросами

## 📁 Структура файлов

```
tests/telegram_ui/
├── README.md              # Эта документация
├── config.py              # Настройки (credentials, usernames)
├── setup_client.py        # Скрипт первичной авторизации
├── bot_client.py          # Helper-класс для работы с ботами
├── test_master_onboarding.py  # Тесты онбординга мастера
└── test_session.session   # Файл сессии (создается автоматически)
```

## 🔒 Безопасность

- ❌ **НЕ коммитьте** файл `test_session.session` в Git
- ❌ **НЕ коммитьте** файл `.env` с реальными данными
- ✅ Используйте **отдельный тестовый аккаунт** Telegram
- ✅ Храните credentials в переменных окружения

## 💡 Best Practices

1. **Изоляция тестов** - каждый тест должен быть независимым
2. **Cleanup** - сбрасывайте состояние бота перед/после тестов
3. **Таймауты** - используйте разумные таймауты ожидания
4. **Логирование** - используйте `-s` флаг для отладки
5. **Переиспользование** - создавайте helper-функции для частых сценариев

## 📊 Примеры сценариев

- ✅ Онбординг мастера (выбор города, района, телефон)
- ✅ Принятие/отклонение заказа
- ✅ Смена статуса мастера (работаю/перерыв/офлайн)
- ✅ Просмотр активных заказов
- ✅ Закрытие заказа и оценка
- ✅ Работа админ-бота (назначение заказа, модерация)

## 🤝 Для разработчиков

При добавлении новых тестов:
1. Используйте `@pytest.mark.asyncio` для async функций
2. Используйте context manager (`async with BotTestClient()`)
3. Добавляйте docstring с описанием сценария
4. Группируйте related тесты в отдельные файлы

---

**Вопросы?** Обращайтесь к тимлиду проекта.
