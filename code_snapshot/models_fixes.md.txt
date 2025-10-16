# Исправления для field_service/db/models.py

## Выявленные проблемы

### 1. Таблица `orders` - ОТСУТСТВУЕТ поле `cancel_reason`

**В БД (ALL_BD.md):**
```sql
cancel_reason | text | | |
```

**В models.py:**
Поле полностью отсутствует.

**Исправление:**
```python
class orders(Base):
    # ... существующие поля ...
    
    # ДОБАВИТЬ:
    cancel_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
```

---

### 2. Таблица `commissions` - ОТСУТСТВУЕТ поле `paid_at`

**В БД (ALL_BD.md):**
```sql
paid_at | timestamp with time zone | | |
```

**В models.py:**
Есть `paid_reported_at` и `paid_approved_at`, но отсутствует `paid_at`.

**Анализ:** Похоже, что в БД есть legacy-поле `paid_at`, которое больше не используется. Нужно добавить его для совместимости со схемой, но помечать как deprecated.

**Исправление:**
```python
class commissions(Base):
    # ... существующие поля ...
    
    # ДОБАВИТЬ (legacy field, используйте paid_approved_at):
    paid_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), 
        nullable=True,
        comment="DEPRECATED: Use paid_approved_at instead"
    )
```

---

### 3. Таблица `commissions` - неправильный FK на `order_id`

**В БД (ALL_BD.md):**
```sql
FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE
```

**В models.py:**
```python
order_id: Mapped[int] = mapped_column(
    Integer,
    nullable=False,
    index=True,
)
```

**Комментарий в коде:**
> "В тестах есть сценарии, где комиссии создаются без таблицы orders"

**Проблема:** 
Модель не соответствует реальной БД. FK должен быть определен.

**Исправление:**
```python
class commissions(Base):
    # ИЗМЕНИТЬ:
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,  # В БД есть uq_commissions__order_id
        index=True,
    )
```

---

### 4. Таблица `offers` - отсутствует FK на `master_id`

**В БД (ALL_BD.md):**
```sql
FOREIGN KEY (master_id) REFERENCES masters(id) ON DELETE CASCADE
```

**В models.py:**
```python
master_id: Mapped[int] = mapped_column(
    Integer,
    nullable=False,
    index=True,
)
```

**Комментарий в коде:**
> "NOTE: FK на masters.id убран ради изоляционных тестов"

**Проблема:**
Модель не соответствует БД, что может вызвать проблемы при создании/обновлении схемы через Alembic.

**Исправление:**
```python
class offers(Base):
    # ИЗМЕНИТЬ:
    master_id: Mapped[int] = mapped_column(
        ForeignKey("masters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # УДАЛИТЬ viewonly=True из relationship:
    master: Mapped["masters"] = relationship(
        "masters",
        lazy="raise_on_sql",
    )
```

---

### 5. Таблица `staff_access_codes` - неправильное имя поля FK

**В БД (ALL_BD.md):**
```sql
created_by_staff_id | integer | | | | plain
FOREIGN KEY (created_by_staff_id) REFERENCES staff_users(id) ON DELETE SET NULL
```

**В models.py:**
```python
issued_by_staff_id: Mapped[Optional[int]] = mapped_column(
    ForeignKey("staff_users.id", ondelete="SET NULL"), nullable=True
)
```

**Проблема:**
Имя поля в models.py (`issued_by_staff_id`) не совпадает с именем в БД (`created_by_staff_id`).

**Исправление:**
```python
class staff_access_codes(Base):
    # ИЗМЕНИТЬ:
    created_by_staff_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("staff_users.id", ondelete="SET NULL"), nullable=True
    )
    
    # ДОБАВИТЬ алиас для обратной совместимости:
    issued_by_staff_id = synonym("created_by_staff_id")
    
    # ИЗМЕНИТЬ relationship:
    created_by_staff: Mapped[Optional["staff_users"]] = relationship(
        foreign_keys=[created_by_staff_id]
    )
    # Алиас для обратной совместимости:
    issued_by_staff = synonym("created_by_staff")
```

---

### 6. Таблица `staff_access_codes` - ОТСУТСТВУЕТ поле `revoked_at`

**В БД (ALL_BD.md):**
```sql
revoked_at | timestamp with time zone | | | | plain
```

**В models.py:**
Поле отсутствует, есть только `is_revoked` (bool).

**Исправление:**
```python
class staff_access_codes(Base):
    # ... существующие поля ...
    
    # ДОБАВИТЬ:
    revoked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
```

---

### 7. Дубликаты в миграциях Alembic

**Проблема:**
В папке `alembic/versions/` множество миграций, которые могут содержать устаревшие определения таблиц.

**Рекомендация:**
1. Проверить последнюю миграцию и убедиться, что она соответствует models.py
2. Создать новую миграцию autogenerate после исправления models.py
3. Удалить старые/дублирующиеся миграции, если они больше не нужны

---

## План действий

1. **Применить исправления к models.py** (см. выше)

2. **Создать новую миграцию Alembic:**
   ```bash
   alembic revision --autogenerate -m "fix_models_sync_with_db"
   ```

3. **Проверить сгенерированную миграцию:**
   - Убедиться, что добавлены отсутствующие поля
   - Убедиться, что FK определены правильно

4. **Применить миграцию:**
   ```bash
   alembic upgrade head
   ```

5. **Обновить тесты:**
   - Найти тесты, которые создают commissions без orders
   - Исправить их для соблюдения FK constraints
   - Аналогично для offers без masters

---

## Дополнительные замечания

### Compatibility Layer
В models.py активно используются `synonym()` для обеспечения обратной совместимости. Это хорошая практика при рефакторинге.

### Legacy Fields
Некоторые поля помечены как deprecated или legacy:
- `order_type` (алиас `type`)
- `final_amount` (алиас `total_sum`)
- `master_id` (алиас `assigned_master_id`)

Эти алиасы следует сохранить для поддержки старого кода.

### Test Isolation
Комментарии в коде указывают на то, что некоторые FK были убраны для изоляции тестов. Это антипаттерн. Правильное решение:
- Использовать фикстуры, которые создают зависимые объекты
- Использовать `relationship(..., viewonly=True)` вместо удаления FK
- Использовать мокирование в юнит-тестах

---

## Итоговый файл с исправлениями

См. отдельный артефакт с полным исправленным файлом models.py.
