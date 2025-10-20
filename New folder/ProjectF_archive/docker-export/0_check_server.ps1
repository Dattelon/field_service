# ===================================================================
# Скрипт проверки готовности Windows Server для Field Service
# ===================================================================

Write-Host "=== Field Service - Проверка готовности сервера ===" -ForegroundColor Cyan
Write-Host ""

$allChecks = @()
$passedChecks = 0
$totalChecks = 0

function Test-Check {
    param(
        [string]$Name,
        [scriptblock]$Test,
        [string]$PassMessage,
        [string]$FailMessage,
        [bool]$Critical = $true
    )
    
    $script:totalChecks++
    Write-Host "[$script:totalChecks] $Name..." -ForegroundColor Yellow -NoNewline
    
    try {
        $result = & $Test
        if ($result) {
            Write-Host " ✓" -ForegroundColor Green
            Write-Host "    $PassMessage" -ForegroundColor Gray
            $script:passedChecks++
            $script:allChecks += @{Name=$Name; Passed=$true; Critical=$Critical}
            return $true
        } else {
            throw "Check failed"
        }
    } catch {
        Write-Host " ✗" -ForegroundColor Red
        Write-Host "    $FailMessage" -ForegroundColor Red
        $script:allChecks += @{Name=$Name; Passed=$false; Critical=$Critical}
        return $false
    }
}

# ===== ПРОВЕРКИ =====

Write-Host "Проверка системы:" -ForegroundColor Cyan
Write-Host ""

# 1. Версия Windows
Test-Check -Name "Версия Windows" `
    -Test { 
        $os = Get-CimInstance Win32_OperatingSystem
        $os.Caption -match "Windows (Server|10|11)" -and $os.Caption -notmatch "Home"
    } `
    -PassMessage "Windows версия поддерживается" `
    -FailMessage "Требуется Windows Server 2019+, Windows 10/11 Pro" `
    -Critical $true

# 2. PowerShell версия
Test-Check -Name "PowerShell версия" `
    -Test { $PSVersionTable.PSVersion.Major -ge 5 } `
    -PassMessage "PowerShell $($PSVersionTable.PSVersion)" `
    -FailMessage "Требуется PowerShell 5.1 или новее" `
    -Critical $true

# 3. Оперативная память
Test-Check -Name "Оперативная память" `
    -Test { 
        $os = Get-CimInstance Win32_OperatingSystem
        $freeGB = [math]::Round($os.FreePhysicalMemory / 1MB, 2)
        $totalGB = [math]::Round($os.TotalVisibleMemorySize / 1MB, 2)
        Write-Host " ($freeGB GB свободно из $totalGB GB)" -ForegroundColor Gray -NoNewline
        $totalGB -ge 4
    } `
    -PassMessage "Достаточно памяти" `
    -FailMessage "Требуется минимум 4 GB RAM" `
    -Critical $true

# 4. Дисковое пространство
Test-Check -Name "Дисковое пространство" `
    -Test { 
        $drive = Get-PSDrive C
        $freeGB = [math]::Round($drive.Free / 1GB, 2)
        Write-Host " ($freeGB GB свободно)" -ForegroundColor Gray -NoNewline
        $freeGB -ge 20
    } `
    -PassMessage "Достаточно места на диске" `
    -FailMessage "Требуется минимум 20 GB свободного места" `
    -Critical $true

# 5. Виртуализация
Test-Check -Name "Поддержка виртуализации" `
    -Test { 
        $virt = Get-ComputerInfo | Select-Object -ExpandProperty HyperVisorPresent -ErrorAction SilentlyContinue
        if ($null -eq $virt) {
            $virt = (Get-CimInstance Win32_Processor).VirtualizationFirmwareEnabled
        }
        $virt -eq $true
    } `
    -PassMessage "Виртуализация включена" `
    -FailMessage "Включите VT-x/AMD-V в BIOS" `
    -Critical $true

Write-Host ""
Write-Host "Проверка Docker:" -ForegroundColor Cyan
Write-Host ""

# 6. Docker установлен
Test-Check -Name "Docker установлен" `
    -Test { 
        $null -ne (Get-Command docker -ErrorAction SilentlyContinue)
    } `
    -PassMessage "Docker найден" `
    -FailMessage "Установите Docker Desktop: https://www.docker.com/products/docker-desktop" `
    -Critical $true

# 7. Docker запущен
if ($script:allChecks[-1].Passed) {
    Test-Check -Name "Docker запущен" `
        -Test { 
            docker ps 2>&1 | Out-Null
            $LASTEXITCODE -eq 0
        } `
        -PassMessage "Docker работает" `
        -FailMessage "Запустите Docker Desktop" `
        -Critical $true
}

# 8. Docker Compose
if ($script:allChecks[-1].Passed) {
    Test-Check -Name "Docker Compose" `
        -Test { 
            docker-compose version 2>&1 | Out-Null
            $LASTEXITCODE -eq 0
        } `
        -PassMessage "Docker Compose установлен" `
        -FailMessage "Docker Compose отсутствует (должен быть в Docker Desktop)" `
        -Critical $false
}

Write-Host ""
Write-Host "Проверка сети:" -ForegroundColor Cyan
Write-Host ""

# 9. Интернет-соединение
Test-Check -Name "Подключение к интернету" `
    -Test { 
        Test-Connection -ComputerName 8.8.8.8 -Count 1 -Quiet
    } `
    -PassMessage "Интернет доступен" `
    -FailMessage "Нет подключения к интернету" `
    -Critical $true

# 10. Доступ к Telegram API
Test-Check -Name "Доступ к Telegram API" `
    -Test { 
        try {
            $response = Invoke-WebRequest -Uri "https://api.telegram.org" -UseBasicParsing -TimeoutSec 5
            $response.StatusCode -eq 200
        } catch {
            $false
        }
    } `
    -PassMessage "Telegram API доступен" `
    -FailMessage "Нет доступа к api.telegram.org (проверьте фаервол)" `
    -Critical $true

# ===== ИТОГИ =====

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Результаты проверки" -ForegroundColor White
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$criticalFailed = ($allChecks | Where-Object { -not $_.Passed -and $_.Critical }).Count

if ($passedChecks -eq $totalChecks) {
    Write-Host "✓ ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ ($passedChecks/$totalChecks)" -ForegroundColor Green
    Write-Host ""
    Write-Host "Сервер готов к развёртыванию Field Service!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Следующие шаги:" -ForegroundColor Cyan
    Write-Host "1. Скопируйте папку docker-export на сервер" -ForegroundColor White
    Write-Host "2. Настройте .env файл" -ForegroundColor White
    Write-Host "3. Запустите: .\2_import_and_deploy.ps1" -ForegroundColor White
    Write-Host ""
    exit 0
    
} elseif ($criticalFailed -eq 0) {
    Write-Host "⚠ Пройдено $passedChecks из $totalChecks проверок" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Некритичные проблемы обнаружены, но можно продолжать" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Не пройденные проверки:" -ForegroundColor Yellow
    $allChecks | Where-Object { -not $_.Passed } | ForEach-Object {
        Write-Host "  • $($_.Name)" -ForegroundColor Gray
    }
    Write-Host ""
    exit 0
    
} else {
    Write-Host "✗ КРИТИЧНЫЕ ПРОБЛЕМЫ ($criticalFailed)" -ForegroundColor Red
    Write-Host ""
    Write-Host "Не пройденные критичные проверки:" -ForegroundColor Red
    $allChecks | Where-Object { -not $_.Passed -and $_.Critical } | ForEach-Object {
        Write-Host "  • $($_.Name)" -ForegroundColor Yellow
    }
    Write-Host ""
    Write-Host "Устраните проблемы и запустите проверку снова" -ForegroundColor Yellow
    Write-Host ""
    exit 1
}
