# 🔧 Инструкция для AI: Прямое подключение к серверу

## 📋 Данные сервера
- **IP**: 217.199.254.27
- **IPv6**: 2a03:6f00:a::1:d62
- **Пользователь**: root
- **Пароль**: owo?8x-YA@vRN*
- **ОС**: Ubuntu 24.04
- **Проект**: /opt/field-service

## 🔑 Установленные инструменты
- ✅ Posh-SSH (PowerShell модуль для SSH)
- ✅ OpenSSH Client (Windows)
- ✅ SSH ключ: C:\Users\v.simzikov\.ssh\id_ed25519 (с passphrase)

## 🚀 БЫСТРЫЙ СТАРТ - Подключение в 1 команду

### Вариант 1: Через Posh-SSH (РЕКОМЕНДУЕТСЯ)
```powershell
$pass = ConvertTo-SecureString "owo?8x-YA@vRN*" -AsPlainText -Force
$cred = New-Object System.Management.Automation.PSCredential("root", $pass)
$s = New-SSHSession -ComputerName 217.199.254.27 -Credential $cred -AcceptKey

# Выполнить команду
$result = Invoke-SSHCommand -SessionId $s.SessionId -Command "whoami && pwd"
Write-Host $result.Output

# Закрыть сессию
Remove-SSHSession -SessionId $s.SessionId
```

### Вариант 2: Проверка подключения
```powershell
$pass = ConvertTo-SecureString "owo?8x-YA@vRN*" -AsPlainText -Force
$cred = New-Object System.Management.Automation.PSCredential("root", $pass)
$s = New-SSHSession -ComputerName 217.199.254.27 -Credential $cred -AcceptKey

if ($s) {
    Write-Host "✓ Подключено! SessionId: $($s.SessionId)" -ForegroundColor Green
} else {
    Write-Host "✗ Ошибка подключения" -ForegroundColor Red
}
```

## 📦 Основные операции

### 1. Выполнение команд
```powershell
$pass = ConvertTo-SecureString "owo?8x-YA@vRN*" -AsPlainText -Force
$cred = New-Object System.Management.Automation.PSCredential("root", $pass)
$s = New-SSHSession -ComputerName 217.199.254.27 -Credential $cred -AcceptKey

# Простая команда
$r = Invoke-SSHCommand -SessionId $s.SessionId -Command "ls -la /opt/field-service"
Write-Host $r.Output

# Команда с таймаутом (в секундах)
$r = Invoke-SSHCommand -SessionId $s.SessionId -Command "docker compose build" -TimeOut 300
Write-Host $r.Output

# Проверка статуса выполнения
if ($r.ExitStatus -eq 0) {
    Write-Host "Команда выполнена успешно" -ForegroundColor Green
} else {
    Write-Host "Ошибка: код $($r.ExitStatus)" -ForegroundColor Red
}

Remove-SSHSession -SessionId $s.SessionId
```

### 2. Загрузка файлов (SFTP)
```powershell
$pass = ConvertTo-SecureString "owo?8x-YA@vRN*" -AsPlainText -Force
$cred = New-Object System.Management.Automation.PSCredential("root", $pass)

# Создать SFTP сессию
$sftp = New-SFTPSession -ComputerName 217.199.254.27 -Credential $cred -AcceptKey

# Загрузить файл
Set-SFTPItem -SessionId $sftp.SessionId -Path "C:\local\file.txt" -Destination "/remote/path/" -Force

# Загрузить директорию рекурсивно
Set-SFTPItem -SessionId $sftp.SessionId -Path "C:\local\folder" -Destination "/remote/path/" -Force

# Скачать файл
Get-SFTPItem -SessionId $sftp.SessionId -Path "/remote/file.txt" -Destination "C:\local\" -Force

# Закрыть сессию
Remove-SFTPSession -SessionId $sftp.SessionId
```

### 3. Множественные команды в одной сессии
```powershell
$pass = ConvertTo-SecureString "owo?8x-YA@vRN*" -AsPlainText -Force
$cred = New-Object System.Management.Automation.PSCredential("root", $pass)
$s = New-SSHSession -ComputerName 217.199.254.27 -Credential $cred -AcceptKey

# Команда 1
$r1 = Invoke-SSHCommand -SessionId $s.SessionId -Command "docker compose ps"
Write-Host $r1.Output

# Команда 2
$r2 = Invoke-SSHCommand -SessionId $s.SessionId -Command "docker compose logs --tail=10 admin-bot"
Write-Host $r2.Output

# Команда 3
$r3 = Invoke-SSHCommand -SessionId $s.SessionId -Command "df -h"
Write-Host $r3.Output

Remove-SSHSession -SessionId $s.SessionId
```

### 4. Создание файла на сервере
```powershell
$pass = ConvertTo-SecureString "owo?8x-YA@vRN*" -AsPlainText -Force
$cred = New-Object System.Management.Automation.PSCredential("root", $pass)
$s = New-SSHSession -ComputerName 217.199.254.27 -Credential $cred -AcceptKey

$fileContent = @"
DATABASE_URL=postgresql+asyncpg://fs_user:fs_password@postgres:5432/field_service
MASTER_BOT_TOKEN=token_here
ADMIN_BOT_TOKEN=token_here
"@

$cmd = @"
cat > /opt/field-service/.env << 'EOF'
$fileContent
EOF
"@

Invoke-SSHCommand -SessionId $s.SessionId -Command $cmd
Remove-SSHSession -SessionId $s.SessionId
```

## 🐳 Docker команды на сервере

### Проверка статуса контейнеров
```powershell
$cmd = "cd /opt/field-service && docker compose ps"
$result = Invoke-SSHCommand -SessionId $s.SessionId -Command $cmd
Write-Host $result.Output
```

### Просмотр логов
```powershell
# Все логи
$cmd = "cd /opt/field-service && docker compose logs --tail=50"
$result = Invoke-SSHCommand -SessionId $s.SessionId -Command $cmd

# Только admin-bot
$cmd = "cd /opt/field-service && docker compose logs admin-bot --tail=50"
$result = Invoke-SSHCommand -SessionId $s.SessionId -Command $cmd

# Только master-bot
$cmd = "cd /opt/field-service && docker compose logs master-bot --tail=50"
$result = Invoke-SSHCommand -SessionId $s.SessionId -Command $cmd
```

### Перезапуск сервисов
```powershell
# Перезапуск всех
$cmd = "cd /opt/field-service && docker compose restart"
Invoke-SSHCommand -SessionId $s.SessionId -Command $cmd

# Перезапуск конкретного сервиса
$cmd = "cd /opt/field-service && docker compose restart admin-bot"
Invoke-SSHCommand -SessionId $s.SessionId -Command $cmd
```

### Остановка/Запуск
```powershell
# Остановить всё
$cmd = "cd /opt/field-service && docker compose down"
Invoke-SSHCommand -SessionId $s.SessionId -Command $cmd

# Запустить всё
$cmd = "cd /opt/field-service && docker compose up -d"
Invoke-SSHCommand -SessionId $s.SessionId -Command $cmd

# Пересобрать и запустить
$cmd = "cd /opt/field-service && docker compose build && docker compose up -d"
Invoke-SSHCommand -SessionId $s.SessionId -Command $cmd -TimeOut 300
```

### Применение миграций
```powershell
$cmd = "cd /opt/field-service && docker compose run --rm admin-bot alembic upgrade head"
$result = Invoke-SSHCommand -SessionId $s.SessionId -Command $cmd -TimeOut 120
Write-Host $result.Output
```

## 🗄️ База данных

### Подключение к PostgreSQL
```powershell
$cmd = "docker compose exec postgres psql -U fs_user -d field_service -c 'SELECT COUNT(*) FROM orders;'"
$result = Invoke-SSHCommand -SessionId $s.SessionId -Command $cmd
Write-Host $result.Output
```

### Список таблиц
```powershell
$cmd = "docker compose exec postgres psql -U fs_user -d field_service -c '\dt'"
$result = Invoke-SSHCommand -SessionId $s.SessionId -Command $cmd
```

### Резервная копия БД
```powershell
$cmd = "docker compose exec postgres pg_dump -U fs_user field_service > /tmp/backup_$(date +%Y%m%d_%H%M%S).sql"
Invoke-SSHCommand -SessionId $s.SessionId -Command $cmd
```

## 📊 Мониторинг

### Проверка ресурсов
```powershell
# Диск
$cmd = "df -h"
$result = Invoke-SSHCommand -SessionId $s.SessionId -Command $cmd

# Память
$cmd = "free -h"
$result = Invoke-SSHCommand -SessionId $s.SessionId -Command $cmd

# Docker статистика
$cmd = "docker stats --no-stream"
$result = Invoke-SSHCommand -SessionId $s.SessionId -Command $cmd
```

### Heartbeat проверка
```powershell
$cmd = "cd /opt/field-service && docker compose logs admin-bot | grep 'alive' | tail -5"
$result = Invoke-SSHCommand -SessionId $s.SessionId -Command $cmd
Write-Host $result.Output
```

## 🔄 Обновление проекта

### Полная процедура обновления
```powershell
$pass = ConvertTo-SecureString "owo?8x-YA@vRN*" -AsPlainText -Force
$cred = New-Object System.Management.Automation.PSCredential("root", $pass)

# 1. Создать архив локально
cd C:\ProjectF
tar -czf field-service.tar.gz --exclude='.venv' --exclude='__pycache__' field-service

# 2. Загрузить на сервер
$sftp = New-SFTPSession -ComputerName 217.199.254.27 -Credential $cred -AcceptKey
Set-SFTPItem -SessionId $sftp.SessionId -Path "C:\ProjectF\field-service.tar.gz" -Destination "/tmp/" -Force
Remove-SFTPSession -SessionId $sftp.SessionId

# 3. Остановить боты, распаковать, запустить
$s = New-SSHSession -ComputerName 217.199.254.27 -Credential $cred -AcceptKey

Invoke-SSHCommand -SessionId $s.SessionId -Command "cd /opt/field-service && docker compose stop admin-bot master-bot"

Invoke-SSHCommand -SessionId $s.SessionId -Command "cd /opt && rm -rf field-service-backup && mv field-service field-service-backup && tar -xzf /tmp/field-service.tar.gz"

Invoke-SSHCommand -SessionId $s.SessionId -Command "cd /opt/field-service && docker compose build" -TimeOut 300

Invoke-SSHCommand -SessionId $s.SessionId -Command "cd /opt/field-service && docker compose run --rm admin-bot alembic upgrade head" -TimeOut 120

Invoke-SSHCommand -SessionId $s.SessionId -Command "cd /opt/field-service && docker compose up -d"

Remove-SSHSession -SessionId $s.SessionId
```

## 🎯 Типичные задачи

### Задача 1: Проверить что боты работают
```powershell
$pass = ConvertTo-SecureString "owo?8x-YA@vRN*" -AsPlainText -Force
$cred = New-Object System.Management.Automation.PSCredential("root", $pass)
$s = New-SSHSession -ComputerName 217.199.254.27 -Credential $cred -AcceptKey

Write-Host "`n=== STATUS ===" -ForegroundColor Cyan
$r = Invoke-SSHCommand -SessionId $s.SessionId -Command "cd /opt/field-service && docker compose ps"
Write-Host $r.Output

Write-Host "`n=== ADMIN BOT LOGS ===" -ForegroundColor Cyan
$r = Invoke-SSHCommand -SessionId $s.SessionId -Command "cd /opt/field-service && docker compose logs admin-bot --tail=20"
Write-Host $r.Output

Write-Host "`n=== MASTER BOT LOGS ===" -ForegroundColor Cyan
$r = Invoke-SSHCommand -SessionId $s.SessionId -Command "cd /opt/field-service && docker compose logs master-bot --tail=20"
Write-Host $r.Output

Remove-SSHSession -SessionId $s.SessionId
```

### Задача 2: Изменить .env файл
```powershell
$pass = ConvertTo-SecureString "owo?8x-YA@vRN*" -AsPlainText -Force
$cred = New-Object System.Management.Automation.PSCredential("root", $pass)
$s = New-SSHSession -ComputerName 217.199.254.27 -Credential $cred -AcceptKey

$newEnv = @"
DATABASE_URL=postgresql+asyncpg://fs_user:fs_password@postgres:5432/field_service
MASTER_BOT_TOKEN=новый_токен_тут
ADMIN_BOT_TOKEN=новый_токен_тут
TIMEZONE=Europe/Moscow
# ... остальные настройки
"@

$cmd = @"
cat > /opt/field-service/.env << 'ENVEOF'
$newEnv
ENVEOF
"@

Invoke-SSHCommand -SessionId $s.SessionId -Command $cmd
Invoke-SSHCommand -SessionId $s.SessionId -Command "cd /opt/field-service && docker compose restart"

Remove-SSHSession -SessionId $s.SessionId
```

### Задача 3: Посмотреть логи за последний час
```powershell
$cmd = "cd /opt/field-service && docker compose logs --since 1h"
$result = Invoke-SSHCommand -SessionId $s.SessionId -Command $cmd
Write-Host $result.Output
```

## ⚠️ Важные заметки

1. **Всегда закрывай сессии** после использования: `Remove-SSHSession -SessionId $s.SessionId`

2. **Для долгих команд** используй TimeOut: 
   ```powershell
   Invoke-SSHCommand -SessionId $s.SessionId -Command "..." -TimeOut 300
   ```

3. **При создании файлов** используй heredoc с EOF:
   ```bash
   cat > file.txt << 'EOF'
   содержимое
   EOF
   ```

4. **Текущие токены ботов** (из .env):
   - MASTER_BOT_TOKEN: 8423680284:AAHXBq-Lmtn5cVwUoxMwhJPOAoCMVGz4688
   - ADMIN_BOT_TOKEN: 7531617746:AAGvHQ0RySGtSSMAYenNdwyenZFkTZA6xbQ

5. **Admin ID**: 332786197

6. **Channels**:
   - LOGS: -1003026745283
   - ALERTS: -1002959114551
   - REPORTS: -1003056834543

## 🔍 Диагностика проблем

### Боты не запускаются
```powershell
# Проверить логи на ошибки
$cmd = "cd /opt/field-service && docker compose logs admin-bot | grep -i error | tail -20"
Invoke-SSHCommand -SessionId $s.SessionId -Command $cmd

# Проверить подключение к БД
$cmd = "docker compose exec postgres pg_isready -U fs_user -d field_service"
Invoke-SSHCommand -SessionId $s.SessionId -Command $cmd

# Проверить .env файл
$cmd = "cat /opt/field-service/.env"
Invoke-SSHCommand -SessionId $s.SessionId -Command $cmd
```

### Конфликт ботов (409 Error)
```powershell
# Остановить все контейнеры
$cmd = "cd /opt/field-service && docker compose down"
Invoke-SSHCommand -SessionId $s.SessionId -Command $cmd

# Подождать 10 секунд
Start-Sleep -Seconds 10

# Запустить снова
$cmd = "cd /opt/field-service && docker compose up -d"
Invoke-SSHCommand -SessionId $s.SessionId -Command $cmd
```

### Мало места на диске
```powershell
# Очистить Docker
$cmd = "docker system prune -a -f"
Invoke-SSHCommand -SessionId $s.SessionId -Command $cmd

# Удалить старые логи
$cmd = "find /opt/field-service -name '*.log' -mtime +7 -delete"
Invoke-SSHCommand -SessionId $s.SessionId -Command $cmd
```

## 📝 Шаблон для быстрого использования

Скопируй и адаптируй:

```powershell
# === ПОДКЛЮЧЕНИЕ К СЕРВЕРУ ===
$pass = ConvertTo-SecureString "owo?8x-YA@vRN*" -AsPlainText -Force
$cred = New-Object System.Management.Automation.PSCredential("root", $pass)
$s = New-SSHSession -ComputerName 217.199.254.27 -Credential $cred -AcceptKey

# === ТВОИ КОМАНДЫ ТУТ ===
$r = Invoke-SSHCommand -SessionId $s.SessionId -Command "твоя_команда_здесь"
Write-Host $r.Output

# === ЗАКРЫТИЕ СЕССИИ ===
Remove-SSHSession -SessionId $s.SessionId
```

---

**Версия документа**: 1.0  
**Дата**: 10 октября 2025  
**Проект**: Field Service v1.2  
**Сервер**: Ubuntu 24.04 @ Timeweb Cloud
