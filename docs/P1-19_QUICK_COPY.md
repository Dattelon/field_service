# P1-19: Быстрое копирование данных

**Статус:** ✅ Реализовано  
**Дата:** 2025-10-09  
**Приоритет:** P1 (Высокий)

---

## 📋 Описание проблемы

Из отчёта UX Analysis:
> **Проблема:** Нельзя скопировать телефон/адрес одним кликом  
> **Решение:** Сделать поля кликабельными с копированием через callback buttons

---

## ✅ Что реализовано

### 1. **Общий модуль копирования**
Файл: `field_service/bots/common/copy_utils.py`

```python
def copy_button(text: str, order_id: int, data_type: str, bot_prefix: str)
    """Создаёт кнопку для копирования данных заказа"""

def format_copy_message(data_type: str, data: str)
    """Форматирует сообщение с данными для копирования"""
```

**Типы данных:**
- `cph` - client_phone (телефон клиента)
- `mph` - master_phone (телефон мастера)  
- `addr` - address (полный адрес)

**Формат callback:** `{bot_prefix}:copy:{data_type}:{order_id}`
- Примеры: `m:copy:cph:123`, `adm:copy:addr:456`

---

### 2. **Master Bot: Копирование в активном заказе**

#### Изменённые файлы:
- `field_service/bots/master_bot/handlers/orders.py`

#### Добавлено:
1. **Handler:** `@router.callback_query(F.data.regexp(r"^m:copy:(cph|addr):(\d+)$"))`
2. **Кнопки в карточке активного заказа:**
   - 📋 Телефон (если указан)
   - 📋 Адрес (всегда)

#### Где показываются кнопки:
- Активные заказы (ASSIGNED, EN_ROUTE, WORKING, PAYMENT)
- Отображаются в отдельной строке под кнопкой "📞 Позвонить клиенту"

```python
# P1-19: Кнопки быстрого копирования
if order.status in ACTIVE_STATUSES or order.status == m.OrderStatus.PAYMENT:
    copy_row: list[InlineKeyboardButton] = []
    if order.client_phone:
        copy_row.append(copy_button("📋 Телефон", order.id, "cph", "m"))
    copy_row.append(copy_button("📋 Адрес", order.id, "addr", "m"))
    if copy_row:
        keyboard_rows.append(copy_row)
```

---

### 3. **Admin Bot: Копирование в карточке заказа**

#### Изменённые файлы:
- `field_service/bots/admin_bot/ui/keyboards/orders.py`
- `field_service/bots/admin_bot/handlers/orders/copy_data.py` (новый)
- `field_service/bots/admin_bot/handlers/orders/__init__.py`

#### Добавлено:
1. **Handler:** `copy_router` с проверкой прав доступа (GLOBAL_ADMIN, CITY_ADMIN, LOGIST)
2. **Кнопки в `order_card_keyboard`:**
   - 📋 Телефон клиента
   - 📋 Телефон мастера
   - 📋 Адрес

#### Где показываются кнопки:
- Карточка заказа в очереди (`adm:q:card:{order_id}:{page}`)
- Отображаются в отдельной строке (3 кнопки в ряд) перед кнопками навигации

```python
# P1-19: Кнопки быстрого копирования
copy_row = InlineKeyboardBuilder()
copy_row.add(copy_button("📋 Телефон клиента", order_id, "cph", "adm"))
copy_row.add(copy_button("📋 Телефон мастера", order_id, "mph", "adm"))
copy_row.add(copy_button("📋 Адрес", order_id, "addr", "adm"))
copy_row.adjust(3)  # Три кнопки в ряд
kb.attach(copy_row)
```

---

## 🔄 Как это работает

### 1. **Пользователь нажимает кнопку копирования**
Например: `📋 Телефон` → callback `m:copy:cph:123`

### 2. **Handler загружает данные из БД**
```python
stmt = (
    select(
        m.orders.id,
        m.orders.client_phone,
        m.orders.house,
        m.cities.name.label("city"),
        m.districts.name.label("district"),
        m.streets.name.label("street"),
    )
    .join(m.cities, m.cities.id == m.orders.city_id)
    .outerjoin(m.districts, m.districts.id == m.orders.district_id)
    .outerjoin(m.streets, m.streets.id == m.orders.street_id)
    .where(m.orders.id == order_id)
)
```

### 3. **Отправка через Telegram Alert**
```python
await safe_answer_callback(callback, data, show_alert=True)
```

Telegram показывает alert с данными, которые можно:
- Прочитать
- Скопировать длинным нажатием (мобилка)
- Выделить и скопировать (десктоп)

---

## 🎯 Преимущества реализации

### ✅ **Безопасность:**
- Callback содержит только ID заказа, не сами данные (ограничение 64 байта)
- Проверка прав доступа в admin_bot
- Мастер видит только свои заказы (проверка `assigned_master_id`)

### ✅ **UX:**
- Один клик для копирования
- Данные всегда актуальные (загружаются из БД)
- Понятные иконки 📋
- Alert с большим текстом удобно копировать

### ✅ **Расширяемость:**
- Легко добавить новые типы данных (например, описание заказа)
- Единый модуль для обоих ботов
- Готовая инфраструктура для будущих улучшений

---

## 📊 Покрытие функциональности

| Бот | Что копируется | Где доступно |
|-----|---------------|--------------|
| Master | Телефон клиента | Активные заказы |
| Master | Адрес | Активные заказы |
| Admin | Телефон клиента | Карточка заказа |
| Admin | Телефон мастера | Карточка заказа |
| Admin | Адрес | Карточка заказа |

---

## 🧪 Как протестировать

### Master Bot:
1. Начать смену
2. Принять заказ
3. Открыть "📦 Активный заказ"
4. Нажать кнопки:
   - 📋 Телефон → должен показать alert с телефоном клиента
   - 📋 Адрес → должен показать alert с полным адресом

### Admin Bot:
1. Открыть "📋 Очередь заявок"
2. Выбрать любой заказ
3. В карточке заказа нажать:
   - 📋 Телефон клиента → alert с телефоном
   - 📋 Телефон мастера → alert с телефоном мастера (если назначен)
   - 📋 Адрес → alert с адресом

### Проверка edge cases:
- Заказ без телефона клиента → "❌ Телефон не указан"
- Заказ без назначенного мастера → "❌ Мастер не назначен"
- Попытка копировать чужой заказ (master) → "Заказ не найден"

---

## 📝 Логирование

Каждое копирование логируется:

**Master Bot:**
```python
_log.info("copy_data: uid=%s order_id=%s type=%s", callback_uid, order_id, data_type)
```

**Admin Bot:**
```python
_log.info("copy_data: staff_id=%s order_id=%s type=%s", staff.staff_id, order_id, data_type)
```

---

## 🔮 Возможные улучшения (будущее)

1. **Копирование описания заказа** - для длинных описаний
2. **История копирований** - аналитика популярных действий
3. **Групповое копирование** - скопировать всё сразу
4. **Форматирование адреса** - разные форматы (короткий/полный)
5. **Копирование в буфер напрямую** - через Web App API (требует дополнительной интеграции)

---

## ✅ Чеклист завершения

- [x] Создан модуль `copy_utils.py`
- [x] Добавлен handler в master_bot
- [x] Добавлены кнопки в master_bot карточку
- [x] Создан handler в admin_bot
- [x] Добавлены кнопки в admin_bot карточку
- [x] Зарегистрирован router в admin_bot
- [x] Документация создана
- [ ] Протестировано в реальных условиях
- [ ] Собрать feedback от пользователей

---

**Готово к тестированию!** 🚀
