# ✅ ФИНАЛЬНОЕ РЕШЕНИЕ: Авторизация по ID ИЛИ username

## Проблема

Добавленный по @username сотрудник не может войти - бот просит код доступа.

## Решение (ПРОСТОЕ)

Один универсальный метод который ищет **ПО ОБОИМ полям сразу**:
- Сначала по `tg_user_id`
- Если не нашел → по `username`
- Если нашел по username → автоматически обновляет `tg_user_id`

---

## Установка (1 шаг!)

### ✅ Добавить ОДИН метод в `services_db.py`

**Файл:** `field_service/bots/admin_bot/services_db.py`  
**Где:** После метода `get_by_tg_id` (~строка 2690)

**Вставить:**

```python
async def get_by_tg_id_or_username(
    self,
    tg_id: int,
    username: Optional[str] = None,
    update_tg_id: bool = True,
) -> Optional[StaffUser]:
    """
    Найти сотрудника по Telegram ID ИЛИ username.
    
    Сначала ищет по tg_user_id, если не нашел - ищет по username.
    Если нашел по username но tg_user_id=NULL - автоматически обновляет.
    """
    if tg_id is None:
        return None
    
    async with self._session_factory() as session:
        # 1. Пытаемся найти по tg_user_id
        row = await session.execute(
            select(m.staff_users).where(m.staff_users.tg_user_id == tg_id)
        )
        staff = row.scalar_one_or_none()
        
        # 2. Если не нашли по tg_id, пытаемся по username
        if not staff and username:
            normalized_username = username.lower().lstrip("@")
            row = await session.execute(
                select(m.staff_users).where(
                    m.staff_users.username == normalized_username
                )
            )
            staff = row.scalar_one_or_none()
            
            # 3. Если нашли по username и tg_user_id=NULL - обновляем
            if staff and staff.tg_user_id is None and update_tg_id:
                async with session.begin():
                    staff.tg_user_id = tg_id
                    await session.flush()
                    live_log.push(
                        "staff",
                        f"tg_id linked: staff_id={staff.id} username={normalized_username} tg_id={tg_id}"
                    )
        
        if not staff:
            return None
        
        # Загружаем города
        city_rows = await session.execute(
            select(m.staff_cities.city_id).where(
                m.staff_cities.staff_user_id == staff.id
            )
        )
        city_ids = frozenset(int(c[0]) for c in city_rows)
        
        return StaffUser(
            id=staff.id,
            tg_id=staff.tg_user_id or tg_id,
            role=_map_staff_role(staff.role),
            is_active=bool(staff.is_active),
            city_ids=city_ids,
            full_name=staff.full_name or "",
            phone=staff.phone or "",
        )
```

### ✅ Middleware уже обновлен!

Больше ничего делать не нужно - middleware уже использует новый метод!

---

## Как это работает

### Сценарий 1: Добавление по Telegram ID

```
1. Админ добавляет: ID 123456789
   DB: tg_user_id=123456789, username=NULL

2. Пользователь пишет /start (tg_id=123456789)
   → Находит сразу по tg_id ✅
```

### Сценарий 2: Добавление по username

```
1. Админ добавляет: @ivan_admin
   DB: tg_user_id=NULL, username='ivan_admin'

2. Иван пишет /start (tg_id=123456789, username='ivan_admin')
   Метод get_by_tg_id_or_username:
   a) Ищет по tg_id=123456789 → не находит
   b) Ищет по username='ivan_admin' → НАХОДИТ! ✅
   c) Обновляет: tg_user_id=123456789
   d) Возвращает StaffUser

3. DB теперь: tg_user_id=123456789, username='ivan_admin'
   При следующем входе найдет сразу по tg_id!
```

### Сценарий 3: Добавление по обоим

```
1. Админ добавляет: @ivan_admin ИЛИ 123456789
   DB: tg_user_id=123456789, username='ivan_admin'

2. Пользователь пишет /start
   → Находит сразу по tg_id ✅
```

---

## Перезапустить бота

```bash
# Ctrl+C для остановки
python -m field_service.bots.admin_bot
```

---

## Тестирование

### Тест 1: Новый пользователь по username ✅

```bash
# 1. В админ-боте
Персонал → Добавить → City Admin → @testuser → Города → Подтвердить

# 2. Проверить БД (опционально)
SELECT id, tg_user_id, username FROM staff_users WHERE username = 'testuser';
# Результат: tg_user_id = NULL

# 3. Попросить @testuser написать /start в админ-бот
# РЕЗУЛЬТАТ: ✅ Должен войти БЕЗ кода доступа!

# 4. Проверить БД снова
SELECT id, tg_user_id, username FROM staff_users WHERE username = 'testuser';
# Результат: tg_user_id = 123456789 (заполнен!)
```

### Тест 2: Пользователь по Telegram ID ✅

```bash
# 1. В админ-боте
Персонал → Добавить → Logist → 987654321 → Города → Подтвердить

# 2. Пользователь пишет /start
# РЕЗУЛЬТАТ: ✅ Должен войти сразу
```

### Тест 3: Username изменился ⚠️

```bash
# Если пользователь изменил username ПОСЛЕ добавления:
# 1. Старый username в БД: 'old_username'
# 2. Новый username в Telegram: 'new_username'
# 3. Если tg_user_id=NULL → НЕ НАЙДЕТ ❌

# РЕШЕНИЕ: Использовать Telegram ID вместо username
# ИЛИ: Удалить старую запись и добавить заново
```

---

## Отладка

### Проблема: Всё равно просит код доступа

**Проверьте:**

1. **Метод добавлен в services_db.py?**
   ```bash
   grep -n "get_by_tg_id_or_username" field_service/bots/admin_bot/services_db.py
   # Должен показать номер строки
   ```

2. **Правильный username в БД?**
   ```sql
   SELECT id, tg_user_id, username, is_active 
   FROM staff_users 
   WHERE username = 'ваш_username';
   ```
   - Username без @
   - is_active = true
   - Регистр НЕ важен (ищем через .lower())

3. **Бот перезапущен?**
   ```bash
   # Обязательно перезапустить после изменений!
   python -m field_service.bots.admin_bot
   ```

4. **Проверить логи:**
   ```bash
   # Должна быть строка при первом входе:
   # "tg_id linked: staff_id=... username=... tg_id=..."
   ```

---

## SQL для проверки

```sql
-- Посмотреть всех сотрудников добавленных по username
SELECT 
    id,
    tg_user_id,
    username,
    full_name,
    role,
    is_active,
    created_at
FROM staff_users
WHERE tg_user_id IS NULL
ORDER BY created_at DESC;

-- После первого входа tg_user_id должен заполниться:
SELECT 
    id,
    tg_user_id,
    username,
    full_name,
    role
FROM staff_users
WHERE username = 'ivan_admin';
-- tg_user_id должен быть НЕ NULL!
```

---

## Преимущества этого решения

### ✅ Простота
Один метод вместо двух - меньше кода, меньше ошибок

### ✅ Универсальность  
Работает для ЛЮБОГО способа добавления:
- По Telegram ID ✅
- По @username ✅
- По обоим сразу ✅

### ✅ Автоматическое обновление
При первом входе tg_user_id автоматически заполняется

### ✅ Производительность
При повторных входах ищет только по tg_user_id (быстро)

### ✅ Безопасность
- Username нормализуется (lowercase, без @)
- Обновление в транзакции
- Логирование связывания

---

## Что изменено

### 1. `services_db.py`
- ✅ Добавлен метод `get_by_tg_id_or_username()`
- Универсальный поиск по двум полям
- Автообновление tg_user_id

### 2. `middlewares.py`  
- ✅ Использует новый метод вместо старого `get_by_tg_id()`
- Передает и tg_id и username
- Автоматически связывает при первом входе

---

## Чеклист установки

- [ ] Добавить метод `get_by_tg_id_or_username` в `services_db.py`
- [x] Middleware уже обновлен автоматически
- [ ] Перезапустить бота
- [ ] Добавить тестового пользователя по @username
- [ ] Попросить его написать /start
- [ ] ✅ Проверить что вошел БЕЗ кода доступа

---

## Статус

**✅ ГОТОВО - ПРОСТОЕ И НАДЕЖНОЕ РЕШЕНИЕ**

Версия: 1.2 (финальная)  
Дата: 04.10.2025

**Время установки:** 1 минута  
**Сложность:** Минимальная 🚀

---

## Быстрая справка

**Файл:** `services_db.py`  
**Метод:** `get_by_tg_id_or_username()`  
**Строк кода:** ~60

**Что делает:**
1. Ищет по tg_id → нашел? → возвращает
2. Не нашел? → ищет по username → нашел? → обновляет tg_id → возвращает  
3. Не нашел? → возвращает None

**Всё!** 🎉
