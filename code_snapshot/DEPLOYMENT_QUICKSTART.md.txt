# 🚀 БЫСТРЫЙ СТАРТ - CI/CD для Field Service

## 📦 ЧТО УСТАНОВЛЕНО

✅ **Скрипты деплоя:**
- `deploy_to_production.ps1` - Главный скрипт деплоя
- `rollback_deployment.ps1` - Откат к предыдущей версии
- `check_server_health.ps1` - Проверка здоровья сервера
- `view_server_logs.ps1` - Просмотр логов

✅ **Автобэкапы БД:**
- Установка: `install_auto_backups.ps1`
- Ежедневные (2:00) - 7 дней
- Еженедельные (воскр 3:00) - 4 недели
- Ежемесячные (1-го числа 4:00) - 12 месяцев

---

## ⚡ ЕЖЕДНЕВНАЯ РАБОТА

### 1. Разработка локально
```powershell
cd C:\ProjectF\field-service

# Внеси изменения в код
# ...

# Запусти тесты
python -m pytest tests/

# Протестируй локально
python -m field_service.bots.admin_bot.main
```

### 2. Деплой на продакшн (ОДНА КОМАНДА!)
```powershell
C:\ProjectF\deploy_to_production.ps1
```

**Скрипт автоматически:**
- ✅ Создаст бэкап БД
- ✅ Загрузит код
- ✅ Соберёт Docker образы
- ✅ Применит миграции
- ✅ Сделает graceful restart
- ✅ Проверит здоровье

### 3. Проверка после деплоя
```powershell
# Проверить здоровье
C:\ProjectF\check_server_health.ps1

# Посмотреть логи
C:\ProjectF\view_server_logs.ps1 -Service all -Lines 100

# Следить за логами в реальном времени
C:\ProjectF\view_server_logs.ps1 -Follow
```

### 4. Если что-то пошло не так
```powershell
# Откат к предыдущей версии
C:\ProjectF\rollback_deployment.ps1
```

---

## 🗄️ РАБОТА С БЭКАПАМИ

### Установка автобэкапов (один раз)
```powershell
C:\ProjectF\install_auto_backups.ps1
```

### Ручной бэкап (перед рискованными изменениями)
```powershell
# Автоматически создаётся при deploy_to_production.ps1
# Или вручную:
$pass = ConvertTo-SecureString "owo?8x-YA@vRN*" -AsPlainText -Force
$cred = New-Object System.Management.Automation.PSCredential("root", $pass)
$s = New-SSHSession -ComputerName 217.199.254.27 -Credential $cred -AcceptKey
Invoke-SSHCommand -SessionId $s.SessionId -Command "/usr/local/bin/field-service-backup.sh daily"
Remove-SSHSession -SessionId $s.SessionId
```

### Список бэкапов
```powershell
$s = New-SSHSession -ComputerName 217.199.254.27 -Credential $cred -AcceptKey
Invoke-SSHCommand -SessionId $s.SessionId -Command "ls -lh /opt/backups/*/"
Remove-SSHSession -SessionId $s.SessionId
```

### Восстановление из бэкапа
```powershell
# На сервере
ssh root@217.199.254.27
/usr/local/bin/field-service-restore.sh /opt/backups/daily/backup_20251010_020000.sql.gz
```

---

## 🎯 ЧАСТЫЕ СЦЕНАРИИ

### Сценарий 1: Быстрое исправление бага
```powershell
# 1. Исправь код локально
# 2. Протестируй
# 3. Деплой
C:\ProjectF\deploy_to_production.ps1

# 4. Проверь
C:\ProjectF\check_server_health.ps1
```

### Сценарий 2: Обновление с миграциями БД
```powershell
# 1. Создай миграцию локально
cd C:\ProjectF\field-service
alembic revision -m "add_new_field"

# 2. Отредактируй миграцию
# 3. Протестируй локально
alembic upgrade head

# 4. Деплой (миграции применятся автоматически)
C:\ProjectF\deploy_to_production.ps1
```

### Сценарий 3: Откат после неудачного деплоя
```powershell
# 1. Заметил проблему
C:\ProjectF\view_server_logs.ps1 -Lines 200

# 2. Откат
C:\ProjectF\rollback_deployment.ps1

# 3. Проверка
C:\ProjectF\check_server_health.ps1
```

### Сценарий 4: Проверка перед важными изменениями
```powershell
# 1. Создать ручной бэкап
# (смотри раздел "Ручной бэкап")

# 2. Проверить текущее состояние
C:\ProjectF\check_server_health.ps1

# 3. Деплой
C:\ProjectF\deploy_to_production.ps1

# 4. Мониторинг
C:\ProjectF\view_server_logs.ps1 -Follow
```

---

## 📊 ПАРАМЕТРЫ ДЕПЛОЯ

### Полный деплой (по умолчанию)
```powershell
C:\ProjectF\deploy_to_production.ps1
```

### Деплой без бэкапа (не рекомендуется)
```powershell
C:\ProjectF\deploy_to_production.ps1 -CreateBackup $false
```

### Деплой без миграций
```powershell
C:\ProjectF\deploy_to_production.ps1 -RunMigrations $false
```

### Деплой без тестов (быстро)
```powershell
C:\ProjectF\deploy_to_production.ps1 -SkipTests $true
```

### Деплой со стандартным рестартом (не graceful)
```powershell
C:\ProjectF\deploy_to_production.ps1 -GracefulRestart $false
```

---

## 🔍 МОНИТОРИНГ

### Просмотр логов admin-bot
```powershell
C:\ProjectF\view_server_logs.ps1 -Service admin-bot -Lines 50
```

### Просмотр логов master-bot
```powershell
C:\ProjectF\view_server_logs.ps1 -Service master-bot -Lines 50
```

### Следить за логами в реальном времени
```powershell
C:\ProjectF\view_server_logs.ps1 -Follow
```

### Проверка здоровья
```powershell
C:\ProjectF\check_server_health.ps1
```

---

## 📁 ЛОГИ ДЕПЛОЯ

Все деплои логируются в:
```
C:\ProjectF\deployment_logs\deploy_YYYYMMDD_HHMMSS.log
```

Посмотреть последний лог:
```powershell
Get-Content (Get-ChildItem C:\ProjectF\deployment_logs\*.log | Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName
```

---

## ⚠️ ВАЖНО

1. **ВСЕГДА** тестируй локально перед деплоем
2. **Бэкапы** создаются автоматически при деплое
3. **Graceful restart** минимизирует даунтайм
4. **Логи** сохраняются для анализа
5. **Откат** доступен всегда

---

## 🆘 TROUBLESHOOTING

### Деплой завис
```powershell
# Ctrl+C для прерывания
# Проверить что происходит:
C:\ProjectF\check_server_health.ps1
```

### Боты не запускаются после деплоя
```powershell
# 1. Посмотреть логи
C:\ProjectF\view_server_logs.ps1 -Lines 200

# 2. Проверить .env файл
$s = New-SSHSession -ComputerName 217.199.254.27 -Credential $cred -AcceptKey
Invoke-SSHCommand -SessionId $s.SessionId -Command "cat /opt/field-service/.env"
Remove-SSHSession -SessionId $s.SessionId

# 3. Если не помогает - откат
C:\ProjectF\rollback_deployment.ps1
```

### Нужно восстановить БД
```powershell
# На сервере
ssh root@217.199.254.27
ls -lh /opt/backups/*/
/usr/local/bin/field-service-restore.sh /opt/backups/daily/имя_файла.sql.gz
```

---

## 📚 ДОКУМЕНТАЦИЯ

- **Полный workflow**: `C:\ProjectF\CICD_WORKFLOW.md`
- **Доступ к серверу**: `C:\ProjectF\AI_SERVER_ACCESS_GUIDE.md`
- **Быстрая справка**: `C:\ProjectF\AI_QUICK_REFERENCE.md`

---

**Версия**: 1.0  
**Дата**: 10 октября 2025  
**Проект**: Field Service v1.2
