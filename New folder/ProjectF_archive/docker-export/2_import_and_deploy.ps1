# ===================================================================
# Скрипт импорта и развёртывания Field Service на Windows Server
# ===================================================================

Write-Host "=== Field Service Docker Import & Deploy ===" -ForegroundColor Cyan
Write-Host ""

# Проверка прав администратора
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "✗ Требуются права администратора!" -ForegroundColor Red
    Write-Host "Запустите PowerShell от имени администратора" -ForegroundColor Yellow
    exit 1
}

# Проверка Docker
Write-Host "[1/8] Проверка Docker..." -ForegroundColor Yellow
try {
    docker ps | Out-Null
    Write-Host "✓ Docker запущен" -ForegroundColor Green
} catch {
    Write-Host "✗ Docker не запущен!" -ForegroundColor Red
    Write-Host ""
    Write-Host "Установите Docker Desktop:" -ForegroundColor Yellow
    Write-Host "1. Скачайте: https://www.docker.com/products/docker-desktop" -ForegroundColor White
    Write-Host "2. Установите и перезагрузите компьютер" -ForegroundColor White
    Write-Host "3. Запустите Docker Desktop" -ForegroundColor White
    Write-Host "4. Повторите запуск этого скрипта" -ForegroundColor White
    exit 1
}

# Определение рабочей директории
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Write-Host ""
Write-Host "[2/8] Рабочая директория:" -ForegroundColor Yellow
Write-Host "  $scriptDir" -ForegroundColor Gray

# Проверка наличия файлов
Write-Host ""
Write-Host "[3/8] Проверка файлов экспорта..." -ForegroundColor Yellow

$requiredFiles = @(
    "images\admin-bot.tar",
    "images\master-bot.tar", 
    "images\postgres.tar",
    "init-db\backup.sql",
    "docker-compose.yml",
    ".env"
)

$allFilesExist = $true
foreach ($file in $requiredFiles) {
    $fullPath = Join-Path $scriptDir $file
    if (Test-Path $fullPath) {
        Write-Host "  ✓ $file" -ForegroundColor Green
    } else {
        Write-Host "  ✗ $file - НЕ НАЙДЕН!" -ForegroundColor Red
        $allFilesExist = $false
    }
}

if (-not $allFilesExist) {
    Write-Host ""
    Write-Host "Некоторые файлы отсутствуют!" -ForegroundColor Red
    Write-Host "Убедитесь что скопировали ВСЮ папку docker-export" -ForegroundColor Yellow
    exit 1
}

# Загрузка Docker-образов
Write-Host ""
Write-Host "[4/8] Загрузка Docker-образов..." -ForegroundColor Yellow
Write-Host "Это может занять несколько минут..." -ForegroundColor Gray

Write-Host "  → Загрузка postgres..." -ForegroundColor Gray
docker load -i "$scriptDir\images\postgres.tar"
if ($LASTEXITCODE -ne 0) {
    Write-Host "  ✗ Ошибка загрузки postgres!" -ForegroundColor Red
    exit 1
}
Write-Host "  ✓ postgres загружен" -ForegroundColor Green

Write-Host "  → Загрузка admin-bot..." -ForegroundColor Gray
docker load -i "$scriptDir\images\admin-bot.tar"
if ($LASTEXITCODE -ne 0) {
    Write-Host "  ✗ Ошибка загрузки admin-bot!" -ForegroundColor Red
    exit 1
}
Write-Host "  ✓ admin-bot загружен" -ForegroundColor Green

Write-Host "  → Загрузка master-bot..." -ForegroundColor Gray
docker load -i "$scriptDir\images\master-bot.tar"
if ($LASTEXITCODE -ne 0) {
    Write-Host "  ✗ Ошибка загрузки master-bot!" -ForegroundColor Red
    exit 1
}
Write-Host "  ✓ master-bot загружен" -ForegroundColor Green

# Проверка .env файла
Write-Host ""
Write-Host "[5/8] Проверка конфигурации .env..." -ForegroundColor Yellow

if (-not (Test-Path "$scriptDir\.env")) {
    Write-Host "  ✗ Файл .env не найден!" -ForegroundColor Red
    Write-Host ""
    Write-Host "Создайте файл .env на основе .env.example:" -ForegroundColor Yellow
    Write-Host "1. Скопируйте .env.example → .env" -ForegroundColor White
    Write-Host "2. Заполните токены ботов" -ForegroundColor White
    Write-Host "3. Проверьте ID каналов и админов" -ForegroundColor White
    Write-Host "4. Запустите скрипт снова" -ForegroundColor White
    exit 1
}

# Чтение и проверка обязательных переменных
$envContent = Get-Content "$scriptDir\.env" -Raw
$requiredVars = @(
    "MASTER_BOT_TOKEN",
    "ADMIN_BOT_TOKEN",
    "GLOBAL_ADMINS_TG_IDS",
    "POSTGRES_PASSWORD"
)

$missingVars = @()
foreach ($var in $requiredVars) {
    if ($envContent -notmatch "$var=.+") {
        $missingVars += $var
    }
}

if ($missingVars.Count -gt 0) {
    Write-Host "  ✗ Не заполнены обязательные переменные:" -ForegroundColor Red
    foreach ($var in $missingVars) {
        Write-Host "    - $var" -ForegroundColor Yellow
    }
    Write-Host ""
    Write-Host "Отредактируйте файл .env и запустите скрипт снова" -ForegroundColor Yellow
    exit 1
}

Write-Host "  ✓ Конфигурация .env корректна" -ForegroundColor Green

# Остановка старых контейнеров (если есть)
Write-Host ""
Write-Host "[6/8] Очистка старых контейнеров..." -ForegroundColor Yellow
Set-Location $scriptDir
docker-compose down -v 2>&1 | Out-Null
Write-Host "  ✓ Старые контейнеры удалены" -ForegroundColor Green

# Запуск PostgreSQL
Write-Host ""
Write-Host "[7/8] Запуск базы данных..." -ForegroundColor Yellow
Write-Host "  → Запуск PostgreSQL..." -ForegroundColor Gray
docker-compose up -d postgres

Write-Host "  → Ожидание готовности БД (30 сек)..." -ForegroundColor Gray
Start-Sleep -Seconds 30

# Проверка состояния БД
$pgReady = docker-compose exec -T postgres pg_isready -U fs_user 2>&1
if ($pgReady -match "accepting connections") {
    Write-Host "  ✓ PostgreSQL запущен" -ForegroundColor Green
} else {
    Write-Host "  ✗ PostgreSQL не отвечает!" -ForegroundColor Red
    Write-Host "Логи контейнера:" -ForegroundColor Yellow
    docker-compose logs postgres
    exit 1
}

# Восстановление БД из дампа
Write-Host "  → Восстановление данных БД..." -ForegroundColor Gray
Get-Content "$scriptDir\init-db\backup.sql" | docker-compose exec -T postgres psql -U fs_user -d field_service
if ($LASTEXITCODE -ne 0) {
    Write-Host "  ✗ Ошибка восстановления БД!" -ForegroundColor Red
    exit 1
}
Write-Host "  ✓ База данных восстановлена" -ForegroundColor Green

# Запуск ботов
Write-Host ""
Write-Host "[8/8] Запуск ботов..." -ForegroundColor Yellow
docker-compose up -d admin-bot master-bot

Write-Host "  → Ожидание запуска (10 сек)..." -ForegroundColor Gray
Start-Sleep -Seconds 10

# Проверка статуса
Write-Host ""
Write-Host "Статус контейнеров:" -ForegroundColor Cyan
docker-compose ps

# Финал
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "✓ РАЗВЁРТЫВАНИЕ ЗАВЕРШЕНО!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Контейнеры запущены:" -ForegroundColor White
Write-Host "  • postgres    - База данных" -ForegroundColor Gray
Write-Host "  • admin-bot   - Админ-бот" -ForegroundColor Gray
Write-Host "  • master-bot  - Мастер-бот" -ForegroundColor Gray
Write-Host ""
Write-Host "Полезные команды:" -ForegroundColor Cyan
Write-Host "  Просмотр логов:        docker-compose logs -f" -ForegroundColor White
Write-Host "  Логи admin-bot:        docker-compose logs -f admin-bot" -ForegroundColor White
Write-Host "  Логи master-bot:       docker-compose logs -f master-bot" -ForegroundColor White
Write-Host "  Остановить всё:        docker-compose stop" -ForegroundColor White
Write-Host "  Запустить всё:         docker-compose start" -ForegroundColor White
Write-Host "  Перезапустить:         docker-compose restart" -ForegroundColor White
Write-Host "  Удалить всё:           docker-compose down -v" -ForegroundColor White
Write-Host ""
Write-Host "Проверьте работу ботов в Telegram!" -ForegroundColor Yellow
Write-Host ""
