# 🚀 БЫСТРАЯ ШПАРГАЛКА - Доступ к серверу

## 📋 Данные
- **IP**: 217.199.254.27
- **User**: root
- **Pass**: owo?8x-YA@vRN*
- **Проект**: /opt/field-service

## ⚡ Подключение (1 строка)
```powershell
$pass = ConvertTo-SecureString "owo?8x-YA@vRN*" -AsPlainText -Force; $cred = New-Object System.Management.Automation.PSCredential("root", $pass); $s = New-SSHSession -ComputerName 217.199.254.27 -Credential $cred -AcceptKey
```

## 🎯 Частые команды

### Статус ботов
```powershell
$r = Invoke-SSHCommand -SessionId $s.SessionId -Command "cd /opt/field-service && docker compose ps"; Write-Host $r.Output
```

### Логи admin-bot
```powershell
$r = Invoke-SSHCommand -SessionId $s.SessionId -Command "cd /opt/field-service && docker compose logs admin-bot --tail=30"; Write-Host $r.Output
```

### Логи master-bot
```powershell
$r = Invoke-SSHCommand -SessionId $s.SessionId -Command "cd /opt/field-service && docker compose logs master-bot --tail=30"; Write-Host $r.Output
```

### Перезапуск ботов
```powershell
Invoke-SSHCommand -SessionId $s.SessionId -Command "cd /opt/field-service && docker compose restart admin-bot master-bot"
```

### Остановка всех сервисов
```powershell
Invoke-SSHCommand -SessionId $s.SessionId -Command "cd /opt/field-service && docker compose down"
```

### Запуск всех сервисов
```powershell
Invoke-SSHCommand -SessionId $s.SessionId -Command "cd /opt/field-service && docker compose up -d"
```

### Миграции БД
```powershell
Invoke-SSHCommand -SessionId $s.SessionId -Command "cd /opt/field-service && docker compose run --rm admin-bot alembic upgrade head" -TimeOut 120
```

### Просмотр .env
```powershell
$r = Invoke-SSHCommand -SessionId $s.SessionId -Command "cat /opt/field-service/.env"; Write-Host $r.Output
```

## 🔄 Обновление проекта (быстро)
```powershell
# 1. Создать архив (на локальной машине)
cd C:\ProjectF; tar -czf field-service.tar.gz --exclude='.venv' --exclude='__pycache__' field-service

# 2. Загрузить
$sftp = New-SFTPSession -ComputerName 217.199.254.27 -Credential $cred -AcceptKey
Set-SFTPItem -SessionId $sftp.SessionId -Path "C:\ProjectF\field-service.tar.gz" -Destination "/tmp/" -Force
Remove-SFTPSession -SessionId $sftp.SessionId

# 3. Развернуть
Invoke-SSHCommand -SessionId $s.SessionId -Command "cd /opt/field-service && docker compose down"
Invoke-SSHCommand -SessionId $s.SessionId -Command "cd /opt && tar -xzf /tmp/field-service.tar.gz"
Invoke-SSHCommand -SessionId $s.SessionId -Command "cd /opt/field-service && docker compose build" -TimeOut 300
Invoke-SSHCommand -SessionId $s.SessionId -Command "cd /opt/field-service && docker compose up -d"
```

## ⚠️ Troubleshooting

### 409 Conflict Error (боты уже запущены)
```powershell
Invoke-SSHCommand -SessionId $s.SessionId -Command "cd /opt/field-service && docker compose down"
Start-Sleep -Seconds 10
Invoke-SSHCommand -SessionId $s.SessionId -Command "cd /opt/field-service && docker compose up -d"
```

### Проверка heartbeat
```powershell
$r = Invoke-SSHCommand -SessionId $s.SessionId -Command "cd /opt/field-service && docker compose logs admin-bot | grep 'alive' | tail -3"; Write-Host $r.Output
```

## 🔚 Закрыть сессию
```powershell
Remove-SSHSession -SessionId $s.SessionId
```

---

**Подробная инструкция**: C:\ProjectF\AI_SERVER_ACCESS_GUIDE.md
