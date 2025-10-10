# ✅ Field Service - Чеклист развёртывания

## Перед началом
- [ ] Есть доступ к серверу: `ssh root@217.199.254.27`
- [ ] Пароль: `owo?8x-YA@vRN*`
- [ ] Токены ботов готовы (BotFather)
- [ ] ID администраторов известны

## Развёртывание

### Вариант 1: Автоматический (РЕКОМЕНДУЕТСЯ)
```powershell
cd C:\ProjectF
.\deploy.ps1
```

### Вариант 2: Ручной
- [ ] Подключиться к серверу
- [ ] Загрузить setup_server.sh
- [ ] Выполнить: `bash setup_server.sh`
- [ ] Загрузить файлы проекта в /opt/field-service
- [ ] Настроить .env
- [ ] Запустить: `docker compose up -d`

## После развёртывания

### 1. Проверка контейнеров
```bash
docker compose ps
```
Должны быть запущены:
- [ ] postgres (healthy)
- [ ] admin-bot (running)
- [ ] master-bot (running)

### 2. Проверка логов
```bash
docker compose logs admin-bot | tail -20
docker compose logs master-bot | tail -20
```
- [ ] Нет ошибок при старте
- [ ] Боты успешно подключились к БД
- [ ] Боты успешно подключились к Telegram API

### 3. Проверка БД
```bash
docker compose exec postgres psql -U fs_user -d field_service -c "\dt"
```
- [ ] Все таблицы созданы
- [ ] Миграции применены

### 4. Тест ботов в Telegram

**Admin Bot (@your_admin_bot):**
- [ ] Отправить `/start` - получен ответ
- [ ] Команда `/queue` - показывает очередь
- [ ] Доступ для суперюзера проверен

**Master Bot (@your_master_bot):**
- [ ] Отправить `/start` - получен ответ онбординга
- [ ] Можно пройти регистрацию
- [ ] FSM работает корректно

### 5. Heartbeat
```bash
# Подождать 60 секунд
docker compose logs admin-bot | grep "alive"
docker compose logs master-bot | grep "alive"
```
- [ ] Admin-bot отправляет heartbeat
- [ ] Master-bot отправляет heartbeat

### 6. Мониторинг

**Система:**
```bash
htop
df -h
free -h
```
- [ ] CPU < 50%
- [ ] RAM < 80%
- [ ] Диск > 10GB свободно

**Docker:**
```bash
docker stats --no-stream
```
- [ ] Контейнеры используют разумное количество ресурсов

### 7. Безопасность
- [ ] Firewall включен: `ufw status`
- [ ] Открыты только необходимые порты (22)
- [ ] Сменён пароль root (опционально)
- [ ] Созданы резервные копии

### 8. Резервное копирование
```bash
# Тестовый бэкап
docker compose exec postgres pg_dump -U fs_user field_service > /tmp/test_backup.sql
ls -lh /tmp/test_backup.sql
```
- [ ] Бэкап создаётся успешно
- [ ] Настроен cron для автобэкапов (опционально)

## Финальная проверка

### Создание тестового заказа
