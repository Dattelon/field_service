# 🔧 BUGFIX: Добавление выбора банка для СБП при онбординге

## 📋 Проблема

При онбординге мастера, когда выбирается способ оплаты СБП:
- ✅ Спрашивается номер телефона
- ❌ НЕ спрашивается банк

**Текущий флоу**:
```
Выбрать СБП → Ввести телефон → Подтверждение
```

**Правильный флоу**:
```
Выбрать СБП → Ввести телефон → Выбрать банк → Подтверждение
```

## 🔧 Исправления

### 1. Добавить state для выбора банка

**Файл**: `field_service/bots/master_bot/states.py`

Добавить новый state `payout_sbp_bank`:

```python
class OnboardingStates(StatesGroup):
    pdn = State()
    last_name = State()
    first_name = State()
    middle_name = State()
    phone = State()
    city = State()
    districts = State()
    vehicle = State()
    skills = State()
    passport = State()
    selfie = State()
    payout_method = State()
    payout_requisites = State()
    payout_sbp_bank = State()  # 🔧 НОВЫЙ STATE
    confirm = State()
```

### 2. Добавить список банков и клавиатуру

**Файл**: `field_service/bots/master_bot/keyboards.py`

Добавить функцию для клавиатуры выбора банка:

```python
# Список популярных банков для СБП
SBP_BANKS = [
    ("sber", "Сбербанк"),
    ("tinkoff", "Тинькофф"),
    ("vtb", "ВТБ"),
    ("alfa", "Альфа-Банк"),
    ("raiff", "Райффайзенбанк"),
    ("gpb", "Газпромбанк"),
    ("mts", "МТС Банк"),
    ("psb", "ПСБ"),
    ("open", "Открытие"),
    ("sovcom", "Совкомбанк"),
    ("rsb", "Россельхозбанк"),
    ("ak_bars", "Ак Барс"),
    ("uralsib", "Уралсиб"),
    ("mkb", "МКБ"),
    ("other", "Другой банк"),
]

def sbp_bank_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора банка для СБП."""
    kb = InlineKeyboardBuilder()
    for code, name in SBP_BANKS:
        kb.button(text=name, callback_data=f"m:onb:sbp_bank:{code}")
    kb.adjust(2)  # 2 кнопки в ряд
    return kb.as_markup()
```

### 3. Изменить логику онбординга

**Файл**: `field_service/bots/master_bot/handlers/onboarding.py`

#### 3.1. Обновить STEP_MAPPING (прогресс-бар):
```python
STEP_MAPPING = {
    OnboardingStates.pdn: 1,
    OnboardingStates.last_name: 2,
    OnboardingStates.first_name: 3,
    OnboardingStates.middle_name: 4,
    OnboardingStates.phone: 5,
    OnboardingStates.city: 6,
    OnboardingStates.districts: 7,
    OnboardingStates.vehicle: 8,
    OnboardingStates.skills: 9,
    OnboardingStates.passport: 10,
    OnboardingStates.selfie: 11,
    OnboardingStates.payout_method: 12,
    OnboardingStates.payout_requisites: 13,
    OnboardingStates.payout_sbp_bank: 14,  # 🔧 НОВЫЙ ШАГ
}
TOTAL_ONBOARDING_STEPS = 14  # Было 13
```

#### 3.2. Изменить обработчик `onboarding_payout_requisites`:

```python
@router.message(OnboardingStates.payout_requisites)
async def onboarding_payout_requisites(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    method_value = data.get("payout_method")
    if not method_value:
        await message.answer("Сначала выберите способ выплаты.")
        return
    
    # 🔧 НОВАЯ ЛОГИКА: Для СБП сохраняем телефон и переходим к выбору банка
    if method_value == m.PayoutMethod.SBP.value:
        try:
            phone = onboarding_service.normalize_phone(message.text or "")
        except onboarding_service.ValidationError as exc:
            await message.answer(str(exc))
            return
        
        await state.update_data(sbp_phone=phone)
        await state.set_state(OnboardingStates.payout_sbp_bank)
        
        text = _add_progress_to_text("Выберите ваш банк для СБП:", OnboardingStates.payout_sbp_bank)
        await push_step_message(
            message,
            state,
            text,
            sbp_bank_keyboard(),  # Новая клавиатура
        )
        return
    
    # Для остальных способов - старая логика
    try:
        payout = onboarding_service.validate_payout(method_value, message.text or "")
    except onboarding_service.ValidationError as exc:
        await message.answer(str(exc))
        return
    
    await state.update_data(payout_method=payout.method.value, payout_payload=payout.payload)
    
    # P0-2: Проверка флага редактирования
    if data.get("is_editing"):
        await state.update_data(is_editing=False)
        await _show_summary(message, state)
        return
    
    await _show_summary(message, state)
```

#### 3.3. Добавить новый handler для выбора банка:

```python
@router.callback_query(OnboardingStates.payout_sbp_bank, F.data.startswith("m:onb:sbp_bank:"))
async def onboarding_sbp_bank_select(callback: CallbackQuery, state: FSMContext) -> None:
    """Обработчик выбора банка для СБП."""
    bank_code = callback.data.split(":")[-1]
    
    # Получаем название банка
    bank_name = next(
        (name for code, name in SBP_BANKS if code == bank_code),
        bank_code
    )
    
    data = await state.get_data()
    sbp_phone = data.get("sbp_phone")
    
    if not sbp_phone:
        await callback.answer("Ошибка: телефон не найден. Начните заново.", show_alert=True)
        return
    
    # Сохраняем полные данные СБП
    payload = {
        "sbp_phone": sbp_phone,
        "sbp_bank": bank_code,
        "sbp_bank_name": bank_name,
    }
    
    await state.update_data(
        payout_method=m.PayoutMethod.SBP.value,
        payout_payload=payload
    )
    
    # Проверка редактирования
    if data.get("is_editing"):
        await state.update_data(is_editing=False)
        await _show_summary(callback.message, state)
        await callback.answer(f"Банк {bank_name} выбран")
        return
    
    await _show_summary(callback.message, state)
    await callback.answer(f"Банк {bank_name} выбран")
```

#### 3.4. Обновить `_format_payout_summary`:

```python
def _format_payout_summary(method_value: str | None, payload: dict | None) -> str:
    if not method_value:
        return ''
    try:
        method = m.PayoutMethod(method_value)
    except ValueError:
        return method_value
    payload = payload or {}
    
    if method is m.PayoutMethod.CARD:
        number = payload.get('card_number', '')
        digits = ''.join(ch for ch in number if ch.isdigit())
        last4 = digits[-4:] if digits else ''
        return f"Карта *{last4}" if last4 else "Карта"
    
    if method is m.PayoutMethod.SBP:
        phone = payload.get('sbp_phone', '')
        bank_name = payload.get('sbp_bank_name', '')
        # 🔧 ОБНОВЛЕНО: Показываем и телефон, и банк
        if phone and bank_name:
            return f"СБП {phone} ({bank_name})"
        elif phone:
            return f"СБП {phone}"
        else:
            return "СБП"
    
    if method is m.PayoutMethod.YOOMONEY:
        account = payload.get('account', '')
        return f"ЮMoney {account}".strip() or "ЮMoney"
    
    if method is m.PayoutMethod.BANK_ACCOUNT:
        account = payload.get('account_number', '')
        last4 = account[-4:] if account else ''
        return f"Банк счёт *{last4}" if last4 else "Банк счёт"
    
    return method.value
```

### 4. Обновить onboarding_service (необязательно)

**Файл**: `field_service/services/onboarding_service.py`

Можно оставить как есть, так как payload теперь формируется в handlers. Но для полноты можно обновить валидацию:

```python
elif method is m.PayoutMethod.SBP:
    # Телефон и банк теперь приходят из handlers
    # Эта ветка больше не используется для СБП
    payload["sbp_phone"] = normalize_phone(normalized)
```

---

## ✅ Результат

### До:
```
Выбрать СБП → Ввести телефон → Подтверждение
Данные: {"sbp_phone": "+79123456789"}
```

### После:
```
Выбрать СБП → Ввести телефон → Выбрать банк → Подтверждение
Данные: {
    "sbp_phone": "+79123456789",
    "sbp_bank": "sber",
    "sbp_bank_name": "Сбербанк"
}
```

### Summary (сводка):
```
Способ выплаты: СБП +79123456789 (Сбербанк)
```

---

## 📊 Список изменённых файлов

1. `field_service/bots/master_bot/states.py` - добавлен state
2. `field_service/bots/master_bot/keyboards.py` - добавлена клавиатура банков
3. `field_service/bots/master_bot/handlers/onboarding.py`:
   - Обновлён STEP_MAPPING
   - Изменена логика `onboarding_payout_requisites`
   - Добавлен handler `onboarding_sbp_bank_select`
   - Обновлён `_format_payout_summary`

---

## 🧪 Тестирование

1. Запустить онбординг мастера
2. Дойти до выбора способа выплаты
3. Выбрать "СБП"
4. Ввести телефон: `+79123456789`
5. ✅ Должен показать список банков
6. Выбрать банк (например, "Сбербанк")
7. ✅ В summary должно быть: `СБП +79123456789 (Сбербанк)`
8. Подтвердить
9. Проверить в БД:
```sql
SELECT id, payout_method, payout_data 
FROM masters 
WHERE phone = '+79123456789';
```
Ожидается:
```json
{
    "sbp_phone": "+79123456789",
    "sbp_bank": "sber",
    "sbp_bank_name": "Сбербанк"
}
```

---

## 📝 Примечания

- Список банков можно расширить
- Можно добавить поиск по названию банка
- Можно добавить поле "Другой банк" с вводом вручную
- Прогресс-бар обновлён: теперь 14 шагов вместо 13

Патч готов к применению!
