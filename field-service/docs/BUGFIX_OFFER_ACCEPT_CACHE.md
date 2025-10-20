# 🐛 BUGFIX: Заказ остаётся в "Новых заявках" после принятия

**Дата**: 2025-10-10  
**Приоритет**: P0 (Critical)  
**Статус**: ✅ FIXED

---

## 📋 Описание проблемы

### Симптомы
1. Мастер нажимает "✅ Взять заявку"
2. Приходит уведомление "✅ Заявка принята. Удачи в работе!"
3. **НО**: Заказ НЕ исчезает из списка "Новые заявки"
4. Можно нажимать "Взять" по кругу бесконечно
5. В БД заказ реально в статусе `ASSIGNED`, оффер в статусе `ACCEPTED`

### Воспроизведение
```
1. Мастер открывает "Новые заявки"
2. Видит заказ #123
3. Нажимает "Взять заявку" → OK ✅
4. Возвращается в список "Новые заявки"
5. Заказ #123 всё ещё там! ❌
```

---

## 🔍 Причина бага

### Root Cause
**SQLAlchemy кэширует данные в `session` и не обновляет их после `commit()`**

### Детали
```python
# В offer_accept() handler:
await session.commit()  # ✅ Данные записаны в БД
_log.info("transaction committed")

# Проблема: session всё ещё хранит старые данные в кэше
await _render_offers(callback, session, master, page=page)
```

### Что происходит в `_load_offers()`:
```python
stmt = select(m.offers).where(
    m.offers.master_id == master_id,
    m.offers.state.in_((m.OfferState.SENT, m.OfferState.VIEWED)),  # ❌
    m.offers.expires_at > func.now(),
)
result = await session.execute(stmt)
```

**SQLAlchemy читает из кэша session:**
- В кэше: `offer.state = SENT` (старое значение)
- В БД: `offer.state = ACCEPTED` (новое значение после commit)

Результат: оффер проходит фильтр `state.in_((SENT, VIEWED))` и показывается мастеру!

---

## ✅ Решение

### Патч
Добавить `session.expire_all()` после `commit()` в `offer_accept()`:

```python
# field-service/field_service/bots/master_bot/handlers/orders.py
# Строки 459-469

await session.commit()
_log.info("offer_accept: transaction committed successfully for order=%s", order_id)

# ✅ BUGFIX: Сбрасываем кэш SQLAlchemy после commit
# Без этого _render_offers будет читать устаревшие данные из кэша,
# где оффер всё ещё в статусе SENT/VIEWED вместо ACCEPTED
session.expire_all()
_log.info("offer_accept: session cache expired for order=%s", order_id)

await safe_answer_callback(callback, ALERT_ACCEPT_SUCCESS, show_alert=True)
await _render_offers(callback, session, master, page=page)
```

### Почему это работает
- `session.expire_all()` помечает все объекты в session как "устаревшие"
- При следующем запросе SQLAlchemy **заново читает данные из БД**
- `_load_offers()` видит `offer.state = ACCEPTED` и **не возвращает оффер**

---

## 🧪 Тестирование

### Unit Test
Создан тест `test_offer_accept_cache_bug.py`:
```python
@pytest.mark.asyncio
async def test_offer_disappears_after_accept(session: AsyncSession) -> None:
    """
    CRITICAL: Regression test для бага где заказ оставался в списке после accept.
    """
    # 1. Создаём оффер в статусе SENT
    # 2. Принимаем заказ (меняем state → ACCEPTED)
    # 3. Проверяем что без expire_all() - данные из кэша (БАГ)
    # 4. Проверяем что с expire_all() - данные из БД (ОК)
```

### Результаты
- ✅ Тест проходит
- ✅ В реальном боте заказ исчезает после принятия
- ✅ Нельзя принять один заказ дважды

---

## 📊 Влияние

### До фикса (БАГ)
- Мастер видит принятый заказ в "Новых заявках"
- Может нажать "Взять" повторно → получит ошибку "Уже занято"
- Плохой UX, путаница

### После фикса
- ✅ Заказ исчезает сразу после принятия
- ✅ Список "Новых заявок" актуален
- ✅ Мастер видит только реально доступные заказы

---

## 🔧 Изменённые файлы

1. **field-service/field_service/bots/master_bot/handlers/orders.py**
   - Добавлен `session.expire_all()` после commit в `offer_accept()`
   - Строки 459-469

2. **field-service/tests/test_offer_accept_cache_bug.py**
   - Новый regression test для проверки бага

3. **code_snapshot/** (обновлён через export_code_snapshot.py)

---

## 📝 Выводы и best practices

### Урок
**ВСЕГДА используй `session.expire_all()` после `commit()` если далее будешь читать данные:**

```python
# ❌ WRONG - читает из кэша
await session.commit()
data = await session.execute(select(...))  # Старые данные!

# ✅ CORRECT - читает из БД
await session.commit()
session.expire_all()  # Сбрасываем кэш
data = await session.execute(select(...))  # Свежие данные!
```

### Когда нужен expire_all()
1. После `commit()` если далее идут SELECT запросы
2. После массовых UPDATE/DELETE через `session.execute()`
3. Перед `refresh()` объекта (иначе может быть MissingGreenlet)
4. В тестах перед проверкой состояния после изменений

### Альтернативы
- `session.refresh(obj)` - обновляет конкретный объект
- `await session.execute(select(...))` с `execution_options(populate_existing=True)`
- Создать новую session (тяжеловесно)

---

## 🎯 Checklist

- [x] Баг воспроизведён и понята причина
- [x] Патч применён в `orders.py`
- [x] Написан regression test
- [x] Тест проходит
- [x] Code snapshot обновлён
- [x] Документация создана
- [x] Готово к деплою

---

## 🚀 Деплой

**Готов к деплою**: ДА ✅

**Риски**: Минимальные - добавлен один вызов `expire_all()`

**Rollback план**: Убрать строку `session.expire_all()` если что-то сломается

**Рекомендация**: Деплоить в production сразу, это critical fix для UX
