# 🚀 Field Service - Инструкция по развёртыванию на сервере

## 📋 Информация о сервере
- **IP**: 217.199.254.27
- **IPv6**: 2a03:6f00:a::1:d62
- **SSH**: ssh root@217.199.254.27
- **Пароль**: `owo?8x-YA@vRN*`
- **ОС**: Ubuntu 24.04
- **Ресурсы**: 4×3.3 ГГц CPU, 8 ГБ RAM, 80 ГБ NVMe

## 🎯 Порядок развёртывания

### Вариант А: Автоматическое развёртывание (РЕКОМЕНДУЕТСЯ)

#### Шаг 1: Установка OpenSSH Client (если нет)

1. Откройте PowerShell **от имени администратора**
2. Проверьте наличие SSH:
   ```powershell
   ssh -V
   ```

3. Если SSH нет, установите:
   ```powershell
   # Через Settings (GUI)
   # Settings > Apps > Optional Features > Add a feature > OpenSSH Client
   
   # ИЛИ через PowerShell
   Add-WindowsCapability -Online -Name OpenSSH.Client~~~~0.0.1.0
   ```

#### Шаг 2: Запуск автоматического развёртывания

1. Откройте PowerShell
2. Перейдите в директорию проекта:
   ```powershell
   cd C:\ProjectF
   ```

3. Запустите скрипт развёртывания:
   ```powershell
   .\deploy.ps1
   ```

4. Вводите пароль при запросе: `owo?8x-YA@vRN*`

**Скрипт автоматически:**
- Загрузит setup_server.sh на сервер
- Установит Docker и все зависимости
- Настроит PostgreSQL
- Загрузит файлы проекта
- Настроит firewall

#### Шаг 3: Настройка переменных окружения

1. Подключитесь к серверу:
   ```bash
   ssh root@217.199.254.27
   ```

2. Перейдите в директорию проекта:
   ```bash
   cd /opt/field-service
   ```

3. Отредактируйте .env файл:
   ```bash
   nano .env
   ```

4. **ОБЯЗАТЕЛЬНО обновите:**
   ```bash
   # Bot Tokens
   MASTER_BOT_TOKEN=ваш_токен_мастер_бота
   ADMIN_BOT_TOKEN=ваш_токен_админ_бота
   
   # Channels (необязательно, но рекомендуется)
   LOGS_CHANNEL_ID=-1001234567890
   ALERTS_CHANNEL_ID=-1001234567891
   REPORTS_CHANNEL_ID=-1001234567892
   
   # Admin superusers (через запятую)
   ADMIN_BOT_SUPERUSERS=123456789,987654321
   GLOBAL_ADMINS_TG_IDS=[123456789,987654321]
   ```

5. Сохраните: `Ctrl+O`, `Enter`, `Ctrl+X`

#### Шаг 4: Сборка и запуск

```bash
# Сборка Docker образов
docker compose build

# Применение миграций БД
docker compose run --rm admin-bot alembic upgrade head

# Запуск всех сервисов
docker compose up -d

# Проверка статуса
docker compose ps

# Просмотр логов
docker compose logs -f
```

✅ **Поздравляем! Боты запущены!**

---

### Вариант Б: Ручное развёртывание

#### 1. Подключение к серверу

```bash
ssh root@217.199.254.27
# Пароль: owo?8x-YA@vRN*
```

#### 2. Обновление системы

```bash
apt-get update
apt-get upgrade -y
```

#### 3. Установка Docker

```bash
# Установка зависимостей
apt-get install -y ca-certificates curl gnupg lsb-release

# Добавление GPG ключа Docker
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg

# Добавление репозитория
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null

# Установка Docker
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Запуск Docker
systemctl start docker
systemctl enable docker

# Проверка
docker --version
docker compose version
```

#### 4. Загрузка проекта на сервер

**С локальной машины (Windows PowerShell):**

```powershell
# Используйте SCP
scp -r C:\ProjectF\field-service root@217.199.254.27:/opt/

# ИЛИ используйте WinSCP / FileZilla
```

**На сервере:**

```bash
# Проверка загрузки
ls -la /opt/field-service
```

#### 5. Настройка конфигурации

```bash
cd /opt/field-service

# Создание .env из примера (если нет)
cat > .env << 'EOF'
DATABASE_URL=postgresql+asyncpg://fs_user:fs_password@postgres:5432/field_service
MASTER_BOT_TOKEN=8423680284:AAHXBq-Lmtn5cVwUoxMwhJPOAoCMVGz4688
ADMIN_BOT_TOKEN=7531617746:AAGvHQ0RySGtSSMAYenNdwyenZFkTZA6xbQ
TIMEZONE=Europe/Moscow
DISTRIBUTION_SLA_SECONDS=120
DISTRIBUTION_ROUNDS=2
HEARTBEAT_SECONDS=60
COMMISSION_DEADLINE_HOURS=3
GUARANTEE_COMPANY_PAYMENT=2500
WORKDAY_START=10:00
WORKDAY_END=20:00
ASAP_LATE_THRESHOLD=19:30
ADMIN_BOT_SUPERUSERS=
GLOBAL_ADMINS_TG_IDS=[]
ACCESS_CODE_TTL_HOURS=24
OVERDUE_WATCHDOG_MIN=10
EOF

# Редактирование .env
nano .env
```

#### 6. Запуск PostgreSQL

```bash
# Создание docker-compose.yml уже должно быть в проекте
# Запуск только PostgreSQL
docker compose up -d postgres

# Проверка
docker compose ps
docker compose logs postgres
```

#### 7. Применение миграций

```bash
# Запуск миграций Alembic
docker compose run --rm admin-bot alembic upgrade head
```

#### 8. Запуск ботов

```bash
# Сборка образов
docker compose build

# Запуск всех сервисов
docker compose up -d

# Проверка статуса
docker compose ps
```

---

## 📊 Мониторинг и управление

### Просмотр логов

```bash
# Все логи
docker compose logs -f

# Только admin-bot
docker compose logs -f admin-bot

# Только master-bot
docker compose logs -f master-bot

# Только PostgreSQL
docker compose logs -f postgres

# Последние 100 строк
docker compose logs --tail=100
```

### Проверка статуса

```bash
# Статус контейнеров
docker compose ps

# Использование ресурсов
docker stats

# Подключение к БД
docker compose exec postgres psql -U fs_user -d field_service
```

### Управление сервисами

```bash
# Остановка всех сервисов
docker compose down

# Остановка с удалением volumes (ВНИМАНИЕ: удалит БД!)
docker compose down -v

# Перезапуск всех сервисов
docker compose restart

# Перезапуск конкретного сервиса
docker compose restart admin-bot
docker compose restart master-bot

# Пересборка после изменения кода
docker compose build
docker compose up -d
```

### Резервное копирование БД

```bash
# Создание бэкапа
docker compose exec postgres pg_dump -U fs_user field_service > backup_$(date +%Y%m%d_%H%M%S).sql

# Восстановление из бэкапа
docker compose exec -T postgres psql -U fs_user field_service < backup_20250101_120000.sql

# Автоматический бэкап (cron)
# Добавить в crontab -e:
# 0 2 * * * cd /opt/field-service && docker compose exec -T postgres pg_dump -U fs_user field_service > /opt/backups/db_$(date +\%Y\%m\%d_\%H\%M\%S).sql
```

---

## 🔧 Troubleshooting

### Проблема: Контейнер постоянно перезапускается

```bash
# Проверить логи
docker compose logs admin-bot --tail=100

# Возможные причины:
# 1. Неверный токен бота - проверьте .env
# 2. Проблема с БД - проверьте postgres logs
# 3. Ошибка в коде - проверьте последние изменения

# Запуск в интерактивном режиме для отладки
docker compose run --rm admin-bot bash
```

### Проблема: PostgreSQL не запускается

```bash
# Проверить логи
docker compose logs postgres

# Проверить порт
netstat -tulpn | grep 5432

# Проверить volumes
docker volume ls
docker volume inspect field-service_fs_pgdata

# Пересоздать volume (ВНИМАНИЕ: удалит данные!)
docker compose down -v
docker compose up -d postgres
```

### Проблема: Боты не отвечают

```bash
# 1. Проверить статус
docker compose ps

# 2. Проверить логи на ошибки
docker compose logs admin-bot | grep -i error
docker compose logs master-bot | grep -i error

# 3. Проверить токены ботов
grep BOT_TOKEN /opt/field-service/.env

# 4. Проверить подключение к Telegram API
docker compose exec admin-bot ping api.telegram.org

# 5. Перезапустить боты
docker compose restart admin-bot master-bot
```

### Проблема: Медленная работа

```bash
# Проверить использование ресурсов
docker stats

# Проверить место на диске
df -h

# Проверить память
free -h

# Очистка неиспользуемых образов
docker system prune -a

# Проверка индексов БД
docker compose exec postgres psql -U fs_user -d field_service -c "\di+"
```

---

## 🔄 Обновление проекта

### Обновление кода

```bash
# 1. Остановить боты (оставить БД)
docker compose stop admin-bot master-bot

# 2. Загрузить новые файлы с локальной машины
# На Windows:
scp -r C:\ProjectF\field-service root@217.199.254.27:/opt/

# 3. Применить новые миграции (если есть)
docker compose run --rm admin-bot alembic upgrade head

# 4. Пересобрать образы
docker compose build

# 5. Запустить боты
docker compose up -d admin-bot master-bot
```

### Откат миграций (при необходимости)

```bash
# Откат на одну миграцию назад
docker compose run --rm admin-bot alembic downgrade -1

# Откат до конкретной ревизии
docker compose run --rm admin-bot alembic downgrade <revision_id>

# Просмотр истории миграций
docker compose run --rm admin-bot alembic history
```

---

## 🔒 Безопасность

### Базовые меры

```bash
# 1. Изменить пароль root
passwd

# 2. Создать отдельного пользователя (опционально)
adduser fieldservice
usermod -aG docker fieldservice

# 3. Настроить firewall (ufw)
ufw enable
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
ufw status

# 4. Отключить вход по паролю SSH (после настройки ключей)
# nano /etc/ssh/sshd_config
# PasswordAuthentication no
# systemctl restart sshd

# 5. Обновления безопасности
apt-get update
apt-get upgrade -y
apt-get autoremove -y
```

### Настройка SSL (для будущего веб-интерфейса)

```bash
# Установка Certbot
apt-get install -y certbot python3-certbot-nginx

# Получение сертификата
certbot certonly --standalone -d yourdomain.com

# Автообновление сертификата
certbot renew --dry-run
```

---

## 📝 Полезные команды

### Работа с Docker

```bash
# Список образов
docker images

# Список контейнеров
docker ps -a

# Удаление остановленных контейнеров
docker container prune

# Удаление неиспользуемых образов
docker image prune -a

# Очистка всего (volumes, images, networks)
docker system prune -a --volumes

# Просмотр логов конкретного контейнера
docker logs -f <container_id>

# Выполнение команды в контейнере
docker compose exec admin-bot python -c "print('test')"

# Вход в контейнер
docker compose exec admin-bot bash
```

### Работа с PostgreSQL

```bash
# Подключение к БД
docker compose exec postgres psql -U fs_user -d field_service

# Список таблиц
\dt

# Описание таблицы
\d orders

# Список индексов
\di

# Размер БД
SELECT pg_size_pretty(pg_database_size('field_service'));

# Размер таблиц
SELECT schemaname, tablename, pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) 
FROM pg_tables WHERE schemaname = 'public' ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;

# Активные соединения
SELECT * FROM pg_stat_activity WHERE datname = 'field_service';

# SQL запросы напрямую
docker compose exec postgres psql -U fs_user -d field_service -c "SELECT COUNT(*) FROM orders;"
```

### Мониторинг системы

```bash
# CPU, память, диск
htop
free -h
df -h

# Логи системы
journalctl -u docker -f

# Использование портов
netstat -tulpn
ss -tulpn

# Процессы Docker
docker stats --no-stream

# Размер Docker volumes
docker system df -v
```

---

## 🎯 Контрольный список после развёртывания

- [ ] PostgreSQL запущен и работает
- [ ] Миграции БД применены успешно
- [ ] Admin-bot запущен и отвечает
- [ ] Master-bot запущен и отвечает
- [ ] .env настроен с правильными токенами
- [ ] Каналы для логов настроены (опционально)
- [ ] Superusers добавлены в .env
- [ ] Боты отправляют heartbeat в лог-канал
- [ ] Firewall настроен
- [ ] Настроено резервное копирование
- [ ] Проверены логи на ошибки
- [ ] Тестовый заказ проходит через систему

---

## 📞 Контакты и поддержка

- **Документация**: `/opt/field-service/docs/`
- **Логи**: `docker compose logs -f`
- **Алерты**: Telegram канал (настроить ALERTS_CHANNEL_ID)

---

## 🔗 Полезные ссылки

- Docker: https://docs.docker.com/
- PostgreSQL: https://www.postgresql.org/docs/
- Aiogram: https://docs.aiogram.dev/
- SQLAlchemy: https://docs.sqlalchemy.org/
- Alembic: https://alembic.sqlalchemy.org/

---

## 📌 Краткая справка команд

```bash
# === БЫСТРЫЙ СТАРТ ===
cd /opt/field-service
docker compose up -d
docker compose logs -f

# === ОСТАНОВКА ===
docker compose down

# === ПЕРЕЗАПУСК ===
docker compose restart

# === ЛОГИ ===
docker compose logs -f admin-bot
docker compose logs -f master-bot

# === СТАТУС ===
docker compose ps
docker stats

# === БД ===
docker compose exec postgres psql -U fs_user -d field_service

# === БЭКАП ===
docker compose exec postgres pg_dump -U fs_user field_service > backup.sql

# === МИГРАЦИИ ===
docker compose run --rm admin-bot alembic upgrade head
docker compose run --rm admin-bot alembic history

# === ОБНОВЛЕНИЕ ===
docker compose down
# (загрузить новые файлы)
docker compose build
docker compose up -d
```

---

## 🚀 Готово!

Ваш Field Service сервер настроен и готов к работе!

**Следующие шаги:**
1. Протестируйте работу обоих ботов
2. Настройте мониторинг и алерты
3. Настройте автоматическое резервное копирование
4. Добавьте администраторов в систему
5. Создайте первые тестовые заказы

**Важно:**
- Регулярно проверяйте логи: `docker compose logs -f`
- Настройте бэкапы БД (минимум раз в день)
- Следите за использованием диска: `df -h`
- Обновляйте систему: `apt-get update && apt-get upgrade`

**При возникновении проблем:**
1. Проверьте логи: `docker compose logs`
2. Проверьте статус контейнеров: `docker compose ps`
3. Проверьте .env файл
4. Перезапустите сервисы: `docker compose restart`

---

*Инструкция актуальна для версии v1.2*  
*Последнее обновление: Октябрь 2025*
