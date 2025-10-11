# Скрипт для деплоя гибких перерывов
# Автоматизирует загрузку файлов и перезапуск master-bot

$ErrorActionPreference = "Stop"

Write-Host "=== Деплой гибких перерывов ===" -ForegroundColor Cyan

# 1. Проверяем файлы локально
Write-Host "`n1. Проверка локальных файлов..." -ForegroundColor Yellow

$files = @(
    "field_service\bots\master_bot\handlers\shift.py",
    "field_service\bots\master_bot\keyboards.py",
    "field_service\bots\master_bot\texts.py",
    "field_service\bots\master_bot\handlers\start.py",
    "field_service\bots\master_bot\main.py",
    "field_service\services\watchdogs.py"
)

foreach ($file in $files) {
    $fullPath = "C:\ProjectF\field-service\$file"
    if (Test-Path $fullPath) {
        Write-Host "  ✓ $file" -ForegroundColor Green
    } else {
        Write-Host "  ✗ $file - НЕ НАЙДЕН!" -ForegroundColor Red
        exit 1
    }
}

# 2. Запускаем тесты локально
Write-Host "`n2. Запуск тестов локально..." -ForegroundColor Yellow
$env:PYTHONIOENCODING='utf-8'
Push-Location "C:\ProjectF\field-service"
try {
    $testResult = pytest tests\test_watchdog_expired_breaks.py -v --tb=short 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  ✓ Все тесты прошли успешно" -ForegroundColor Green
    } else {
        Write-Host "  ✗ Тесты провалились:" -ForegroundColor Red
        Write-Host $testResult
        $continue = Read-Host "Продолжить деплой несмотря на ошибки? (y/N)"
        if ($continue -ne "y") {
            exit 1
        }
    }
} finally {
    Pop-Location
}

# 3. Подключаемся к серверу
Write-Host "`n3. Подключение к серверу..." -ForegroundColor Yellow

$pass = ConvertTo-SecureString "owo?8x-YA@vRN*" -AsPlainText -Force
$cred = New-Object System.Management.Automation.PSCredential("root", $pass)
$s = New-SSHSession -ComputerName 217.199.254.27 -Credential $cred -AcceptKey

if (-not $s) {
    Write-Host "  ✗ Не удалось подключиться к серверу" -ForegroundColor Red
    exit 1
}

Write-Host "  ✓ Подключено к серверу" -ForegroundColor Green

try {
    # 4. Создаём бэкап перед изменениями
    Write-Host "`n4. Создание бэкапа..." -ForegroundColor Yellow
    $backupCmd = "/usr/local/bin/field-service-backup.sh manual"
    $result = Invoke-SSHCommand -SessionId $s.SessionId -Command $backupCmd
    if ($result.ExitStatus -eq 0) {
        Write-Host "  ✓ Бэкап создан" -ForegroundColor Green
    } else {
        Write-Host "  ⚠ Не удалось создать бэкап (продолжаем)" -ForegroundColor Yellow
    }

    # 5. Копируем файлы на сервер
    Write-Host "`n5. Копирование файлов на сервер..." -ForegroundColor Yellow
    
    foreach ($file in $files) {
        $localPath = "C:\ProjectF\field-service\$file"
        $remotePath = "/opt/field-service/$($file.Replace('\', '/'))"
        
        # Создаём директорию если нужно
        $remoteDir = Split-Path -Parent $remotePath
        Invoke-SSHCommand -SessionId $s.SessionId -Command "mkdir -p $remoteDir" | Out-Null
        
        # Копируем файл
        Set-SCPFile -SessionId $s.SessionId -LocalFile $localPath -RemotePath $remotePath -Force
        Write-Host "  ✓ $file" -ForegroundColor Green
    }

    # 6. Перезапускаем master-bot
    Write-Host "`n6. Перезапуск master-bot..." -ForegroundColor Yellow
    $restartCmd = "cd /opt/field-service && docker compose restart master-bot"
    $result = Invoke-SSHCommand -SessionId $s.SessionId -Command $restartCmd
    
    if ($result.ExitStatus -eq 0) {
        Write-Host "  ✓ Master-bot перезапущен" -ForegroundColor Green
    } else {
        Write-Host "  ✗ Ошибка перезапуска:" -ForegroundColor Red
        Write-Host $result.Output
        exit 1
    }

    # 7. Ждём запуска
    Write-Host "`n7. Ожидание запуска (10 сек)..." -ForegroundColor Yellow
    Start-Sleep -Seconds 10

    # 8. Проверяем логи
    Write-Host "`n8. Проверка логов master-bot..." -ForegroundColor Yellow
    $logsCmd = "cd /opt/field-service && docker compose logs master-bot --tail=30"
    $result = Invoke-SSHCommand -SessionId $s.SessionId -Command $logsCmd
    
    # Проверяем на ошибки
    if ($result.Output -match "error|Error|ERROR|exception|Exception") {
        Write-Host "  ⚠ Обнаружены ошибки в логах:" -ForegroundColor Yellow
        Write-Host $result.Output
        $continue = Read-Host "`nПродолжить проверку? (Y/n)"
        if ($continue -eq "n") {
            exit 1
        }
    } else {
        Write-Host "  ✓ Логи выглядят нормально" -ForegroundColor Green
    }

    # 9. Проверяем статус контейнеров
    Write-Host "`n9. Проверка статуса контейнеров..." -ForegroundColor Yellow
    $statusCmd = "cd /opt/field-service && docker compose ps"
    $result = Invoke-SSHCommand -SessionId $s.SessionId -Command $statusCmd
    Write-Host $result.Output

    # 10. Финальная проверка
    Write-Host "`n10. Финальная проверка..." -ForegroundColor Yellow
    $healthCmd = @"
cd /opt/field-service && docker compose exec -T postgres psql -U postgres -d field_service -c "
    SELECT COUNT(*) as masters_on_break 
    FROM masters 
    WHERE shift_status = 'BREAK' 
    AND break_until IS NOT NULL;
"
"@
    $result = Invoke-SSHCommand -SessionId $s.SessionId -Command $healthCmd
    Write-Host $result.Output

} finally {
    # Закрываем соединение
    Remove-SSHSession -SessionId $s.SessionId | Out-Null
}

Write-Host "`n=== Деплой завершён успешно! ===" -ForegroundColor Green
Write-Host "`nЧто проверить вручную:" -ForegroundColor Cyan
Write-Host "  1. Мастер может выбрать длительность перерыва (15 мин / 1 ч / 2 ч)"
Write-Host "  2. В главном меню отображается таймер перерыва"
Write-Host "  3. После окончания перерыва мастер снимается со смены"
Write-Host "  4. Можно продлить перерыв с выбором длительности"
Write-Host "  5. За 10 минут до окончания приходит напоминание"

Write-Host "`nДокументация: C:\ProjectF\field-service\FLEXIBLE_BREAKS_DEPLOYMENT.md" -ForegroundColor Cyan
