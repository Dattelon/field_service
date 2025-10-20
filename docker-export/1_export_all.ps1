# ===================================================================
# Скрипт экспорта Docker-контейнеров Field Service для переноса
# ===================================================================

Write-Host "=== Field Service Docker Export ===" -ForegroundColor Cyan
Write-Host ""

# Проверка что Docker запущен
Write-Host "[1/7] Проверка Docker..." -ForegroundColor Yellow
try {
    docker ps | Out-Null
    Write-Host "✓ Docker запущен" -ForegroundColor Green
} catch {
    Write-Host "✗ Docker не запущен или не установлен!" -ForegroundColor Red
    Write-Host "Запустите Docker Desktop и повторите попытку" -ForegroundColor Red
    exit 1
}

# Переход в директорию проекта
Write-Host ""
Write-Host "[2/7] Переход в директорию field-service..." -ForegroundColor Yellow
Set-Location "C:\ProjectF\field-service"
Write-Host "✓ Текущая директория: $(Get-Location)" -ForegroundColor Green

# Остановка контейнеров если запущены
Write-Host ""
Write-Host "[3/7] Остановка контейнеров (если запущены)..." -ForegroundColor Yellow
docker-compose down 2>&1 | Out-Null
Write-Host "✓ Контейнеры остановлены" -ForegroundColor Green

# Сборка образов
Write-Host ""
Write-Host "[4/7] Сборка Docker-образов..." -ForegroundColor Yellow
Write-Host "Это может занять несколько минут..." -ForegroundColor Gray
docker-compose build --no-cache
if ($LASTEXITCODE -ne 0) {
    Write-Host "✗ Ошибка при сборке образов!" -ForegroundColor Red
    exit 1
}
Write-Host "✓ Образы собраны успешно" -ForegroundColor Green

# Создание папок для экспорта
Write-Host ""
Write-Host "[5/7] Подготовка директорий экспорта..." -ForegroundColor Yellow
$exportDir = "C:\ProjectF\docker-export"
$imagesDir = "$exportDir\images"
$initDbDir = "$exportDir\init-db"

if (Test-Path $imagesDir) { Remove-Item $imagesDir -Recurse -Force }
if (Test-Path $initDbDir) { Remove-Item $initDbDir -Recurse -Force }

New-Item -ItemType Directory -Path $imagesDir -Force | Out-Null
New-Item -ItemType Directory -Path $initDbDir -Force | Out-Null
Write-Host "✓ Директории созданы" -ForegroundColor Green

# Экспорт образов
Write-Host ""
Write-Host "[6/7] Экспорт Docker-образов..." -ForegroundColor Yellow

Write-Host "  → Экспорт admin-bot..." -ForegroundColor Gray
docker save field-service-admin-bot:latest -o "$imagesDir\admin-bot.tar"
if ($LASTEXITCODE -ne 0) {
    Write-Host "  ✗ Ошибка экспорта admin-bot!" -ForegroundColor Red
    exit 1
}
$adminSize = [math]::Round((Get-Item "$imagesDir\admin-bot.tar").Length / 1MB, 2)
Write-Host "  ✓ admin-bot.tar ($adminSize MB)" -ForegroundColor Green

Write-Host "  → Экспорт master-bot..." -ForegroundColor Gray
docker save field-service-master-bot:latest -o "$imagesDir\master-bot.tar"
if ($LASTEXITCODE -ne 0) {
    Write-Host "  ✗ Ошибка экспорта master-bot!" -ForegroundColor Red
    exit 1
}
$masterSize = [math]::Round((Get-Item "$imagesDir\master-bot.tar").Length / 1MB, 2)
Write-Host "  ✓ master-bot.tar ($masterSize MB)" -ForegroundColor Green

Write-Host "  → Экспорт postgres..." -ForegroundColor Gray
docker pull postgres:15-alpine 2>&1 | Out-Null
docker save postgres:15-alpine -o "$imagesDir\postgres.tar"
if ($LASTEXITCODE -ne 0) {
    Write-Host "  ✗ Ошибка экспорта postgres!" -ForegroundColor Red
    exit 1
}
$pgSize = [math]::Round((Get-Item "$imagesDir\postgres.tar").Length / 1MB, 2)
Write-Host "  ✓ postgres.tar ($pgSize MB)" -ForegroundColor Green

# Экспорт данных БД
Write-Host ""
Write-Host "[7/7] Экспорт данных базы данных..." -ForegroundColor Yellow

# Запуск временного контейнера БД для экспорта
Write-Host "  → Запуск временного контейнера БД..." -ForegroundColor Gray
docker-compose up -d postgres
Start-Sleep -Seconds 10

Write-Host "  → Создание дампа БД..." -ForegroundColor Gray
docker-compose exec -T postgres pg_dump -U fs_user -d field_service --clean --if-exists > "$initDbDir\backup.sql"
if ($LASTEXITCODE -ne 0) {
    Write-Host "  ✗ Ошибка создания дампа БД!" -ForegroundColor Red
    docker-compose down
    exit 1
}
$dbSize = [math]::Round((Get-Item "$initDbDir\backup.sql").Length / 1KB, 2)
Write-Host "  ✓ backup.sql ($dbSize KB)" -ForegroundColor Green

# Остановка временного контейнера
Write-Host "  → Остановка контейнера БД..." -ForegroundColor Gray
docker-compose down
Write-Host "  ✓ Контейнер остановлен" -ForegroundColor Green

# Итоговая информация
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "✓ ЭКСПОРТ ЗАВЕРШЁН УСПЕШНО!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Файлы экспорта сохранены в:" -ForegroundColor White
Write-Host "  $exportDir" -ForegroundColor Gray
Write-Host ""
Write-Host "Размеры файлов:" -ForegroundColor White
Write-Host "  admin-bot.tar   : $adminSize MB" -ForegroundColor Gray
Write-Host "  master-bot.tar  : $masterSize MB" -ForegroundColor Gray
Write-Host "  postgres.tar    : $pgSize MB" -ForegroundColor Gray
Write-Host "  backup.sql      : $dbSize KB" -ForegroundColor Gray
$totalSize = $adminSize + $masterSize + $pgSize + ($dbSize / 1024)
Write-Host "  Всего           : $([math]::Round($totalSize, 2)) MB" -ForegroundColor Yellow
Write-Host ""
Write-Host "Следующие шаги:" -ForegroundColor Cyan
Write-Host "1. Скопируйте папку docker-export на целевой сервер" -ForegroundColor White
Write-Host "2. Настройте .env файл на сервере" -ForegroundColor White
Write-Host "3. Запустите скрипт 2_import_and_deploy.ps1" -ForegroundColor White
Write-Host ""
