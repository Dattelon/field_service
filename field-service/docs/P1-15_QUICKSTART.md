# P1-15: Группировка комиссий - QUICKSTART

## 🚀 Быстрый старт для тестирования

### 1. Запуск проекта
```bash
cd C:\ProjectF\field-service
docker-compose up -d
python -m field_service.bots.admin_bot.main
```

### 2. Тестовый сценарий

#### Сценарий 1: Просмотр групп
```
1. Открыть админ-бота
2. Нажать "💰 Финансы"
3. Нажать "📊 По периодам"
4. ✅ Видим меню с группами и количествами
```

#### Сценарий 2: Просмотр комиссий периода
```
1. В меню групп выбрать "📅 Сегодня"
2. ✅ Видим список комиссий за сегодня
3. Нажать на любую комиссию
4. ✅ Открывается карточка комиссии
5. Нажать "⬅️ Назад"
6. ✅ Возвращаемся к списку комиссий (не к меню групп!)
```

#### Сценарий 3: Пагинация
```
1. Если комиссий больше 10
2. ✅ Видим кнопки ◀️ Назад / ▶️ Далее
3. Проверить что пагинация работает
```

### 3. Проверка callback data

Открыть логи и проверить что генерируются правильные callback:
```
adm:f:grouped:aw          # Меню групп
adm:f:grp:aw:today:1      # Просмотр периода
adm:f:cm:card:123         # Карточка комиссии
```

### 4. Проверка RBAC

#### CITY_ADMIN
```python
# Должен видеть только комиссии из своих городов
await session.execute(
    update(m.staff_users)
    .where(m.staff_users.id == test_admin_id)
    .values(role='CITY_ADMIN', city_ids=[1, 2])
)
```

#### GLOBAL_ADMIN
```python
# Должен видеть все комиссии
await session.execute(
    update(m.staff_users)
    .where(m.staff_users.id == test_admin_id)
    .values(role='GLOBAL_ADMIN', city_ids=None)
)
```

---

## 🐛 Возможные проблемы

### Проблема: Кнопки не работают
**Решение:** Проверить что callback handlers зарегистрированы:
```python
# В admin_bot/handlers/__init__.py должен быть импорт
from .finance import router as finance_router
```

### Проблема: Группы не отображаются
**Решение:** Проверить что есть комиссии в БД:
```sql
SELECT 
    DATE(created_at) as date,
    status,
    COUNT(*) as count
FROM commissions
WHERE status IN ('WAIT_PAY', 'REPORTED')
GROUP BY DATE(created_at), status
ORDER BY date DESC;
```

### Проблема: Import Error
**Решение:** Проверить что все импорты на месте:
```python
# В admin_bot/handlers/finance/main.py
from ...core.access import visible_city_ids_for
from ...ui.keyboards import (
    finance_grouped_keyboard,
    finance_group_period_keyboard,
)
```

---

## 📊 SQL для создания тестовых данных

```sql
-- Создать комиссии за разные периоды
INSERT INTO commissions (order_id, master_id, amount, status, created_at)
VALUES 
    -- Сегодня
    (1, 1, 1500, 'WAIT_PAY', NOW()),
    (2, 2, 2300, 'WAIT_PAY', NOW()),
    
    -- Вчера
    (3, 1, 800, 'WAIT_PAY', NOW() - INTERVAL '1 day'),
    (4, 2, 1200, 'WAIT_PAY', NOW() - INTERVAL '1 day'),
    
    -- Неделя назад
    (5, 1, 3000, 'WAIT_PAY', NOW() - INTERVAL '5 days'),
    
    -- Месяц назад
    (6, 2, 950, 'WAIT_PAY', NOW() - INTERVAL '20 days');
```

---

## ✅ Чеклист проверки

- [ ] Кнопка "📊 По периодам" отображается в меню Финансов
- [ ] Клик на кнопку открывает меню групп
- [ ] Группы показывают правильное количество комиссий
- [ ] Пустые группы скрыты
- [ ] Клик на группу открывает список комиссий
- [ ] Пагинация работает (если комиссий >10)
- [ ] Клик на комиссию открывает карточку
- [ ] Возврат из карточки идёт в список периода, а не в меню групп
- [ ] RBAC работает (CITY_ADMIN видит только свои города)
- [ ] Нет ошибок в логах

---

**Готово к тестированию!** 🎉
