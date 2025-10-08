# Quick Start - Telegram UI Testing

## 🚀 Быстрый старт (3 шага)

### Шаг 1: Авторизация (один раз)

```powershell
cd C:\ProjectF
python tests\telegram_ui\setup_client.py
```

Введите:
1. Номер телефона: `+79991234567`
2. Код из SMS/Telegram
3. Пароль 2FA (если есть)

✅ После этого создастся файл `test_session.session`

---

### Шаг 2: Настройка ботов

Отредактируйте `config.py` или создайте `.env`:

```python
# В config.py укажите username ботов:
MASTER_BOT_USERNAME = "your_master_bot"  # БЕЗ @
ADMIN_BOT_USERNAME = "your_admin_bot"    # БЕЗ @
```

Или создайте `.env`:
```env
MASTER_BOT_USERNAME=your_master_bot
ADMIN_BOT_USERNAME=your_admin_bot
```

---

### Шаг 3: Запуск тестов

```powershell
# Все тесты
pytest tests\telegram_ui\test_master_onboarding.py -v

# С логами
pytest tests\telegram_ui\test_master_onboarding.py -v -s

# Один тест
pytest tests\telegram_ui\test_master_onboarding.py::test_master_start_command -v
```

---

## 📝 Пример теста

```python
@pytest.mark.asyncio
async def test_example():
    async with BotTestClient() as client:
        # Отправить /start
        msg = await client.send_command("bot_username", "/start")
        
        # Проверить текст
        client.assert_text_in_message("Привет", msg)
        
        # Нажать кнопку
        msg = await client.click_button("Кнопка", "bot_username")
```

---

## ⚡ Теперь я могу сам тестировать ботов!

После настройки я смогу запускать тесты через PowerShell:

```powershell
# Я выполню это через MCP Desktop Commander
pytest tests\telegram_ui\test_master_onboarding.py -v -s
```

**Без вашего участия!** 🎉
