# P0 ЗАДАЧА 1: МОДЕРАЦИЯ МАСТЕРОВ - АНАЛИЗ И РЕАЛИЗАЦИЯ

## СТАТУС: ✅ ГОТОВО (требуется только добавить недостающие методы)

### ЧТО УЖЕ РЕАЛИЗОВАНО:

1. **Роутеры:**
   - ✅ `admin_moderation.py` - обработчики для модерации
   - ✅ `admin_masters.py` - логика списков и карточек мастеров

2. **UI компоненты:**
   - ✅ Кнопка "🛠 Модерация" в главном меню (`keyboards.py:25`)
   - ✅ Список анкет на модерации с пагинацией
   - ✅ Карточка мастера с полной информацией
   - ✅ Кнопки "✅ Одобрить" / "❌ Отклонить"
   - ✅ FSM для ввода причины отклонения
   - ✅ Уведомления мастеру через `notify_master()`

3. **Сервисные методы:**
   Нужно проверить наличие в `DBMastersService`:
   - `approve_master(master_id, by_staff_id)` - одобрение
   - `reject_master(master_id, reason, by_staff_id)` - отклонение  
   - `block_master(master_id, reason, by_staff_id)` - блокировка
   - `unblock_master(master_id, by_staff_id)` - разблокировка
   - `set_master_limit(master_id, limit, by_staff_id)` - изменение лимита
   - `enqueue_master_notification(master_id, message)` - отправка уведомления

### ТРЕБУЕТСЯ ДОРАБОТКА:

1. **Добавить недостающие методы в services_db.py:**

```python
# В класс DBMastersService добавить:

async def approve_master(self, master_id: int, by_staff_id: int) -> bool:
    """Одобрить мастера - установить verified=True, moderation_status=APPROVED"""
    async with self._session_factory() as session:
        async with session.begin():
            result = await session.execute(
                update(m.masters)
                .where(m.masters.id == master_id)
                .values(
                    verified=True,
                    moderation_status=m.ModerationStatus.APPROVED,
                    verified_at=datetime.now(UTC),
                    verified_by=by_staff_id,
                )
                .returning(m.masters.id)
            )
            if not result.first():
                return False
            
            await self._log_admin_action(
                session,
                admin_id=by_staff_id,
                master_id=master_id,
                action="approve_master",
                payload={},
            )
            live_log.push("moderation", f"master#{master_id} approved by staff#{by_staff_id}")
    return True


async def reject_master(self, master_id: int, reason: str, by_staff_id: int) -> bool:
    """Отклонить анкету мастера"""
    async with self._session_factory() as session:
        async with session.begin():
            result = await session.execute(
                update(m.masters)
                .where(m.masters.id == master_id)
                .values(
                    verified=False,
                    moderation_status=m.ModerationStatus.REJECTED,
                    moderation_reason=reason,
                )
                .returning(m.masters.id)
            )
            if not result.first():
                return False
            
            await self._log_admin_action(
                session,
                admin_id=by_staff_id,
                master_id=master_id,
                action="reject_master",
                payload={"reason": reason},
            )
            live_log.push("moderation", f"master#{master_id} rejected by staff#{by_staff_id}: {reason}")
    return True


async def block_master(self, master_id: int, reason: str, by_staff_id: int) -> bool:
    """Заблокировать мастера"""
    async with self._session_factory() as session:
        async with session.begin():
            result = await session.execute(
                update(m.masters)
                .where(m.masters.id == master_id)
                .values(
                    is_blocked=True,
                    is_active=False,
                    blocked_at=datetime.now(UTC),
                    blocked_reason=reason,
                )
                .returning(m.masters.id)
            )
            if not result.first():
                return False
            
            await self._log_admin_action(
                session,
                admin_id=by_staff_id,
                master_id=master_id,
                action="block_master",
                payload={"reason": reason},
            )
            live_log.push("moderation", f"master#{master_id} blocked by staff#{by_staff_id}: {reason}")
    return True


async def unblock_master(self, master_id: int, by_staff_id: int) -> bool:
    """Разблокировать мастера"""
    async with self._session_factory() as session:
        async with session.begin():
            result = await session.execute(
                update(m.masters)
                .where(m.masters.id == master_id)
                .values(
                    is_blocked=False,
                    is_active=True,
                    blocked_at=None,
                    blocked_reason=None,
                )
                .returning(m.masters.id)
            )
            if not result.first():
                return False
            
            await self._log_admin_action(
                session,
                admin_id=by_staff_id,
                master_id=master_id,
                action="unblock_master",
                payload={},
            )
            live_log.push("moderation", f"master#{master_id} unblocked by staff#{by_staff_id}")
    return True


async def set_master_limit(self, master_id: int, limit: int, by_staff_id: int) -> bool:
    """Установить индивидуальный лимит активных заказов"""
    async with self._session_factory() as session:
        async with session.begin():
            result = await session.execute(
                update(m.masters)
                .where(m.masters.id == master_id)
                .values(max_active_orders_override=limit)
                .returning(m.masters.id)
            )
            if not result.first():
                return False
            
            await self._log_admin_action(
                session,
                admin_id=by_staff_id,
                master_id=master_id,
                action="set_limit",
                payload={"limit": limit},
            )
            live_log.push("moderation", f"master#{master_id} limit set to {limit} by staff#{by_staff_id}")
    return True


async def enqueue_master_notification(self, master_id: int, message: str) -> None:
    """Добавить уведомление в очередь для отправки мастеру"""
    async with self._session_factory() as session:
        async with session.begin():
            # Получить tg_user_id мастера
            row = await session.execute(
                select(m.masters.tg_user_id).where(m.masters.id == master_id)
            )
            tg_user_id = row.scalar_one_or_none()
            
            if not tg_user_id:
                logger.warning(f"Cannot notify master#{master_id}: no tg_user_id")
                return
            
            # Записать в notifications_outbox
            await session.execute(
                insert(m.notifications_outbox).values(
                    master_id=master_id,
                    event="moderation_update",
                    payload={"message": message},
                )
            )
            live_log.push("moderation", f"notification queued for master#{master_id}")
```

2. **Проверить интеграцию с мастер-ботом:**
   - Уведомления из `notifications_outbox` должны обрабатываться watcher'ом
   - Мастер должен получить сообщение при одобрении/отклонении

### ТЕСТИРОВАНИЕ:

1. **Запустить админ-бот:**
   ```bash
   python -m field_service.bots.admin_bot.main
   ```

2. **Проверить UI:**
   - /start → кнопка "🛠 Модерация"
   - Должен показаться список мастеров со статусом PENDING
   - Открыть карточку мастера
   - Кнопки "✅ Одобрить" / "❌ Отклонить" должны работать

3. **Проверить уведомления:**
   - После одобрения мастер должен получить: "Анкета одобрена. Вам доступна смена."
   - После отклонения: "Анкета отклонена. Причина: {reason}"

### ОЦЕНКА ТРУДОЗАТРАТ:
- Добавление методов в services_db.py: **15 минут**
- Тестирование: **10 минут**
- **ИТОГО: 25 минут**

---

## СЛЕДУЮЩИЕ ШАГИ:

После завершения P0-1 переходим к:
- P0-2: Валидация телефона при онбординге
- P0-3: Уведомление мастеру о блокировке  
- P0-4: Отображение телефона клиента при ASSIGNED
