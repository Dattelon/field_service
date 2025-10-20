# P1-13: Retry Action - QUICKSTART

**Время на прочтение:** 2 минуты  
**Статус:** ✅ Готово к использованию

---

## 🎯 Что это?

Автоматическая система повтора действий при ошибках. Если при клике на кнопку происходит ошибка (сеть, таймаут, БД), пользователь видит:

```
❌ Не удалось выполнить действие
[🔄 Повторить] [❌ Отменить]
```

---

## 🚀 Уже работает

✅ Подключено к **master_bot**  
✅ Подключено к **admin_bot**  
✅ Перехватывает ошибки в **всех callback handlers**  
✅ Лимит попыток: **3**  
✅ Автоматическое логирование

**Вам ничего делать не нужно!** Система работает из коробки.

---

## 📝 Как это работает

### 1. Пользователь нажимает кнопку
```python
# Любой callback handler
@router.callback_query(F.data.startswith("adm:o:assign"))
async def assign_master(callback: CallbackQuery, ...):
    # Ваш код может упасть с ошибкой
    await some_db_operation()  # 💥 Timeout!
```

### 2. RetryMiddleware перехватывает ошибку
```python
# Автоматически:
# 1. Логирует ошибку
# 2. Сохраняет контекст (callback_data, user_id, attempt=1)
# 3. Показывает UI с кнопками
```

### 3. Пользователь выбирает действие

**Повторить:**
- Загружается сохранённый контекст
- Увеличивается счётчик попыток (1 → 2)
- Повторяется оригинальное действие
- При успехе - контекст очищается

**Отменить:**
- Контекст очищается
- Показывается "✅ Действие отменено"

---

## 🔧 Настройка (опционально)

### Выключить для конкретного бота

```python
# В main.py бота
setup_retry_middleware(dp, enabled=False)  # Выключить
```

### Изменить лимит попыток

```python
# field_service/bots/common/retry_context.py
@dataclass
class RetryContext:
    MAX_ATTEMPTS = 5  # Было 3, стало 5
```

---

## 🧪 Тестирование

### Запустить тесты

```powershell
$env:PYTHONIOENCODING='utf-8'; pytest tests/test_retry_action.py -v
```

### Создать искусственную ошибку

```python
@router.callback_query(F.data == "test:error")
async def test_error(callback: CallbackQuery):
    # Искусственная ошибка для проверки retry
    raise ValueError("Test error for P1-13")
```

Нажмите кнопку с `callback_data="test:error"` и увидите UI retry.

---

## 📊 Мониторинг

### Логи при ошибке

```
ERROR [retry_middleware] Error in callback handler: adm:o:assign:123:456
exc_info=(ValueError, "Network timeout", <traceback>)
extra={"user_id": 123, "callback_data": "adm:o:assign:123:456"}
```

### Логи при повторе

```
INFO [retry_handler] Retrying action: adm:o:assign:123:456, attempt 2
extra={"user_id": 123, "callback_data": "...", "attempt": 2}
```

---

## ❓ FAQ

**Q: Это работает для всех кнопок?**  
A: Да, для всех callback handlers в обоих ботах.

**Q: Что если я хочу обработать ошибку по-своему?**  
A: Добавьте try/except в handler - middleware не перехватит обработанные исключения.

**Q: Сколько раз можно повторять?**  
A: 3 раза (MAX_ATTEMPTS). После этого показывается "Превышено максимальное количество попыток".

**Q: Работает ли для message handlers?**  
A: Нет, только для callback_query. Message handlers не перехватываются.

**Q: Где хранится контекст?**  
A: В FSM state пользователя. Очищается автоматически при успехе или отмене.

---

## 📚 Полная документация

См. `docs/P1-13_RETRY_ACTION.md`

---

**Дата:** 2025-10-09  
**Статус:** ✅ Production Ready
