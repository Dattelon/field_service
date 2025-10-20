# Quick Start: E2E Тестирование

## ✅ Что уже сделано

### 1. Подготовка БД
- ✅ Назначен глобальный админ (regizdrou)
- ✅ База данных очищена
- ✅ Сохранены города, районы, админы

### 2. Инфраструктура тестов
- ✅ `conftest.py` - фикстуры для БД и Telethon
- ✅ `pytest.ini` - настройки pytest
- ✅ `helpers/` - вспомогательные функции:
  - `master_helpers.py` - работа с мастерами
  - `order_helpers.py` - работа с заказами
  - `admin_helpers.py` - админские действия

### 3. Тесты
- ✅ `test_lifecycle_p0.py` - первый P0 тест (TP-001)

---

## 🔐 Требуется: Авторизация Telethon

**ВАЖНО:** Прежде чем запускать тесты, нужно авторизовать Telethon сессию!

```powershell
cd C:\ProjectF
$env:PYTHONIOENCODING='utf-8'
python tests\telegram_ui\setup_client.py
```

Проверить авторизацию:
```powershell
python tests\telegram_ui\check_session_advanced.py
```

Должно вывести:
```
SUCCESS! Authorization status: AUTHORIZED
User: [имя]
User ID: 6022057382
```

---

## 🚀 Запуск тестов

### Проверка окружения

```powershell
cd C:\ProjectF\tests\telegram_ui
```

1. **БД запущена:**
   ```powershell
   docker ps  # Проверить что field-service-postgres-1 запущен
   ```

2. **Боты запущены:**
   - Мастер-бот должен быть запущен
   - Админ-бот должен быть запущен

3. **Telethon авторизован** (см. выше)

---

### Запуск первого P0 теста

```powershell
cd C:\ProjectF
pytest tests\telegram_ui\test_lifecycle_p0.py::test_tp001_full_order_cycle -v -s
```

**Что произойдет:**
1. Очистка БД (фикстура `clean_db`)
2. Создание 2 мастеров через онбординг
3. Создание заказа через админ-бота
4. Автораспределение офферов
5. Принятие заказа Мастером 1
6. Выполнение работы
7. Финализация админом
8. Проверка комиссии и истории

**Ожидаемое время:** ~60 секунд

---

### Запуск всех P0 тестов

```powershell
pytest tests\telegram_ui\test_lifecycle_p0.py -v -m p0
```

---

### Запуск с подробным выводом

```powershell
pytest tests\telegram_ui\test_lifecycle_p0.py -v -s --tb=short
```

Флаги:
- `-v` - подробный вывод
- `-s` - показывать print() statements
- `--tb=short` - короткий traceback при ошибках

---

## 🐛 Troubleshooting

### "Authorization status: NOT AUTHORIZED"
**Решение:**
```powershell
cd C:\ProjectF
python tests\telegram_ui\setup_client.py
```

### "Connection refused" (PostgreSQL)
**Решение:**
```powershell
cd C:\ProjectF\field-service
docker-compose up -d postgres
```

### "Bot not responding"
**Решение:**
1. Проверить что боты запущены:
   ```powershell
   docker ps  # Должны быть admin-bot и master-bot
   ```
2. Перезапустить боты если нужно:
   ```powershell
   cd C:\ProjectF\field-service
   docker-compose restart admin-bot master-bot
   ```

### "Fixture 'clean_db' not found"
**Проблема:** conftest.py не загружается
**Решение:**
```powershell
cd C:\ProjectF\tests\telegram_ui
pytest --fixtures  # Проверить что фикстуры видны
```

### "Master not created"
**Проблема:** Онбординг мастера не завершился
**Возможные причины:**
- Бот не отвечает
- Неправильная последовательность кнопок
- Таймаут слишком короткий

**Решение:**
- Увеличить `asyncio.sleep()` в `master_helpers.py`
- Проверить что мастер-бот доступен

---

## 📁 Структура проекта

```
tests/telegram_ui/
├── conftest.py                    # Фикстуры
├── pytest.ini                     # Настройки pytest
├── config.py                      # Конфигурация
├── bot_client.py                  # Telethon клиент
├── test_session.session           # Сессия Telethon
├── helpers/
│   ├── __init__.py
│   ├── master_helpers.py          # Функции для мастеров
│   ├── order_helpers.py           # Функции для заказов
│   └── admin_helpers.py           # Функции для админа
├── test_lifecycle_p0.py           # P0 тесты
├── E2E_TESTING_PLAN.md            # Полный план (20 тестов)
└── QUICK_START_TESTING.md         # Этот файл
```

---

## 📋 Следующие шаги

1. ✅ Авторизовать Telethon
2. ✅ Запустить TP-001
3. ⬜ Написать TP-002 (заказ с эскалацией)
4. ⬜ Написать TP-003 (заказ без мастеров)
5. ⬜ Написать P1 тесты (отмены)
6. ⬜ Написать P2 тесты (финансы)
7. ⬜ Написать P3 тесты (edge cases)

---

## 💡 Полезные команды

```powershell
# Очистить БД вручную
docker exec -i field-service-postgres-1 psql -U fs_user -d field_service < field-service\migrations\2025-10-09_clean_test_data.sql

# Проверить статус заказа
docker exec -i field-service-postgres-1 psql -U fs_user -d field_service -c "SELECT id, status FROM orders;"

# Проверить мастеров
docker exec -i field-service-postgres-1 psql -U fs_user -d field_service -c "SELECT id, telegram_id, is_approved FROM masters;"

# Проверить офферы
docker exec -i field-service-postgres-1 psql -U fs_user -d field_service -c "SELECT id, order_id, master_id, status FROM offers;"

# Проверить комиссии
docker exec -i field-service-postgres-1 psql -U fs_user -d field_service -c "SELECT id, order_id, master_id, amount, status FROM commissions;"
```

---

## 📞 Поддержка

При возникновении проблем:
1. Проверить логи pytest (с флагом `-s`)
2. Проверить логи ботов в Docker
3. Проверить состояние БД вручную

**Документация:**
- `E2E_TESTING_PLAN.md` - полный план тестирования
- `2025-10-09_TESTING_SETUP_INSTRUCTIONS.md` - инструкции по настройке БД
