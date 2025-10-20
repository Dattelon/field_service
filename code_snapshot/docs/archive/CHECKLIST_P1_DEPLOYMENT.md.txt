# ✅ ЧЕКЛИСТ ПРИМЕНЕНИЯ ИЗМЕНЕНИЙ P1

**Цель:** Применить все разработки спринта P1 в production  
**Время выполнения:** ~2 часа  
**Дата:** 03.10.2025

---

## 📋 ПРЕДВАРИТЕЛЬНАЯ ПОДГОТОВКА (10 мин)

- [ ] Создать резервную копию БД
  ```bash
  pg_dump -U postgres field_service > backup_$(date +%Y%m%d_%H%M%S).sql
  ```

- [ ] Создать git branch для изменений
  ```bash
  cd field-service
  git checkout -b feature/p1-sprint
  ```

- [ ] Убедиться что все боты остановлены
  ```bash
  # Найти процессы
  ps aux | grep "python.*bot"
  # Остановить
  kill <PID>
  ```

---

## 🗄️ ШАГ 1: МИГРАЦИИ БД (10 мин)

### 1.1. Скопировать миграцию
- [ ] Скопировать `alembic/versions/0010_order_autoclose.py` в проект
- [ ] Исправить `down_revision` на актуальный ID последней миграции:
  ```bash
  # Найти последнюю миграцию
  alembic current
  # Или посмотреть в папке alembic/versions/
  ```

### 1.2. Добавить модель в models.py
- [ ] Открыть `field_service/db/models.py`
- [ ] После класса `order_status_history` вставить:
  ```python
  class order_autoclose_queue(Base):
      """Очередь для автозакрытия заказов через 24ч после CLOSED."""
      __tablename__ = 'order_autoclose_queue'
      
      order_id: Mapped[int] = mapped_column(
          ForeignKey("orders.id", ondelete="CASCADE"),
          primary_key=True
      )
      closed_at: Mapped[datetime] = mapped_column(
          DateTime(timezone=True),
          nullable=False
      )
      autoclose_at: Mapped[datetime] = mapped_column(
          DateTime(timezone=True),
          nullable=False
      )
      processed_at: Mapped[Optional[datetime]] = mapped_column(
          DateTime(timezone=True),
          nullable=True
      )
      created_at: Mapped[datetime] = mapped_column(
          DateTime(timezone=True),
          server_default=func.now()
      )
      
      __table_args__ = (
          Index(
              "ix_order_autoclose_queue__pending",
              "autoclose_at",
              postgresql_where=text("processed_at IS NULL")
          ),
      )
  ```

### 1.3. Запустить миграцию
- [ ] Выполнить:
  ```bash
  cd field-service
  alembic upgrade head
  ```
- [ ] Проверить:
  ```sql
  \dt order_autoclose_queue
  \d order_autoclose_queue
  ```

---

## 🔧 ШАГ 2: АВТОЗАКРЫТИЕ ЗАКАЗОВ (20 мин)

### 2.1. Файл уже создан
- [ ] Убедиться что существует:
  ```bash
  ls -la field_service/services/autoclose_scheduler.py
  ```

### 2.2. Интегрировать в админ-бота
- [ ] Открыть `field_service/bots/admin_bot/main.py`
- [ ] Добавить импорт:
  ```python
  from field_service.services.autoclose_scheduler import autoclose_scheduler
  ```
- [ ] В функции `main()` после других `asyncio.create_task()` добавить:
  ```python
  # Автозакрытие заказов через 24ч
  asyncio.create_task(
      autoclose_scheduler(
          interval_seconds=3600,  # Проверка каждый час
      ),
      name="autoclose_scheduler"
  )
  ```

### 2.3. Добавить в обработчик закрытия заказа
- [ ] Открыть `field_service/bots/master_bot/handlers/orders.py`
- [ ] Найти функцию `active_close_act`
- [ ] После строки `order.status = m.OrderStatus.CLOSED` добавить:
  ```python
  # Автозакрытие через 24ч
  from field_service.services.autoclose_scheduler import enqueue_order_for_autoclose
  await enqueue_order_for_autoclose(
      session,
      order_id=order.id,
      closed_at=datetime.now(timezone.utc)
  )
  ```

### 2.4. Тестирование
- [ ] Запустить бота
- [ ] Закрыть тестовый заказ
- [ ] Проверить в БД:
  ```sql
  SELECT * FROM order_autoclose_queue;
  ```

---

## 🔔 ШАГ 3: PUSH-УВЕДОМЛЕНИЯ (30 мин)

### 3.1. Файл уже создан
- [ ] Убедиться что существует:
  ```bash
  ls -la field_service/services/push_notifications.py
  ```

### 3.2. Обновить модерацию мастеров
- [ ] Открыть `field_service/bots/admin_bot/routers/admin_masters.py`
- [ ] Найти функцию `approve_master`
- [ ] Заменить старый код уведомления на:
  ```python
  from field_service.services.push_notifications import notify_master, NotificationEvent
  from field_service.db.session import SessionLocal
  
  async with SessionLocal() as notif_session:
      await notify_master(
          notif_session,
          master_id=master_id,
          event=NotificationEvent.MODERATION_APPROVED,
      )
      await notif_session.commit()
  ```
- [ ] Аналогично для `reject_master`, `block_master`, `unblock_master`

### 3.3. Обновить watchdog комиссий
- [ ] Открыть `field_service/services/watchdogs.py`
- [ ] В `_notify_master_blocked` заменить на:
  ```python
  from field_service.services.push_notifications import notify_master, NotificationEvent
  
  async with SessionLocal() as session:
      await notify_master(
          session,
          master_id=event.master_id,
          event=NotificationEvent.ACCOUNT_BLOCKED,
          reason="Просрочка оплаты комиссии",
      )
      await session.commit()
  ```

### 3.4. Добавить монитор нераспределённых
- [ ] Создать файл `field_service/services/unassigned_monitor.py`:
  ```python
  from datetime import datetime, timedelta, timezone
  import asyncio
  from sqlalchemy import and_, func, select
  from field_service.db import models as m
  from field_service.db.session import SessionLocal
  from field_service.services.push_notifications import notify_logist, NotificationEvent
  
  async def monitor_unassigned_orders(bot, alerts_chat_id: int, *, interval_seconds: int = 600):
      while True:
          try:
              threshold = datetime.now(timezone.utc) - timedelta(minutes=10)
              async with SessionLocal() as session:
                  count = await session.scalar(
                      select(func.count()).select_from(m.orders).where(
                          and_(
                              m.orders.status == m.OrderStatus.SEARCHING,
                              m.orders.created_at < threshold,
                          )
                      )
                  )
                  if count and count > 0:
                      await notify_logist(bot, alerts_chat_id, event=NotificationEvent.UNASSIGNED_ORDERS, count=count)
          except Exception as exc:
              import logging
              logging.exception("Unassigned monitor error: %s", exc)
          await asyncio.sleep(interval_seconds)
  ```

- [ ] В `field_service/bots/admin_bot/main.py` добавить:
  ```python
  from field_service.services.unassigned_monitor import monitor_unassigned_orders
  from field_service.config import settings as env_settings
  
  # В main():
  if env_settings.alerts_chat_id:
      asyncio.create_task(
          monitor_unassigned_orders(bot, env_settings.alerts_chat_id),
          name="unassigned_monitor"
      )
  ```

---

## 🎁 ШАГ 4: РЕФЕРАЛКА ADMIN UI (15 мин)

### 4.1. Добавить метод статистики
- [ ] Открыть `field_service/bots/admin_bot/services_db.py`
- [ ] В класс `DBMastersService` добавить метод:
  ```python
  async def get_master_referral_stats(self, master_id: int) -> dict:
      """Получить статистику по рефералам мастера."""
      async with self._session_factory() as session:
          # Приглашённые мастера
          invited_total = int((await session.execute(
              select(func.count()).where(m.masters.referred_by_master_id == master_id)
          )).scalar_one() or 0)
          
          # Ожидающие модерации
          invited_pending = int((await session.execute(
              select(func.count()).where(
                  m.masters.referred_by_master_id == master_id,
                  m.masters.verified == False,
              )
          )).scalar_one() or 0)
          
          # Общая сумма начислений
          result = (await session.execute(
              select(func.count(), func.sum(m.referral_rewards.amount)).where(
                  m.referral_rewards.referrer_id == master_id,
                  m.referral_rewards.status != m.ReferralRewardStatus.CANCELED,
              )
          )).first()
          
          return {
              'invited_total': invited_total,
              'invited_pending': invited_pending,
              'rewards_count': int(result[0] or 0),
              'rewards_amount': Decimal(result[1] or 0),
          }
  ```

### 4.2. Обновить карточку мастера
- [ ] Открыть `field_service/bots/admin_bot/routers/admin_masters.py`
- [ ] Найти функцию `render_master_card`
- [ ] После блока с документами добавить:
  ```python
  # Реферальная информация
  if detail.referral_code:
      lines.append(f"🎁 Реф. код: {detail.referral_code}")
      try:
          ref_stats = await service.get_master_referral_stats(master_id)
          if ref_stats['invited_total'] > 0:
              lines.append(
                  f"👥 Рефералов: {ref_stats['invited_total']} "
                  f"(ожидают: {ref_stats['invited_pending']})"
              )
              lines.append(
                  f"💰 Начислено: {ref_stats['rewards_amount']:.2f} ₽ "
                  f"({ref_stats['rewards_count']} шт.)"
              )
      except Exception:
          logger.debug("Failed to load referral stats", exc_info=True)
  ```

---

## ⏰ ШАГ 5: НАСТРОЙКА СЛОТОВ (ОПЦИОНАЛЬНО) (20 мин)

**Выберите один из вариантов:**

### Вариант A: Через БД (рекомендуется)

- [ ] Выполнить SQL:
  ```sql
  INSERT INTO settings (key, value, value_type, description) VALUES
      ('timeslot_buckets', '[
          {"key": "10-13", "start": "10:00", "end": "13:00"},
          {"key": "13-16", "start": "13:00", "end": "16:00"},
          {"key": "16-19", "start": "16:00", "end": "19:00"}
      ]', 'JSON', 'Временные слоты для заказов');
  ```

- [ ] Обновить `field_service/services/time_service.py` (см. PATCH_P1_03)

### Вариант B: Через .env (быстрый)

- [ ] Добавить в `.env`:
  ```
  TIMESLOT_BUCKETS=10-13,13-16,16-19
  ```

- [ ] Обновить `config.py` для парсинга

---

## ✅ ШАГ 6: ТЕСТИРОВАНИЕ (30 мин)

### 6.1. Запустить боты
- [ ] Запустить админ-бот:
  ```bash
  python -m field_service.bots.admin_bot.main
  ```
- [ ] Запустить мастер-бот:
  ```bash
  python -m field_service.bots.master_bot.main
  ```
- [ ] Проверить логи на ошибки

### 6.2. Тестовые сценарии

**Автозакрытие:**
- [ ] Закрыть тестовый заказ
- [ ] Проверить запись в `order_autoclose_queue`
- [ ] Изменить `autoclose_at` на прошлое время
- [ ] Дождаться срабатывания планировщика (или перезапустить)
- [ ] Проверить логи: "order#X auto-closed after 24h"

**Рефералка:**
- [ ] Открыть мастер-бот → Реферальная программа
- [ ] Проверить отображение кода
- [ ] Проверить статистику
- [ ] Открыть админ-бот → карточку мастера
- [ ] Проверить отображение реферальной информации

**Уведомления:**
- [ ] Одобрить анкету мастера
- [ ] Проверить что мастер получил уведомление
- [ ] Заблокировать мастера
- [ ] Проверить уведомление в alerts канале
- [ ] Создать заказ и оставить нераспределённым >10 мин
- [ ] Проверить алерт логистам

---

## 📝 ШАГ 7: КОММИТ И ДЕПЛОЙ (10 мин)

- [ ] Добавить изменения в git:
  ```bash
  git add .
  git commit -m "feat: P1 sprint - autoclose, notifications, referral v2"
  ```

- [ ] Создать PR или замержить в main:
  ```bash
  git checkout main
  git merge feature/p1-sprint
  ```

- [ ] Задеплоить на сервер:
  ```bash
  git pull
  alembic upgrade head
  supervisorctl restart admin_bot master_bot
  ```

- [ ] Проверить что боты запустились:
  ```bash
  supervisorctl status
  tail -f /var/log/admin_bot.log
  ```

---

## 🎯 КРИТЕРИИ УСПЕХА

- [ ] Миграция применена без ошибок
- [ ] Оба бота запускаются без ошибок
- [ ] Автозакрытие: запись в очереди создаётся при закрытии заказа
- [ ] Рефералка: статистика отображается корректно
- [ ] Уведомления: мастера получают алерты при модерации
- [ ] Мониторы: планировщики работают в фоне

---

## 🚨 ROLLBACK PLAN

Если что-то пошло не так:

1. **Откатить миграцию:**
   ```bash
   alembic downgrade -1
   ```

2. **Откатить git:**
   ```bash
   git checkout main
   git reset --hard origin/main
   ```

3. **Восстановить БД:**
   ```bash
   psql -U postgres field_service < backup_YYYYMMDD_HHMMSS.sql
   ```

4. **Перезапустить старую версию:**
   ```bash
   supervisorctl restart admin_bot master_bot
   ```

---

## 📞 ПОДДЕРЖКА

Если возникли проблемы:
- Проверить логи: `tail -f /var/log/*.log`
- Проверить БД: `psql -U postgres field_service`
- Откатиться по плану выше
- Создать issue с описанием ошибки

---

**Время выполнения:** ~2 часа  
**Сложность:** Средняя  
**Версия:** 1.0
