# 🚀 БЫСТРЫЙ СТАРТ - Telegram UI Testing

## ✅ ВСЁ ГОТОВО К РАБОТЕ!

Автоматизированное тестирование Telegram ботов **полностью настроено** и работает.

---

## 📋 Проверка что всё работает (30 секунд)

```powershell
cd C:\ProjectF
$env:PYTHONPATH='C:\ProjectF'
python tests\telegram_ui\test_quick_check.py
```

**Ожидаемый результат:**
```
Мастер-бот: ✅ OK
Админ-бот: ✅ OK
```

Если видите ✅ - всё отлично!

---

## 💻 Базовое использование

### Пример теста
```python
import pytest
from tests.telegram_ui.bot_client import BotTestClient

@pytest.mark.asyncio
async def test_master_bot_start():
    async with BotTestClient() as client:
        # Отправляем /start
        msg = await client.send_command("BotZaMaster_bot", "/start")
        
        # Проверяем ответ
        assert "Field Service" in msg.text
        assert msg.buttons  # Есть кнопки
        
        # Проверяем конкретную кнопку
        client.assert_has_buttons(["Заполнить анкету"], msg)
```

### Запуск тестов
```powershell
cd C:\ProjectF
pytest tests\telegram_ui\test_your_test.py -v
```

---

## 🔧 Что уже работает

✅ **Отправка команд боту**
```python
msg = await client.send_command("BotZaMaster_bot", "/start")
```

✅ **Проверка текста**
```python
assert "Field Service" in msg.text
```

✅ **Проверка кнопок**
```python
assert len(msg.buttons) == 1
client.assert_has_buttons(["Кнопка 1", "Кнопка 2"], msg)
```

✅ **Нажатие на кнопку**
```python
msg = await client.click_button("Заполнить анкету", "BotZaMaster_bot")
```

---

## 📁 Файлы

| Файл | Описание |
|------|----------|
| `config.py` | Конфигурация (API credentials, bot usernames) |
| `bot_client.py` | Главный helper-класс для тестов |
| `test_quick_check.py` | Скрипт проверки связи с ботами |
| `test_session.session` | Файл сессии (НЕ коммитить!) |
| `SUCCESS_REPORT.md` | Полный отчёт о проделанной работе |

---

## ⚠️ Если что-то не работает

### 1. Боты не отвечают?
Проверьте что боты запущены:
```powershell
# Посмотреть Python процессы
Get-Process python*

# Если не запущены - запустите:
cd C:\ProjectF\field-service
python -m field_service.bots.master_bot.main   # В одном окне
python -m field_service.bots.admin_bot.main    # В другом окне
```

### 2. Ошибка "Сессия не авторизована"?
Создайте сессию заново:
```powershell
cd C:\ProjectF
$env:PYTHONPATH='C:\ProjectF'
python tests\telegram_ui\setup_client.py
```

### 3. Import ошибки?
Проверьте PYTHONPATH:
```powershell
$env:PYTHONPATH='C:\ProjectF'
```

---

## 📊 Реальные ответы ботов

### Мастер-бот
**Команда:** `/start`
```
**Field Service — мастер**
Статус анкеты: На модерации

Добро пожаловать в Field Service! 
Ваша анкета отправлена на модерацию...
```
**Кнопки:** `Заполнить анкету`

### Админ-бот  
**Команда:** `/start`
```
Добро пожаловать в Field Service. Выберите раздел:
```
**Кнопки:** `📦 Заявки`, `🧾 Логи`

---

## 🎯 Что делать дальше

1. **Изучите примеры:** `test_mock_examples.py`
2. **Напишите свои тесты** для конкретных сценариев
3. **Интегрируйте в CI/CD** pipeline
4. **Добавьте больше проверок** (статусы, финансы, etc.)

---

## 📚 Полная документация

Смотрите: `SUCCESS_REPORT.md` - полный отчёт со всеми деталями

---

**Всё готово для написания тестов! 🚀**
