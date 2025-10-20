# ⚡ БЫСТРЫЙ СТАРТ - Field Service на Windows Server

## 📋 Что нужно установить на чистом сервере

1. **Docker Desktop for Windows**
   - Скачать: https://www.docker.com/products/docker-desktop
   - Установить → Перезагрузить → Запустить Docker Desktop

Всё! Больше ничего не нужно (Python, Git - не требуются).

---

## 🚀 Шаг 1: На локальной машине (где проект)

```powershell
cd C:\ProjectF\docker-export
.\1_export_all.ps1
```

Результат: Папка `docker-export` готова (примерно 800 MB).

---

## 📦 Шаг 2: Копирование на сервер

Скопируйте **всю папку** `docker-export` на сервер любым способом:
- RDP (копировать-вставить)
- USB-накопитель
- OneDrive/Google Drive
- FileZilla/WinSCP

---

## ⚙️ Шаг 3: На сервере

### 3.1 Настройка

```powershell
cd C:\путь\к\docker-export

# Скопировать шаблон
Copy-Item .env.example .env

# Открыть в блокноте
notepad .env
```

**Обязательно заполните:**
- `MASTER_BOT_TOKEN` - токен мастер-бота
- `ADMIN_BOT_TOKEN` - токен админ-бота
- `GLOBAL_ADMINS_TG_IDS` - ваш Telegram ID в формате [123456789]
- `POSTGRES_PASSWORD` - придумайте пароль

Сохраните файл.

### 3.2 Развёртывание

```powershell
# Запустить PowerShell от имени администратора!
.\2_import_and_deploy.ps1
```

Скрипт выполнится за 5-10 минут.

---

## ✅ Проверка

```powershell
# Статус контейнеров
docker-compose ps

# Все должны быть Up:
#   fs_postgres     Up
#   fs_admin_bot    Up  
#   fs_master_bot   Up

# Просмотр логов
docker-compose logs -f
```

**В Telegram:**
- Напишите `/start` админ-боту → должен ответить
- Напишите `/start` мастер-боту → должен ответить

---

## 🔧 Основные команды

```powershell
# Остановить
docker-compose stop

# Запустить
docker-compose start

# Перезапустить
docker-compose restart

# Логи
docker-compose logs -f

# Бэкап БД
docker-compose exec postgres pg_dump -U fs_user field_service > backup.sql
```

---

## 🚨 Если что-то пошло не так

1. **Посмотрите логи:**
   ```powershell
   docker-compose logs admin-bot
   docker-compose logs master-bot
   ```

2. **Типичные проблемы:**
   - Неверный токен → проверьте `.env`
   - Неверный формат ID → должен быть `[123456]` с квадратными скобками
   - Docker не запущен → откройте Docker Desktop

3. **Полный рестарт:**
   ```powershell
   docker-compose down
   .\2_import_and_deploy.ps1
   ```

---

## 📖 Полная документация

Подробное руководство: `README.md`

---

**Время развёртывания:** 15-20 минут  
**Требования к серверу:** Windows Server/10/11 + 4 GB RAM + 20 GB диск
