# CHANGE REQUEST: Исправление экспорта отчётов (date vs datetime)

**Дата:** 2025-10-04  
**Приоритет:** HIGH  
**Статус:** IMPLEMENTED  
**Автор:** AI Assistant  

## Проблема

При формировании отчётов в админ-боте возникала ошибка:
```
'datetime.date' object has no attribute 'tzinfo'
```

Отчёты (Заказы, Комиссии, Реферальные) не формировались ни в CSV, ни в XLSX формате.

## Причина

1. **Несоответствие типов**: Обработчики в `reports.py` передают объекты `date` (из парсинга периодов), а функции экспорта ожидают `datetime`
2. **Функция `_ensure_utc()`**: Пыталась работать с атрибутом `tzinfo`, который есть только у `datetime`, но не у `date`
3. **Неполный период**: При использовании `date` для `date_to` включалась только полночь (00:00), а не весь день

## Решение

### 1. Обновлена функция `_ensure_utc()` в `export_service.py`

```python
def _ensure_utc(value: datetime | date, *, end_of_day: bool = False) -> datetime:
    """Convert date or datetime to UTC-aware datetime.
    
    Args:
        value: Date or datetime to convert
        end_of_day: If True and value is date, set time to 23:59:59
    """
    if isinstance(value, date) and not isinstance(value, datetime):
        # Convert date to datetime
        if end_of_day:
            value = datetime.combine(value, datetime.max.time().replace(microsecond=0), tzinfo=UTC)
        else:
            value = datetime.combine(value, datetime.min.time(), tzinfo=UTC)
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
```

**Изменения:**
- ✅ Добавлена проверка типа `date`
- ✅ Конвертация `date` → `datetime` (00:00:00 для начала, 23:59:59 для конца)
- ✅ Параметр `end_of_day` для корректной обработки конечной даты
- ✅ Импорт `date` из `datetime`

### 2. Обновлены сигнатуры функций экспорта

```python
async def export_orders(
    *, 
    date_from: datetime | date,  # было: datetime
    date_to: datetime | date,    # было: datetime
    ...
) -> ExportBundle:
    start_utc = _ensure_utc(date_from)
    end_utc = _ensure_utc(date_to, end_of_day=True)  # включить весь день
    ...
```

Аналогично для:
- `export_commissions()`
- `export_referral_rewards()`

### 3. Добавлены тесты

Созданы 3 новых теста в `test_export_service.py`:
- `test_export_orders_with_date_objects()`
- `test_export_commissions_with_date_objects()`
- `test_export_referral_rewards_with_date_objects()`

Проверяют корректность работы с объектами `date`.

## Затронутые файлы

### Изменённые:
1. `field_service/services/export_service.py` - основное исправление
2. `tests/test_export_service.py` - добавлены тесты

### Без изменений:
- `field_service/bots/admin_bot/handlers/reports.py` - работает как ожидалось

## Проверка

### До исправления:
```
❌ Ошибка при формировании отчёта: 'datetime.date' object has no attribute 'tzinfo'
```

### После исправления:
```
✅ Отчёт отправлен.
```

### Тест-кейсы:

1. **Быстрые периоды** (today, yesterday, last7, this_month, prev_month):
   - Передаётся `date` → конвертируется в `datetime` с полным днём ✅

2. **Ручной ввод** ("2025-01-15 2025-01-31"):
   - Парсится в `date` → конвертируется в `datetime` ✅

3. **Граничные даты**:
   - `date_from = 2025-01-15` → `2025-01-15 00:00:00 UTC` ✅
   - `date_to = 2025-01-15` → `2025-01-15 23:59:59 UTC` ✅

## Обратная совместимость

✅ **Полная**: функции по-прежнему принимают `datetime` (для программного вызова), но теперь также корректно работают с `date`.

## Риски

🟢 **Низкий риск**: 
- Изменения локализованы в одной функции
- Добавлена только поддержка нового типа, старая логика не нарушена
- Покрыто тестами

## Тестирование

### Запуск тестов:
```bash
cd field-service
pytest tests/test_export_service.py -v
```

### Ожидаемый результат:
```
test_export_orders_with_date_objects PASSED
test_export_commissions_with_date_objects PASSED
test_export_referral_rewards_with_date_objects PASSED
test_export_orders_bundle PASSED
test_export_commissions PASSED
test_export_referral_rewards PASSED
```

## Развёртывание

1. Перезапустить админ-бота:
   ```bash
   systemctl restart field-service-admin-bot
   ```

2. Проверить логи:
   ```bash
   journalctl -u field-service-admin-bot -f
   ```

3. Протестировать формирование отчёта через UI

## Статус реализации

- [x] Код изменён
- [x] Тесты добавлены
- [x] Документация обновлена
- [ ] Code review
- [ ] Развёрнуто на production
- [ ] Протестировано на production

---

**Подпись разработчика:** AI Assistant  
**Дата:** 2025-10-04
