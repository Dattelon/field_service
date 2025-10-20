# Рефакторинг accept_offer: Централизация логики принятия оффера

**Дата:** 2025-10-15  
**Статус:** ✅ Выполнено  
**Цель:** Устранить разрозненную логику принятия оффера и использовать SELECT ... FOR UPDATE SKIP LOCKED

## Проблема

Логика принятия оффера была разбросана по обработчику `offer_accept` в мастер-боте (~440 строк). Это приводило к:
- Сложности поддержки и тестирования
- Дублированию кода при добавлении других способов принятия
- Отсутствию единой точки для атомарных операций
- Риску Race Condition при параллельных запросах

## Решение

### 1. Создан централизованный сервис

**Файл:** `field_service/services/orders_service.py`

```python
class OrdersService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.metrics_service = DistributionMetricsService()
    
    async def accept_offer(
        self,
        offer_id: int,
        master_id: int,
    ) -> tuple[bool, Optional[str]]:
        """
        Атомарное принятие оффера мастером.
        
        Использует SELECT ... FOR UPDATE SKIP LOCKED для предотвращения Race Condition.
        """
```

### 2. Ключевые улучшения

#### 2.1. Атомарные блокировки с SKIP LOCKED

```python
# Блокировка оффера
offer_stmt = (
    select(...)
    .where(...)
    .with_for_update(skip_locked=True)  # ✅ Атомарная блокировка
)

# Блокировка заказа
order_stmt = (
    select(...)
    .where(...)
    .with_for_update(skip_locked=True)  # ✅ Атомарная блокировка
)
```

**Преимущества:**
- Если оффер/заказ уже заблокирован другой транзакцией - сразу возвращаем ошибку
- Нет ожидания освобождения блокировки
- Предотвращение дедлоков

#### 2.2. Валидация состояния оффера

```python
# Проверяем состояние оффера
if offer_state not in (m.OfferState.SENT, m.OfferState.VIEWED):
    if offer_state == m.OfferState.EXPIRED:
        return False, "⏰ Время истекло. Заказ ушёл другим мастерам."
    elif offer_state == m.OfferState.DECLINED:
        return False, "❌ Вы уже отклонили этот заказ"
    # ...
```

#### 2.3. Проверка expires_at

```python
now_utc = datetime.now(timezone.utc)
if expires_at and expires_at < now_utc:
    return False, "⏰ Время истекло. Заказ ушёл другим мастерам."
```

#### 2.4. Атомарное обновление заказа с версионированием

```python
update_result = await self.session.execute(
    update(m.orders)
    .where(
        and_(
            m.orders.id == order_id,
            m.orders.assigned_master_id.is_(None),
            m.orders.status == current_status,
            m.orders.version == current_version,  # ✅ Оптимистичная блокировка
        )
    )
    .values(
        assigned_master_id=master_id,
        status=m.OrderStatus.ASSIGNED,
        updated_at=func.now(),
        version=current_version + 1,  # ✅ Инкремент версии
    )
    .returning(m.orders.id)
)
```

#### 2.5. Централизованная запись метрик

```python
await self.metrics_service.record_assignment(
    order_id=order_id,
    master_id=master_id,
    round_number=stats_row.max_round or 1,
    candidates_count=stats_row.total_candidates or 1,
    time_to_assign_seconds=time_to_assign,
    # ...
    session=self.session,  # ✅ Передаём существующую сессию
)
```

### 3. Обновлён DistributionMetricsService

Добавлен параметр `session: Optional[AsyncSession] = None` в метод `record_assignment`:

```python
async def record_assignment(
    self,
    *,
    # ... параметры
    session: Optional[AsyncSession] = None,  # ✅ Опциональная сессия
) -> None:
    # Если передана сессия - используем её (без commit)
    if session is not None:
        await session.execute(insert(...))
        # НЕ делаем commit - это ответственность вызывающего кода
    else:
        # Создаём свою сессию и делаем commit
        async with self._session_factory() as new_session:
            await new_session.execute(insert(...))
            await new_session.commit()
```

### 4. Упрощён обработчик в мастер-боте

**До:** ~440 строк со сложной логикой  
**После:** ~82 строки с простой логикой

```python
@router.callback_query(F.data.regexp(r"^m:new:acc:(\d+)(?::(\d+))?$"))
async def offer_accept(
    callback: CallbackQuery,
    session: AsyncSession,
    master: m.masters,
) -> None:
    # 1. Парсим callback_data
    order_id, page = _parse_offer_callback_payload(callback.data, "acc")
    
    # 2. Проверка блокировки мастера
    if master.is_blocked:
        ...
        return
    
    # 3. Проверка лимита активных заказов
    if active_orders >= limit:
        ...
        return
    
    # 4. Находим offer_id
    offer_id = ...
    
    # 5. Используем централизованный сервис
    orders_service = OrdersService(session)
    success, error_message = await orders_service.accept_offer(
        offer_id=offer_id,
        master_id=master.id,
    )
    
    # 6. Показываем результат
    if not success:
        ...
    else:
        await _render_active_order(callback, session, master, order_id=order_id)
```

### 5. Добавлены частичные индексы

**Файл:** `migrations/2025-10-15_add_offers_partial_indexes.sql`

```sql
-- Индекс для активных офферов (SENT, VIEWED)
CREATE INDEX CONCURRENTLY idx_offers_active_state
ON offers (order_id, master_id, state)
WHERE state IN ('SENT', 'VIEWED');

-- Индекс для неистекших офферов
CREATE INDEX CONCURRENTLY idx_offers_not_expired
ON offers (order_id, master_id)
WHERE expires_at > NOW();

-- Уникальный индекс для предотвращения дублей
CREATE UNIQUE INDEX CONCURRENTLY idx_offers_order_master_active
ON offers (order_id, master_id)
WHERE state IN ('SENT', 'VIEWED', 'ACCEPTED');

-- Индекс для списка офферов мастера
CREATE INDEX CONCURRENTLY idx_offers_master_active
ON offers (master_id, state, sent_at DESC)
WHERE state IN ('SENT', 'VIEWED');
```

## Преимущества

### 1. Централизация логики
- Единая точка для принятия оффера
- Легко добавить другие способы принятия (админ-бот, API)
- Упрощённое тестирование

### 2. Атомарность операций
- `SELECT ... FOR UPDATE SKIP LOCKED` предотвращает Race Condition
- Версионирование заказов через `version` поле
- Транзакционная консистентность

### 3. Улучшенная производительность
- Частичные индексы для быстрого поиска активных офферов
- Минимизация времени удержания блокировок
- Оптимизированные запросы

### 4. Лучшая обработка ошибок
- Детальные сообщения об ошибках
- Разделение типов ошибок (истёк/отклонён/занят)
- Корректное логирование

### 5. Упрощённая поддержка
- Меньше кода в обработчике (440 → 82 строки)
- Чистая архитектура (handler → service → repository)
- Явные зависимости

## План применения

### Шаг 1: Создать миграцию индексов
```bash
docker exec -i fs_postgres psql -U field_user -d field_service < migrations/2025-10-15_add_offers_partial_indexes.sql
```

### Шаг 2: Проверить работу локально
```bash
cd C:\ProjectF\field-service
docker compose up -d postgres
pytest tests/ -v -k test_accept_offer
```

### Шаг 3: Деплой на сервер
```bash
# Через WinSCP загрузить файлы:
# - field_service/services/orders_service.py
# - field_service/services/distribution_metrics_service.py (обновлённый)
# - field_service/bots/master_bot/handlers/orders.py (обновлённый)
# - migrations/2025-10-15_add_offers_partial_indexes.sql

# На сервере:
ssh root@217.199.254.27
cd /opt/field-service
docker compose down
docker compose up -d postgres

# Применить миграцию
docker exec -i fs_postgres psql -U field_user -d field_service < migrations/2025-10-15_add_offers_partial_indexes.sql

# Запустить боты
docker compose up -d
docker compose logs -f --tail=100
```

### Шаг 4: Мониторинг
```bash
# Проверить индексы
docker exec fs_postgres psql -U field_user -d field_service -c "
SELECT schemaname, tablename, indexname, indexdef
FROM pg_indexes
WHERE tablename = 'offers'
ORDER BY indexname;"

# Проверить логи
docker compose logs -f master-bot | grep "offer_accept"
docker compose logs -f admin-bot | grep "offer_accept"
```

## Тесты

### Тест 1: Простое принятие оффера
```python
# Создать мастера и заказ
# Отправить оффер
# Мастер принимает оффер
# Проверить: order.status == ASSIGNED, order.assigned_master_id == master.id
```

### Тест 2: Параллельное принятие (Race Condition)
```python
# Создать 2 мастеров и 1 заказ
# Отправить офферы обоим
# Оба одновременно пытаются принять (asyncio.gather)
# Проверить: только один успешно принял, у второго ошибка "⚠️ Заказ уже занят"
```

### Тест 3: Истекший оффер
```python
# Создать мастера и заказ
# Отправить оффер с expires_at в прошлом
# Мастер пытается принять
# Проверить: ошибка "⏰ Время истекло"
```

### Тест 4: Блокированный мастер
```python
# Создать заблокированного мастера
# Отправить оффер
# Мастер пытается принять
# Проверить: ошибка с причиной блокировки
```

### Тест 5: Превышен лимит активных
```python
# Создать мастера с лимитом 5
# Назначить ему 5 активных заказов
# Отправить новый оффер
# Мастер пытается принять
# Проверить: ошибка "⚠️ Превышен лимит активных заказов"
```

## Откаты (Rollback)

Если что-то пошло не так:

### 1. Откатить индексы
```sql
DROP INDEX CONCURRENTLY IF EXISTS idx_offers_active_state;
DROP INDEX CONCURRENTLY IF EXISTS idx_offers_not_expired;
DROP INDEX CONCURRENTLY IF EXISTS idx_offers_order_master_active;
DROP INDEX CONCURRENTLY IF EXISTS idx_offers_master_active;
```

### 2. Откатить код
```bash
git checkout HEAD~1 field_service/services/orders_service.py
git checkout HEAD~1 field_service/services/distribution_metrics_service.py
git checkout HEAD~1 field_service/bots/master_bot/handlers/orders.py
```

### 3. Перезапустить боты
```bash
docker compose restart master-bot admin-bot
```

## Итоги

✅ **Код стал проще:** 440 → 82 строки в обработчике  
✅ **Атомарность:** SELECT ... FOR UPDATE SKIP LOCKED  
✅ **Производительность:** Частичные индексы  
✅ **Поддержка:** Единая точка логики  
✅ **Тестируемость:** Изолированный сервис  

**Токенов осталось:** 64837/190000
