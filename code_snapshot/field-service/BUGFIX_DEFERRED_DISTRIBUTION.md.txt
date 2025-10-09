# 🔧 BUGFIX: DEFERRED Distribution & UI Issues

## 📋 Проблемы

### 1. ⚠️ Кнопка "Телефон мастера" показывается всегда
- **Файл**: `field_service/bots/admin_bot/ui/keyboards/orders.py`
- **Проблема**: Кнопка "Телефон мастера" отображается даже когда мастер не назначен
- **Место**: Функция `order_card_keyboard`, строки 87-89

### 2. ⚠️ Принудительное распределение DEFERRED не работает
- **Файл**: `field_service/bots/admin_bot/services/distribution.py`
- **Проблема**: При принудительном запуске распределения для DEFERRED заказа:
  - Статус не переводится в SEARCHING перед отправкой оффера
  - DEFERRED отсутствует в `allowed_statuses` в методе `send_manual_offer`
- **Результат**: Оффер не отправляется мастеру, распределение не запускается

### 3. ⚠️ Битые строки в меню "Заявки"
- **Файл**: `field_service/bots/admin_bot/handlers/orders/queue.py`
- **Проблема**: Текст меню использует Unicode escape-последовательности вместо нормального текста
- **Место**: Функция `cb_orders_menu`, строки 586-589

---

## 🔧 Исправления

### Патч 1: Условное отображение кнопки "Телефон мастера"

**Файл**: `field_service/bots/admin_bot/ui/keyboards/orders.py`

#### Изменения:
1. Добавлен параметр `has_master: bool = False` в сигнатуру `order_card_keyboard`
2. Кнопка "Телефон мастера" отображается только если `has_master=True`
3. Адаптивное количество кнопок в ряду: 3 если есть мастер, 2 если нет

```python
def order_card_keyboard(
    order_id: int,
    attachments: Sequence[OrderAttachment] = (),
    *,
    allow_return: bool = True,
    allow_cancel: bool = True,
    show_guarantee: bool = False,
    is_deferred: bool = False,
    page: int = 1,
    has_master: bool = False,  # 🔧 НОВЫЙ ПАРАМЕТР
) -> InlineKeyboardMarkup:
    # ...
    # Кнопки быстрого копирования
    copy_row = InlineKeyboardBuilder()
    copy_row.add(copy_button("📋 Телефон клиента", order_id, "cph", "adm"))
    # 🔧 Показывать только если мастер назначен
    if has_master:
        copy_row.add(copy_button("📋 Телефон мастера", order_id, "mph", "adm"))
    copy_row.add(copy_button("📋 Адрес", order_id, "addr", "adm"))
    copy_row.adjust(3 if has_master else 2)  # Адаптивная раскладка
    kb.attach(copy_row)
```

**Файл**: `field_service/bots/admin_bot/handlers/orders/queue.py`

#### Изменения в `_order_card_markup`:
```python
def _order_card_markup(order: OrderDetail, *, show_guarantee: bool = False, page: int = 1) -> InlineKeyboardMarkup:
    status = (order.status or '').upper()
    allow_return = status not in {'CANCELED', 'CLOSED'}
    allow_cancel = status not in {'CANCELED', 'CLOSED'}
    is_deferred = status == 'DEFERRED'
    has_master = bool(order.master_id)  # 🔧 ПРОВЕРКА НАЛИЧИЯ МАСТЕРА
    return order_card_keyboard(
        order.id,
        attachments=order.attachments,
        allow_return=allow_return,
        allow_cancel=allow_cancel,
        show_guarantee=show_guarantee,
        is_deferred=is_deferred,
        page=page,
        has_master=has_master,  # 🔧 ПЕРЕДАЁМ ФЛАГ
    )
```

---

### Патч 2: Автоматический перевод DEFERRED → SEARCHING

**Файл**: `field_service/bots/admin_bot/services/distribution.py`

#### Изменения:

1. **Добавлен импорт `insert`**:
```python
from sqlalchemy import func, insert, select, update
```

2. **В методе `assign_auto` (автораспределение)**:
```python
status_enum = _coerce_order_status(getattr(data, "status", None))
logistic_mark = getattr(data, "dist_escalated_logist_at", None)

# 🔧 BUGFIX: Переводим DEFERRED → SEARCHING перед распределением
if status_enum == m.OrderStatus.DEFERRED:
    await session.execute(
        update(m.orders)
        .where(m.orders.id == order_id)
        .values(status=m.OrderStatus.SEARCHING)
    )
    await session.execute(
        insert(m.order_status_history).values(
            order_id=order_id,
            from_status=m.OrderStatus.DEFERRED,
            to_status=m.OrderStatus.SEARCHING,
            changed_by_staff_id=by_staff_id,
            reason="Принудительный запуск распределения из админ-бота",
        )
    )
    status_enum = m.OrderStatus.SEARCHING
    _push_dist_log(f"[dist] order={order_id} DEFERRED→SEARCHING (forced by staff #{by_staff_id})", level="INFO")
```

3. **В методе `send_manual_offer` (ручное назначение)**:

Добавлен DEFERRED в `allowed_statuses`:
```python
status = getattr(order, "status", None)
# 🔧 BUGFIX: Разрешаем ручное назначение для DEFERRED
allowed_statuses = {
    m.OrderStatus.SEARCHING,
    m.OrderStatus.GUARANTEE,
    m.OrderStatus.DEFERRED,  # 🔧 ДОБАВЛЕНО
}
```

Аналогичный код перевода DEFERRED → SEARCHING:
```python
# 🔧 BUGFIX: Переводим DEFERRED → SEARCHING при ручном назначении
if status_enum == m.OrderStatus.DEFERRED:
    await session.execute(
        update(m.orders)
        .where(m.orders.id == order_id)
        .values(status=m.OrderStatus.SEARCHING)
    )
    await session.execute(
        insert(m.order_status_history).values(
            order_id=order_id,
            from_status=m.OrderStatus.DEFERRED,
            to_status=m.OrderStatus.SEARCHING,
            changed_by_staff_id=by_staff_id,
            reason="Ручное назначение из админ-бота",
        )
    )
    status_enum = m.OrderStatus.SEARCHING
```

---

### Патч 3: Исправление битых строк в меню

**Файл**: `field_service/bots/admin_bot/handlers/orders/queue.py`

#### Изменения в `cb_orders_menu`:
```python
text = (
    "📦 <b>Заявки</b>\n\n"
    "Выберите раздел для просмотра заявок."
)
```

Вместо:
```python
text = (
    "\U0001f4e6 <b>\u0437\u0430\u044f\0432\043a\0438</b>\n\n"
    "\u0412\u044b\u0431\0435\0440\0438\0442\0435..."
)
```

---

## ✅ Результат

### 1. Кнопка "Телефон мастера"
- ✅ Отображается **только когда мастер назначен**
- ✅ Адаптивная раскладка: 2 или 3 кнопки в ряду

### 2. Распределение DEFERRED
- ✅ Автораспределение теперь работает для DEFERRED заказов
- ✅ Ручное назначение теперь работает для DEFERRED заказов
- ✅ Автоматический перевод DEFERRED → SEARCHING с записью в историю
- ✅ Логирование перехода статуса

### 3. Меню "Заявки"
- ✅ Корректный текст без Unicode escape-последовательностей
- ✅ Читаемый эмодзи "📦"

---

## 🧪 Тестирование

### Сценарий 1: Проверка кнопки "Телефон мастера"
1. Открыть карточку заказа БЕЗ мастера
   - ✅ Должны быть 2 кнопки: "Телефон клиента", "Адрес"
2. Назначить мастера на заказ
3. Открыть карточку снова
   - ✅ Должны быть 3 кнопки: "Телефон клиента", "Телефон мастера", "Адрес"

### Сценарий 2: Автораспределение DEFERRED
1. Создать заказ в нерабочее время (статус DEFERRED)
2. Открыть карточку заказа
   - ✅ Должна быть кнопка "⚠️ Перевести в поиск мастера"
3. Нажать "Назначить" → "Автораспределение"
   - ✅ Должно показать предупреждение о DEFERRED
4. Нажать "Да, запустить"
   - ✅ Заказ переходит в SEARCHING
   - ✅ Отправляется оффер мастеру
   - ✅ В истории статусов записан переход DEFERRED → SEARCHING

### Сценарий 3: Ручное назначение DEFERRED
1. Создать заказ в нерабочее время (статус DEFERRED)
2. Нажать "Назначить" → "Выбрать мастера"
   - ✅ Должен показать предупреждение в шапке
3. Выбрать мастера и нажать "Назначить"
   - ✅ Заказ переходит в SEARCHING
   - ✅ Отправляется оффер мастеру
   - ✅ В истории записан переход

### Сценарий 4: Меню "Заявки"
1. Открыть раздел "Заявки" в админ-боте
   - ✅ Заголовок: "📦 Заявки"
   - ✅ Текст: "Выберите раздел для просмотра заявок"
   - ✅ Без битых символов

---

## 📊 SQL для проверки

### Проверка перехода DEFERRED → SEARCHING:
```sql
SELECT 
    id, 
    status, 
    created_at,
    updated_at
FROM orders 
WHERE id = 2;

SELECT 
    id,
    order_id,
    from_status,
    to_status,
    changed_by_staff_id,
    reason,
    changed_at
FROM order_status_history 
WHERE order_id = 2 
ORDER BY changed_at DESC 
LIMIT 5;
```

### Проверка офферов:
```sql
SELECT 
    id,
    order_id,
    master_id,
    state,
    round,
    deadline,
    created_at
FROM offers 
WHERE order_id = 2 
ORDER BY created_at DESC;
```

---

## 📝 Измененные файлы

1. `field_service/bots/admin_bot/ui/keyboards/orders.py`
   - Добавлен параметр `has_master`
   - Условное отображение кнопки "Телефон мастера"

2. `field_service/bots/admin_bot/handlers/orders/queue.py`
   - Передача флага `has_master` в `order_card_keyboard`
   - Исправлен текст меню "Заявки"

3. `field_service/bots/admin_bot/services/distribution.py`
   - Добавлен импорт `insert`
   - Автоперевод DEFERRED → SEARCHING в `assign_auto`
   - Автоперевод DEFERRED → SEARCHING в `send_manual_offer`
   - Добавлен DEFERRED в `allowed_statuses`

---

## 🔄 Применение патча

```bash
# Перезапустить админ-бот
docker-compose restart admin-bot

# Проверить логи
docker-compose logs -f admin-bot | grep -i "deferred\|dist"
```

Патч готов к тестированию!
