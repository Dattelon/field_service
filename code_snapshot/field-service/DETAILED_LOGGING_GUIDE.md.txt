# Детализированное логирование для create/assign операций

## Что добавлено

### 1. Новый модуль operation_logger.py

Создан модуль `field_service/services/operation_logger.py` с функциями для детального логирования:

- `generate_request_id()` - генерация уникального request_id
- `log_order_creation_start()` - логирование начала создания
- `log_order_created()` - логирование успешного создания 
- `log_order_creation_error()` - логирование ошибки создания
- `log_assign_start()` - логирование начала назначения
- `log_assign_attempt()` - логирование попытки назначения
- `log_assign_sql_result()` - логирование результата SQL
- `log_assign_success()` - логирование успешного назначения
- `log_assign_error()` - логирование ошибки назначения
- `log_callback_handler_entry()` - логирование входа в callback
- `log_callback_handler_exit()` - логирование выхода из callback

### 2. Изменения в файлах

Необходимо добавить импорт и вызовы logger в следующих местах:

#### `field_service/bots/admin_bot/services/orders.py`

В начало файла добавить:
```python
from field_service.services import operation_logger as oplog
```

В метод `create_order()` добавить логи:

**В начале метода:**
```python
async def create_order(self, data: NewOrderData) -> int:
    request_id = oplog.generate_request_id()
    oplog.log_order_creation_start(
        request_id=request_id,
        staff_id=data.created_by_staff_id,
        city_id=data.city_id,
        category=data.category.value if data.category else "UNKNOWN",
        initial_status=data.initial_status or "AUTO",
    )
    
    try:
        async with self._session_factory() as session:
            async with session.begin():
                # ... существующий код ...
```

**После успешного создания (перед return order.id):**
```python
                # После всех session.add()
                await session.flush()
                
                oplog.log_order_created(
                    request_id=request_id,
                    order_id=order.id,
                    status=initial_status.value,
                    staff_id=data.created_by_staff_id,
                    tx_id=str(session.get_transaction()._trans.connection) if hasattr(session, '_trans') else None,
                )
                
            return order.id
    except Exception as e:
        oplog.log_order_creation_error(
            request_id=request_id,
            error=str(e),
            staff_id=data.created_by_staff_id,
        )
        raise
```

В метод `assign_master()` добавить логи:

**В начале метода:**
```python
async def assign_master(self, order_id: int, master_id: int, by_staff_id: int) -> bool:
    request_id = oplog.generate_request_id()
    
    try:
        async with self._session_factory() as session:
            async with session.begin():
                order_q = await session.execute(
                    select(m.orders)
                    .where(m.orders.id == order_id)
                    .with_for_update()
                )
                order = order_q.scalar_one_or_none()
                if not order:
                    oplog.log_assign_error(
                        request_id=request_id,
                        order_id=order_id,
                        error="Order not found",
                        staff_id=by_staff_id,
                        callback_data=f"assign:manual:{order_id}:{master_id}",
                    )
                    return False
                
                oplog.log_assign_start(
                    request_id=request_id,
                    order_id=order_id,
                    master_id=master_id,
                    staff_id=by_staff_id,
                    callback_data=f"assign:manual:{order_id}:{master_id}",
                    current_status=order.status.value,
                )
                
                # ... проверки доступа и мастера ...
                
                prev_status = order.status
                
                oplog.log_assign_attempt(
                    request_id=request_id,
                    order_id=order.id,
                    old_status=prev_status.value,
                    new_status=m.OrderStatus.ASSIGNED.value,
                    master_id=master.id,
                    staff_id=by_staff_id,
                    actor="ADMIN",
                )
                
                # Изменение статуса заказа
                order.assigned_master_id = master.id
                order.status = m.OrderStatus.ASSIGNED
                order.updated_at = datetime.now(UTC)
                order.version = (order.version or 0) + 1
                order.cancel_reason = None
                
                # Запись в историю
                session.add(m.order_status_history(...))
                
                # Отмена других офферов
                res = await session.execute(update(m.offers)...)
                rows_affected = getattr(res, "rowcount", 0) or 0
                
                oplog.log_assign_sql_result(
                    request_id=request_id,
                    order_id=order.id,
                    rows_affected=rows_affected,
                    operation="cancel_offers",
                )
                
                await session.flush()
                
                oplog.log_assign_success(
                    request_id=request_id,
                    order_id=order.id,
                    master_id=master.id,
                    old_status=prev_status.value,
                    new_status=m.OrderStatus.ASSIGNED.value,
                    staff_id=by_staff_id,
                    tx_id=str(session.get_transaction()._trans.connection) if hasattr(session, '_trans') else None,
                )
                
        return True
    except Exception as e:
        oplog.log_assign_error(
            request_id=request_id,
            order_id=order_id,
            error=str(e),
            staff_id=by_staff_id,
            callback_data=f"assign:manual:{order_id}:{master_id}",
        )
        raise
```

#### `field_service/bots/admin_bot/handlers/orders/queue.py`

В начало файла добавить:
```python
from field_service.services import operation_logger as oplog
```

В обработчики callback добавить логи:

**В `cb_queue_assign_manual_pick()`:**
```python
async def cb_queue_assign_manual_pick(cq: CallbackQuery, staff: StaffUser) -> None:
    request_id = oplog.generate_request_id()
    
    parts = cq.data.split(":")
    try:
        order_id = int(parts[4])
        page = int(parts[5])
        master_id = int(parts[6])
    except (IndexError, ValueError):
        oplog.log_callback_handler_entry(
            handler_name="cb_queue_assign_manual_pick",
            callback_data=cq.data,
            staff_id=staff.id,
            request_id=request_id,
        )
        oplog.log_callback_handler_exit(
            handler_name="cb_queue_assign_manual_pick",
            request_id=request_id,
            success=False,
            result="Invalid callback data format",
        )
        await _safe_answer(cq, "❌ Неверный формат", show_alert=True)
        return
    
    oplog.log_callback_handler_entry(
        handler_name="cb_queue_assign_manual_pick",
        callback_data=cq.data,
        staff_id=staff.id,
        request_id=request_id,
    )
    
    try:
        # ... существующий код ...
        
        ok, message = await distribution_service.send_manual_offer(...)
        
        oplog.log_callback_handler_exit(
            handler_name="cb_queue_assign_manual_pick",
            request_id=request_id,
            success=ok,
            result=f"offer_sent:{master_id}" if ok else message,
        )
        
        # ... rest of handler ...
    except Exception as e:
        oplog.log_callback_handler_exit(
            handler_name="cb_queue_assign_manual_pick",
            request_id=request_id,
            success=False,
            result=f"exception:{str(e)}",
        )
        raise
```

**В `cb_queue_assign_auto()`:**
```python
async def cb_queue_assign_auto(cq: CallbackQuery, staff: StaffUser) -> None:
    request_id = oplog.generate_request_id()
    
    parts = cq.data.split(":")
    try:
        order_id = int(parts[4])
    except (IndexError, ValueError):
        await _safe_answer(cq, "Неверный формат", show_alert=True)
        return
    
    oplog.log_callback_handler_entry(
        handler_name="cb_queue_assign_auto",
        callback_data=cq.data,
        staff_id=staff.id,
        request_id=request_id,
    )
    
    try:
        # ... существующий код ...
        
        ok, result = await distribution_service.assign_auto(order_id, staff.id)
        
        oplog.log_callback_handler_exit(
            handler_name="cb_queue_assign_auto",
            request_id=request_id,
            success=ok,
            result=f"code:{result.code},master:{result.master_id}",
        )
        
        # ... rest of handler ...
    except Exception as e:
        oplog.log_callback_handler_exit(
            handler_name="cb_queue_assign_auto",
            request_id=request_id,
            success=False,
            result=f"exception:{str(e)}",
        )
        raise
```

### 3. Формат логов

Все логи пишутся через стандартный Python logger с уровнем INFO/ERROR.

Пример вывода:
```
[INFO] [CREATE_ORDER_START] request_id=req_7f9a3b | staff_id=5 | city_id=1 | category=ELECTRICS | initial_status=AUTO
[INFO] [CREATE_ORDER_SUCCESS] request_id=req_7f9a3b | order_id=123 | status=SEARCHING | staff_id=5 | tx_id=...
[INFO] [ASSIGN_START] request_id=req_8c4d2a | order_id=123 | master_id=42 | staff_id=5 | callback_data=adm:q:as:pick:123:1:42 | current_status=SEARCHING
[INFO] [ASSIGN_ATTEMPT] request_id=req_8c4d2a | order_id=123 | old_status=SEARCHING → new_status=ASSIGNED | master_id=42 | staff_id=5 | actor=ADMIN
[INFO] [ASSIGN_SQL] request_id=req_8c4d2a | order_id=123 | operation=cancel_offers | rows_affected=2
[INFO] [ASSIGN_SUCCESS] request_id=req_8c4d2a | order_id=123 | master_id=42 | SEARCHING → ASSIGNED | staff_id=5 | tx_id=...
```

### 4. Конфигурация логирования

Добавить в основной конфиг приложения настройку уровня для operation_logger:

```python
logging.getLogger("field_service.services.operation_logger").setLevel(logging.INFO)
```

## Тестирование

После применения изменений:

1. Создать заказ через админ-бота
2. Назначить мастера вручную
3. Назначить заказ автоматически
4. Проверить логи на наличие всех ключевых событий с request_id

## Что логируется

- **request_id** - уникальный ID запроса для трассировки
- **order_id** - ID заказа
- **old_status / new_status** - переходы статусов
- **master_id** - ID назначаемого мастера
- **staff_id / actor** - кто выполнил операцию
- **tx_id** - ID транзакции БД (опционально)
- **callback_data** - данные callback кнопки
- **rows_affected** - количество затронутых строк в SQL
- **success / result** - результат операции
