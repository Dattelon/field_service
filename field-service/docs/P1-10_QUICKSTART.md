# P1-10: Push-уведомления офферов - QUICKSTART

**Статус:** ✅ Применено  
**Дата:** 2025-10-08

## 🎯 Что сделано

Реализованы push-уведомления мастерам при создании оффера через систему `notifications_outbox`.

### Изменённые файлы

1. **field_service/services/distribution_scheduler.py**
   - Добавлен импорт `notify_master`
   - Добавлена функция `_get_order_notification_data()`
   - Добавлен вызов `notify_master()` после создания оффера

2. **tests/test_p1_10_push_offer_notification.py** (новый)
   - Тест создания уведомления при распределении
   - Тест формата данных уведомления
   - Тест заказа без района

## 🚀 Применение изменений

### 1. Применить патч (УЖЕ ПРИМЕНЁН)

```powershell
# Изменения уже применены в:
C:\ProjectF\field-service\field_service\services\distribution_scheduler.py
```

### 2. Запустить тесты

```powershell
cd C:\ProjectF\field-service
$env:PYTHONIOENCODING='utf-8'
pytest tests/test_p1_10_push_offer_notification.py -v -s
```

### 3. Обновить code_snapshot

```powershell
cd C:\ProjectF
python export_code_snapshot.py
```

## 🧪 Ручное тестирование

### Сценарий 1: Новый заказ

1. Открыть админ-бот
2. Создать новый заказ в районе где есть мастер
3. Дождаться автораспределения (~15 секунд)
4. Проверить что мастер получил уведомление

### Сценарий 2: Проверка в БД

```sql
-- Проверить что оффер создан
SELECT * FROM offers 
WHERE order_id = <order_id> 
ORDER BY sent_at DESC 
LIMIT 1;

-- Проверить что уведомление в очереди
SELECT * FROM notifications_outbox 
WHERE master_id = <master_id> 
  AND event = 'new_offer'
ORDER BY created_at DESC 
LIMIT 1;

-- Проверить что уведомление отправлено
SELECT * FROM notifications_outbox 
WHERE master_id = <master_id> 
  AND event = 'new_offer'
  AND sent_at IS NOT NULL
ORDER BY sent_at DESC 
LIMIT 1;
```

## 📋 Формат уведомления

```
🆕 Новый заказ #123

📍 Москва, Центральный
⏰ 14:00-16:00
🛠 ⚡ Электрика

Откройте бот для принятия заказа.
```

## ⚙️ Как это работает

1. **Auto-distribution** находит подходящего мастера
2. Создаёт оффер через `_send_offer()`
3. При успехе вызывает `notify_master()` с данными заказа
4. Запись добавляется в `notifications_outbox`
5. **Воркер `notifications_watcher`** читает очередь каждые 5 секунд
6. Отправляет сообщение в Telegram
7. Помечает запись как `sent_at = NOW()`

## 🔍 Отладка

### Проверить логи распределения

```powershell
# В логах Docker контейнера должно быть:
docker logs field-service-scheduler -f | grep "Push notification queued"

# Пример:
# [dist] Push notification queued for master#5 about order#123
```

### Проверить логи уведомлений

```powershell
docker logs field-service-notifications -f

# Должно быть:
# [notifications] Processing 1 pending notifications
# [notifications] Sent new_offer to master#5 for order#123
```

### Если уведомления не отправляются

1. Проверить что воркер `notifications_watcher` запущен:
   ```sql
   -- В таблице должны накапливаться записи
   SELECT COUNT(*) FROM notifications_outbox WHERE sent_at IS NULL;
   ```

2. Проверить что мастер имеет `telegram_user_id`:
   ```sql
   SELECT id, telegram_user_id FROM masters WHERE id = <master_id>;
   ```

3. Проверить ошибки в логах:
   ```powershell
   docker logs field-service-notifications | grep ERROR
   ```

## 📊 Метрики успеха

После развёртывания отслеживать:

- **Скорость принятия офферов** - уменьшилась ли с ~5 мин до ~1 мин?
- **% принятых офферов** - вырос ли процент принятых офферов?
- **% expired офферов** - уменьшился ли процент просроченных?

## ✅ Чеклист развёртывания

- [x] Патч применён в `distribution_scheduler.py`
- [x] Тесты написаны
- [ ] Тесты прошли
- [ ] Code snapshot обновлён
- [ ] Развёрнуто на dev
- [ ] Ручное тестирование на dev
- [ ] Развёрнуто на prod
- [ ] Мониторинг метрик

## 🐛 Известные ограничения

1. **Timezone** - сейчас hardcoded Moscow time, нужно брать из города
2. **Воркер** - если `notifications_watcher` не запущен, уведомления не отправятся
3. **Telegram** - если у мастера нет `telegram_user_id`, уведомление не отправится

## 🔄 Откат изменений

Если нужно откатить изменения:

```bash
cd C:\ProjectF\field-service
git diff field_service/services/distribution_scheduler.py
git checkout field_service/services/distribution_scheduler.py
```

---

**Готово к развёртыванию!** 🚀
