# 🚀 Field Service - Руководство по развёртыванию на Windows Server

## 📋 Содержание папки

```
docker-export/
├── images/                    # Docker-образы (создаются при экспорте)
│   ├── admin-bot.tar         # Образ админ-бота (~300-400 MB)
│   ├── master-bot.tar        # Образ мастер-бота (~300-400 MB)
│   └── postgres.tar          # Образ PostgreSQL (~80 MB)
├── init-db/                   # Данные базы (создаются при экспорте)
│   └── backup.sql            # Дамп БД с городами, районами, улицами
├── 1_export_all.ps1          # Скрипт экспорта (запускать на локальной машине)
├── 2_import_and_deploy.ps1   # Скрипт развёртывания (запускать на сервере)
├── docker-compose.yml        # Конфигурация Docker Compose
├── .env.example              # Шаблон конфигурации
└── README.md                 # Этот файл
```

---

## 🖥️ Требования к серверу

### Минимальные требования:
- **ОС**: Windows Server 2019/2022 или Windows 10/11 Pro
- **CPU**: 2 ядра (рекомендуется 4)
- **RAM**: 4 GB (рекомендуется 8 GB)
- **Диск**: 20 GB свободного места
- **Интернет**: Стабильное подключение

### Необходимое ПО:
1. **Docker Desktop for Windows** - обязательно
2. **PowerShell 5.1+** - уже есть в Windows
3. **Git for Windows** - опционально (для удобства)

---

## 📦 Часть 1: Подготовка на локальной машине

### Шаг 1: Экспорт контейнеров

На вашей **локальной машине** с проектом:

```powershell
# Перейдите в папку docker-export
cd C:\ProjectF\docker-export

# Запустите скрипт экспорта
.\1_export_all.ps1
```

**Что делает скрипт:**
- Останавливает запущенные контейнеры
- Собирает Docker-образы из исходников
- Экспортирует образы в .tar файлы
- Создаёт дамп базы данных
- Упаковывает всё в папку `docker-export`

**Результат:** Папка `docker-export` готова к копированию на сервер.

### Шаг 2: Копирование на сервер

Скопируйте **всю папку** `docker-export` на Windows Server любым способом:

- **RDP**: Копирование через буфер обмена
- **FileZilla/WinSCP**: FTP/SFTP
- **OneDrive/Google Drive**: Облачное хранилище
- **USB-накопитель**: Физический перенос

---

## ⚙️ Часть 2: Установка на Windows Server

### Шаг 1: Установка Docker Desktop

На **Windows Server**:

1. Скачайте Docker Desktop:
   ```
   https://www.docker.com/products/docker-desktop
   ```

2. Запустите установщик `Docker Desktop Installer.exe`

3. При установке выберите:
   - ✅ Use WSL 2 instead of Hyper-V (рекомендуется)
   - ✅ Add shortcut to desktop

4. **ПЕРЕЗАГРУЗИТЕ СЕРВЕР** после установки

5. Запустите Docker Desktop

6. Дождитесь запуска Docker Engine (иконка в трее станет зелёной)

### Проверка установки:

```powershell
# Откройте PowerShell от имени администратора
docker --version
# Должно вывести: Docker version 24.x.x

docker ps
# Должно вывести пустой список контейнеров
```

### Шаг 2: Настройка конфигурации

1. Перейдите в папку, куда скопировали `docker-export`:
   ```powershell
   cd C:\путь\к\docker-export
   ```

2. Скопируйте шаблон конфигурации:
   ```powershell
   Copy-Item .env.example .env
   ```

3. Откройте `.env` в текстовом редакторе:
   ```powershell
   notepad .env
   ```

4. Заполните **обязательные** параметры:

   ```env
   # Токены ботов (получите у @BotFather)
   MASTER_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
   ADMIN_BOT_TOKEN=0987654321:ZYXwvuTSRqponMLKjihGFEdcba
   
   # Ваш Telegram ID (узнайте у @userinfobot)
   ADMIN_BOT_SUPERUSERS=123456789
   GLOBAL_ADMINS_TG_IDS=[123456789]
   
   # Пароль БД (придумайте сложный)
   POSTGRES_PASSWORD=СложныйПароль123!
   DATABASE_URL=postgresql+asyncpg://fs_user:СложныйПароль123!@postgres:5432/field_service
   ```

5. **Опционально** настройте каналы для логов:
   - Создайте приватные каналы в Telegram
   - Добавьте ботов как администраторов
   - Узнайте ID каналов через @getidsbot
   - Вставьте ID в `.env`

6. Сохраните и закройте файл


### Шаг 3: Развёртывание системы

```powershell
# Убедитесь что находитесь в папке docker-export
cd C:\путь\к\docker-export

# Запустите скрипт развёртывания от имени администратора
.\2_import_and_deploy.ps1
```

**Что делает скрипт:**
1. Проверяет Docker и права администратора
2. Проверяет наличие всех файлов
3. Загружает Docker-образы (3-5 минут)
4. Проверяет конфигурацию `.env`
5. Запускает PostgreSQL
6. Восстанавливает базу данных из дампа
7. Запускает админ-бота и мастер-бота
8. Показывает статус контейнеров

**Ожидаемый результат:**

```
========================================
✓ РАЗВЁРТЫВАНИЕ ЗАВЕРШЕНО!
========================================

Контейнеры запущены:
  • postgres    - База данных
  • admin-bot   - Админ-бот
  • master-bot  - Мастер-бот
```

### Шаг 4: Проверка работы

1. **Проверьте статус контейнеров:**
   ```powershell
   docker-compose ps
   ```
   
   Все контейнеры должны быть в статусе `Up` (running).

2. **Проверьте логи:**
   ```powershell
   # Логи всех сервисов
   docker-compose logs -f
   
   # Логи только админ-бота
   docker-compose logs -f admin-bot
   
   # Логи только мастер-бота
   docker-compose logs -f master-bot
   ```

3. **Проверьте ботов в Telegram:**
   - Напишите `/start` админ-боту
   - Напишите `/start` мастер-боту
   - Боты должны ответить

---

## 🔧 Управление системой

### Основные команды

```powershell
# Просмотр статуса
docker-compose ps

# Просмотр логов (Ctrl+C для выхода)
docker-compose logs -f

# Остановка всех сервисов
docker-compose stop

# Запуск всех сервисов
docker-compose start

# Перезапуск всех сервисов
docker-compose restart

# Перезапуск одного сервиса
docker-compose restart admin-bot
docker-compose restart master-bot
docker-compose restart postgres

# Просмотр использования ресурсов
docker stats

# Полное удаление (БД будет удалена!)
docker-compose down -v
```

### Обновление конфигурации

Если нужно изменить `.env`:

```powershell
# 1. Отредактируйте .env
notepad .env

# 2. Перезапустите ботов
docker-compose restart admin-bot master-bot
```

### Резервное копирование БД

```powershell
# Создание бэкапа
docker-compose exec postgres pg_dump -U fs_user field_service > backup_$(Get-Date -Format 'yyyy-MM-dd_HH-mm').sql

# Восстановление из бэкапа
Get-Content backup_2025-10-17_10-30.sql | docker-compose exec -T postgres psql -U fs_user -d field_service
```

---

## 🚨 Решение проблем

### Проблема: Docker не запускается

**Симптомы:**
```
docker: command not found
или
error during connect: this error may indicate that the docker daemon is not running
```

**Решение:**
1. Откройте Docker Desktop
2. Дождитесь полного запуска (зелёная иконка в трее)
3. Повторите команды

### Проблема: Контейнер постоянно перезапускается

**Симптомы:**
```
docker-compose ps
NAME         STATUS
fs_admin_bot    Restarting
```

**Решение:**
```powershell
# Посмотрите логи для диагностики
docker-compose logs admin-bot

# Типичные причины:
# 1. Неверный токен бота → проверьте .env
# 2. Ошибка подключения к БД → проверьте DATABASE_URL
# 3. Неверный формат GLOBAL_ADMINS_TG_IDS → должен быть JSON-массив: [123456]
```

### Проблема: Бот не отвечает в Telegram

**Решение:**
1. Проверьте что контейнер запущен:
   ```powershell
   docker-compose ps
   ```

2. Проверьте логи на ошибки:
   ```powershell
   docker-compose logs -f admin-bot
   ```

3. Проверьте токен бота:
   - Токен должен быть активным
   - Бот не должен быть заблокирован

4. Проверьте интернет-соединение сервера

### Проблема: БД не восстанавливается

**Симптомы:**
```
ERROR: role "fs_user" does not exist
```

**Решение:**
```powershell
# Пересоздайте контейнеры
docker-compose down -v
docker-compose up -d postgres

# Дождитесь запуска БД
Start-Sleep -Seconds 30

# Восстановите дамп
Get-Content init-db\backup.sql | docker-compose exec -T postgres psql -U fs_user -d field_service
```

### Проблема: Не хватает памяти

**Симптомы:**
- Контейнеры медленно работают
- OOM (Out of Memory) в логах

**Решение:**
1. Увеличьте лимиты в Docker Desktop:
   - Settings → Resources → Memory → 4 GB минимум

2. Перезапустите Docker Desktop

---

## 📊 Мониторинг

### Просмотр использования ресурсов

```powershell
# Реал-тайм мониторинг
docker stats

# Один раз
docker stats --no-stream
```

### Проверка здоровья БД

```powershell
# Подключение к БД
docker-compose exec postgres psql -U fs_user -d field_service

# SQL-запросы:
# Количество мастеров
SELECT COUNT(*) FROM masters;

# Количество заказов
SELECT COUNT(*) FROM orders;

# Выход
\q
```

---

## 🔄 Автозапуск при перезагрузке

Docker Desktop по умолчанию запускается при старте Windows.
Контейнеры с `restart: unless-stopped` запустятся автоматически.

Если нужно отключить автозапуск Docker:
- Docker Desktop → Settings → General → 
  - ❌ Start Docker Desktop when you log in

---

## 📞 Поддержка

При возникновении проблем:

1. **Соберите информацию:**
   ```powershell
   # Версия Docker
   docker --version
   docker-compose --version
   
   # Статус контейнеров
   docker-compose ps
   
   # Логи (последние 100 строк)
   docker-compose logs --tail=100
   ```

2. **Проверьте документацию:**
   - Docker: https://docs.docker.com/
   - PostgreSQL: https://www.postgresql.org/docs/

3. **Сохраните логи:**
   ```powershell
   docker-compose logs > logs_$(Get-Date -Format 'yyyy-MM-dd_HH-mm').txt
   ```

---

## ✅ Чеклист успешного развёртывания

- [ ] Docker Desktop установлен и запущен
- [ ] Все файлы из `docker-export` скопированы на сервер
- [ ] Файл `.env` создан и настроен
- [ ] Скрипт `2_import_and_deploy.ps1` выполнен успешно
- [ ] Все контейнеры в статусе `Up` (running)
- [ ] Боты отвечают в Telegram
- [ ] БД содержит данные (города, районы, улицы)
- [ ] Логи не содержат критических ошибок

---

## 🎯 Следующие шаги

После успешного развёртывания:

1. **Настройте мониторинг**
   - Настройте Telegram-каналы для логов
   - Проверяйте логи регулярно

2. **Настройте резервное копирование**
   - Автоматические бэкапы БД
   - Хранение бэкапов вне сервера

3. **Документируйте**
   - Запишите все пароли в безопасное место
   - Сохраните конфигурацию `.env`

4. **Тестируйте**
   - Создайте тестового мастера
   - Создайте тестовую заявку
   - Проверьте работу комиссий

---

**Дата создания:** 2025-10-17
**Версия документа:** 1.0
