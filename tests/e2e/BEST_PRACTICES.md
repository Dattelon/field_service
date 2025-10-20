# 🎓 BEST PRACTICES & EXAMPLES

## 📚 Содержание

1. [Лучшие практики написания тестов](#лучшие-практики)
2. [Примеры использования](#примеры-использования)
3. [Частые ошибки](#частые-ошибки)
4. [Паттерны тестирования](#паттерны-тестирования)
5. [Оптимизация тестов](#оптимизация)

---

## 🎯 Лучшие практики

### 1. **Один тест = один сценарий**

❌ **Плохо:**
```python
async def test_everything():
    # Создание заказа
    # Автораспределение
    # Выполнение
    # Отмены
    # Споры
    # ... 500 строк
```

✅ **Хорошо:**
```python
async def test_scenario_1_happy_path():
    """Фокус на одном happy path"""
    pass

async def test_scenario_2_cancellation():
    """Отдельный тест для отмен"""
    pass
```

---

### 2. **Детальное логирование**

❌ **Плохо:**
```python
order = create_order()
assert order.status == "created"
```

✅ **Хорошо:**
```python
log.action("Клиент", "Создаёт заказ")
log.db_write("orders", "INSERT", {"status": "created"})
log.assertion("Заказ создан", order.status == "created")
```

**Почему:** При падении теста вы сразу видите где и почему упало.

---

### 3. **Проверяйте побочные эффекты**

❌ **Плохо:**
```python
await master.accept_order(5001)
assert order.status == "assigned"
```

✅ **Хорошо:**
```python
await master.accept_order(5001)

# Проверка заказа
assert order.status == "assigned"
assert order.master_id == 2001

# Проверка уведомлений
assert "Мастер найден" in client.get_last_message()
assert "Вы приняли" in master.get_last_message()

# Проверка БД
assignment = db.get_assignment_attempt(5001)
assert assignment.sla_met == True
```

---

### 4. **Изолируйте тесты**

❌ **Плохо:**
```python
# test_1 создаёт order_id=5001
# test_2 рассчитывает на order_id=5001
```

✅ **Хорошо:**
```python
@pytest.fixture
async def fresh_order(db):
    """Каждый тест получает свой заказ"""
    order = db.insert_test_order()
    yield order
    db.cleanup()
```

---

### 5. **Тестируйте граничные случаи**

```python
@pytest.mark.parametrize("sla_seconds,expected_met", [
    (119, True),   # Граница: 119s < 120s
    (120, True),   # Ровно SLA
    (121, False),  # Превышение на 1s
    (0, True),     # Мгновенно
    (300, False),  # Сильное превышение
])
async def test_sla_boundaries(sla_seconds, expected_met):
    # ...
```

---

## 💡 Примеры использования

### Пример 1: Тест с таймаутами

```python
@pytest.mark.asyncio
@pytest.mark.timeout(60)  # Максимум 60 секунд
async def test_autoassign_timeout():
    log = TestLogger()
    
    # Создание заказа
    order = create_order()
    
    # Запуск автораспределения с таймаутом
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(
            autoassign(order.id),
            timeout=10.0
        )
```

---

### Пример 2: Параметризованный тест

```python
@pytest.mark.parametrize("amount,commission_rate,expected_payout", [
    (100, 0.50, 50),   # Обычная комиссия
    (100, 0.60, 40),   # Просрочка
    (100, 0.00, 100),  # Гарантийка
    (0, 0.50, 0),      # Бесплатно
])
async def test_commission_calculation(amount, commission_rate, expected_payout):
    log = TestLogger()
    
    payout = calculate_payout(amount, commission_rate)
    
    log.assertion(
        f"Выплата {amount}€ с комиссией {commission_rate*100}% = {expected_payout}€",
        payout == expected_payout
    )
```

---

### Пример 3: Тест с моками внешних API

```python
@pytest.fixture
def mock_payment_gateway():
    """Мок платёжного шлюза"""
    with patch('payment.gateway.process_payment') as mock:
        mock.return_value = {"status": "success", "transaction_id": "TXN123"}
        yield mock

async def test_payment_processing(mock_payment_gateway):
    log = TestLogger()
    
    result = await process_master_payout(master_id=2001, amount=60.00)
    
    # Проверяем что API был вызван
    mock_payment_gateway.assert_called_once_with(
        amount=60.00,
        recipient="master_2001"
    )
    
    log.assertion("Платёж обработан", result['status'] == 'success')
```

---

## 🚫 Частые ошибки

### Ошибка 1: Жёсткая привязка ко времени

❌ **Плохо:**
```python
created_at = datetime(2025, 10, 4, 12, 0, 0)
assert order.created_at == created_at
```

✅ **Хорошо:**
```python
# Проверяем относительное время
assert order.created_at >= datetime.now() - timedelta(seconds=5)
assert order.created_at <= datetime.now()
```

---

### Ошибка 2: Игнорирование асинхронности

❌ **Плохо:**
```python
send_notification(user_id=1000, text="Тест")
message = get_last_message(user_id=1000)  # None!
```

✅ **Хорошо:**
```python
await send_notification(user_id=1000, text="Тест")
await asyncio.sleep(0.1)  # Даём время на обработку
message = get_last_message(user_id=1000)
```

---

### Ошибка 3: Забыть cleanup

❌ **Плохо:**
```python
async def test_something():
    db.insert_test_order()
    # ... тест
    # Данные остались в БД!
```

✅ **Хорошо:**
```python
async def test_something(db):
    order = db.insert_test_order()
    try:
        # ... тест
    finally:
        db.delete_order(order.id)

# Или через фикстуру с autouse
@pytest.fixture(autouse=True)
async def cleanup_db(db):
    yield
    db.reset()
```

---

## 🎨 Паттерны тестирования

### Паттерн 1: Page Object для ботов

```python
class MasterBotPage:
    """Абстракция над мастер-ботом"""
    
    def __init__(self, bot):
        self.bot = bot
    
    async def open_orders_list(self, master_id):
        await self.bot.send_message(master_id, "/orders")
        return await self.bot.get_last_message(master_id)
    
    async def accept_order(self, master_id, order_id):
        await self.bot.click_button(f"accept_order:{order_id}", master_id)

# Использование
async def test_with_page_object():
    master_page = MasterBotPage(bot_master)
    await master_page.accept_order(2001, 5001)
```

---

### Паттерн 2: Builder для тестовых данных

```python
class OrderBuilder:
    """Построитель заказов для тестов"""
    
    def __init__(self):
        self._order = {
            "client_id": 1000,
            "status": "searching",
            "city_id": 1
        }
    
    def with_client(self, client_id):
        self._order["client_id"] = client_id
        return self
    
    def in_status(self, status):
        self._order["status"] = status
        return self
    
    def assigned_to(self, master_id):
        self._order["master_id"] = master_id
        self._order["status"] = "assigned"
        return self
    
    def build(self):
        return self._order

# Использование
order = (OrderBuilder()
    .with_client(1005)
    .assigned_to(2010)
    .build())
```

---

### Паттерн 3: Fixture factories

```python
@pytest.fixture
def order_factory(db):
    """Фабрика заказов"""
    
    def _make_order(**kwargs):
        default = {
            "client_id": 1000,
            "status": "searching",
            "city_id": 1
        }
        default.update(kwargs)
        return db.insert_test_order(**default)
    
    return _make_order

# Использование
async def test_with_factory(order_factory):
    order1 = order_factory(status="assigned")
    order2 = order_factory(client_id=2000, status="completed")
```

---

## ⚡ Оптимизация тестов

### 1. Параллельный запуск

```bash
# Установка
pip install pytest-xdist

# Запуск на 4 ядрах
pytest -n 4
```

---

### 2. Кэширование фикстур

```python
@pytest.fixture(scope="session")  # Один раз на всю сессию
async def db_connection():
    conn = await create_connection()
    yield conn
    await conn.close()

@pytest.fixture(scope="module")  # Один раз на модуль
async def test_data():
    return load_test_data()
```

---

### 3. Пропуск медленных тестов

```python
@pytest.mark.slow
async def test_long_autoassign():
    # Долгий тест
    pass

# Запуск без медленных тестов
# pytest -m "not slow"
```

---

### 4. Группировка тестов

```python
class TestOrderCreation:
    """Группа тестов создания заказа"""
    
    async def test_valid_address(self):
        pass
    
    async def test_invalid_address(self):
        pass
    
    async def test_time_slot_selection(self):
        pass
```

---

## 📊 Метрики качества тестов

### Хороший E2E тест:

✅ **Запускается за < 30 секунд**  
✅ **Покрывает один чёткий сценарий**  
✅ **Независим от других тестов**  
✅ **Детально логирует действия**  
✅ **Проверяет побочные эффекты**  
✅ **Легко читается и понимается**  
✅ **Использует моки для внешних зависимостей**

---

## 🎓 Дополнительное чтение

- [Pytest Async Documentation](https://pytest-asyncio.readthedocs.io/)
- [Testing Best Practices](https://testdriven.io/blog/testing-best-practices/)
- [E2E Testing Patterns](https://martinfowler.com/articles/practical-test-pyramid.html)

---

**Совет:** Начните с простых тестов, постепенно усложняя. Лучше 10 простых тестов, чем 1 сложный!
