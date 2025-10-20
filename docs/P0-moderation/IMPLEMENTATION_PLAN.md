# ПЛАН ДОРАБОТКИ P0 (КРИТИЧНЫЕ ЗАДАЧИ)

## ИСКЛЮЧЕНО ИЗ РАЗРАБОТКИ:
- ❌ Геокодер и координаты (lat/lon) - исключены по запросу

---

## P0-1: МОДЕРАЦИЯ МАСТЕРОВ ✅

### СТАТУС: Инфраструктура готова, требуется добавить методы

### ЧТО РЕАЛИЗОВАНО:
- ✅ UI: Кнопка "🛠 Модерация" в главном меню
- ✅ Роутеры: `admin_moderation.py`, `admin_masters.py`
- ✅ Список анкет с фильтрами (группы: на модерации, одобренные, заблокированные)
- ✅ Карточка мастера с полной информацией
- ✅ Кнопки "✅ Одобрить" / "❌ Отклонить"
- ✅ FSM для ввода причины отклонения (1-200 символов)

### ТРЕБУЕТСЯ ДОРАБОТКА:

**1. Добавить методы в `services_db.py` → класс `DBMastersService`:**

Файл с патчем создан: `field-service/PATCH_DBMastersService_moderation.py`

Методы для добавления:
- `approve_master(master_id, by_staff_id)` - одобрение анкеты
- `reject_master(master_id, reason, by_staff_id)` - отклонение
- `block_master(master_id, reason, by_staff_id)` - блокировка
- `unblock_master(master_id, by_staff_id)` - разблокировка
- `set_master_limit(master_id, limit, by_staff_id)` - изменение лимита
- `enqueue_master_notification(master_id, message)` - отправка уведомления

**2. Инструкция по применению патча:**

```bash
# 1. Открыть файл
nano field-service/field_service/bots/admin_bot/services_db.py

# 2. Найти конец класса DBMastersService (перед следующим class или EOF)

# 3. Вставить методы из PATCH_DBMastersService_moderation.py
#    Важно: отступы должны совпадать с другими методами класса (4 пробела)

# 4. Сохранить файл
```

**ТРУДОЗАТРАТЫ:** 15 минут

---

## P0-2: ВАЛИДАЦИЯ ТЕЛЕФОНА ПРИ ОНБОРДИНГЕ ⚠️

### ПРОБЛЕМА:
В мастер-боте при онбординге телефон НЕ валидируется:
- Поле `phone` в БД nullable
- Пользователь может пропустить ввод или ввести некорректный формат

### РЕШЕНИЕ:

**Файл:** `field-service/field_service/bots/master_bot/handlers/onboarding.py`

**Найти:** Обработчик ввода телефона в FSM онбординга

**Добавить:**
```python
from field_service.services.onboarding_service import normalize_phone

@router.message(StateFilter(OnboardingFSM.phone))
async def onboarding_phone(msg: Message, state: FSMContext) -> None:
    raw_phone = (msg.text or "").strip()
    
    # Валидация
    try:
        normalized = normalize_phone(raw_phone)
    except ValueError:
        await msg.answer(
            "❌ Неверный формат телефона.\n"
            "Используйте: +79001234567 или 89001234567"
        )
        return
    
    # Сохранить нормализованный телефон
    await state.update_data(phone=normalized)
    await state.set_state(OnboardingFSM.next_step)
    await msg.answer("✅ Телефон сохранён.")
```

**ТРУДОЗАТРАТЫ:** 10 минут

---

## P0-3: УВЕДОМЛЕНИЕ МАСТЕРУ О БЛОКИРОВКЕ ⚠️

### ПРОБЛЕМА:
При просрочке комиссии >3ч watchdog блокирует мастера, но НЕ отправляет уведомление.

### РЕШЕНИЕ:

**Файл:** `field-service/field_service/services/watchdogs.py`

**Найти:** Функцию `watchdog_commissions_overdue`

**После блокировки мастера добавить:**
```python
# В конце блока, где блокируется мастер:
if blocked_master_id:
    try:
        master = await session.get(m.masters, blocked_master_id)
        if master and master.tg_user_id:
            await bot.send_message(
                master.tg_user_id,
                f"⚠️ <b>Ваш аккаунт заблокирован</b>\n\n"
                f"Причина: Просрочка оплаты комиссии #{commission_id}\n"
                f"Дедлайн был: {deadline_local}\n\n"
                f"Для разблокировки обратитесь к администратору."
            )
            live_log.push("watchdog", f"Sent block notification to master#{blocked_master_id}")
    except Exception as exc:
        logger.warning(f"Failed to notify master#{blocked_master_id}: {exc}")
```

**ТРУДОЗАТРАТЫ:** 10 минут

---

## P0-4: ТЕЛЕФОН КЛИЕНТА ПРИ ASSIGNED ⚠️

### ПРОБЛЕМА:
Телефон клиента отображается только после перехода в EN_ROUTE, но ТЗ требует показ сразу при ASSIGNED.

### РЕШЕНИЕ:

**Файл:** `field-service/field_service/bots/master_bot/handlers/orders.py`

**Найти:** Функцию `_render_active_order`

**Изменить условие:**
```python
# БЫЛО:
if order.status in ACTIVE_STATUSES or order.status == m.OrderStatus.PAYMENT:
    text_lines.append(f"👤 Клиент: {escape_html(order.client_name or '—')}")
    text_lines.append(f"📞 Телефон: {escape_html(order.client_phone or '—')}")

# СТАЛО:
if order.status in (
    m.OrderStatus.ASSIGNED,  # ← ДОБАВЛЕНО
    m.OrderStatus.EN_ROUTE,
    m.OrderStatus.WORKING,
    m.OrderStatus.PAYMENT
):
    text_lines.append(f"👤 Клиент: {escape_html(order.client_name or '—')}")
    text_lines.append(f"📞 Телефон: {escape_html(order.client_phone or '—')}")
```

**ТРУДОЗАТРАТЫ:** 5 минут

---

## ОБЩИЙ ПЛАН ВЫПОЛНЕНИЯ:

### Шаг 1: Модерация (15 мин)
1. Открыть `services_db.py`
2. Найти класс `DBMastersService`
3. Добавить методы из патча `PATCH_DBMastersService_moderation.py`
4. Сохранить

### Шаг 2: Валидация телефона (10 мин)
1. Открыть `field_service/bots/master_bot/handlers/onboarding.py`
2. Найти обработчик `OnboardingFSM.phone`
3. Добавить валидацию через `normalize_phone()`
4. Сохранить

### Шаг 3: Уведомление о блокировке (10 мин)
1. Открыть `field_service/services/watchdogs.py`
2. Найти `watchdog_commissions_overdue`
3. Добавить `bot.send_message()` после блокировки
4. Сохранить

### Шаг 4: Телефон при ASSIGNED (5 мин)
1. Открыть `field_service/bots/master_bot/handlers/orders.py`
2. Найти `_render_active_order`
3. Добавить `m.OrderStatus.ASSIGNED` в условие
4. Сохранить

### Шаг 5: Тестирование (15 мин)
```bash
# Запустить оба бота
python -m field_service.bots.admin_bot.main &
python -m field_service.bots.master_bot.main &

# Проверить:
# 1. Модерацию: /start → "🛠 Модерация" → одобрить/отклонить анкету
# 2. Онбординг: создать нового мастера, попробовать неправильный телефон
# 3. Блокировку: создать просроченную комиссию, запустить watchdog
# 4. Телефон клиента: принять заказ, проверить отображение в ASSIGNED
```

---

## ИТОГО: 55 минут
- Разработка: 40 минут
- Тестирование: 15 минут

## КРИТЕРИИ ПРИЁМКИ:

- ✅ P0-1: Админ может одобрять/отклонять анкеты, мастер получает уведомления
- ✅ P0-2: Мастер не может завершить онбординг без корректного телефона
- ✅ P0-3: При блокировке за просрочку мастер получает push-уведомление в бот
- ✅ P0-4: Телефон клиента виден сразу после взятия заказа (ASSIGNED)

## ФАЙЛЫ ДЛЯ ИЗМЕНЕНИЯ:

1. `field_service/bots/admin_bot/services_db.py` - добавить методы модерации
2. `field_service/bots/master_bot/handlers/onboarding.py` - валидация телефона
3. `field_service/services/watchdogs.py` - уведомление о блокировке
4. `field_service/bots/master_bot/handlers/orders.py` - телефон при ASSIGNED

## BACKUP PLAN:

Перед внесением изменений создать бэкап:
```bash
cd field-service
git add -A
git commit -m "WIP: Before P0 fixes"
git branch backup-before-p0-fixes
```

После завершения:
```bash
git add -A
git commit -m "feat: P0 critical fixes (moderation, phone validation, notifications)"
```
