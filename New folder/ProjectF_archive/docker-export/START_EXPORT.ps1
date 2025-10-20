# ===================================================================
# Field Service - Complete Export Script
# ===================================================================

Write-Host "=== Field Service Docker Export ===" -ForegroundColor Cyan
Write-Host ""

Write-Host "This script will:" -ForegroundColor White
Write-Host "  1. Build Docker images" -ForegroundColor Gray
Write-Host "  2. Export containers to .tar files" -ForegroundColor Gray
Write-Host "  3. Create database backup" -ForegroundColor Gray
Write-Host "  4. Prepare everything for server deployment" -ForegroundColor Gray
Write-Host ""

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Write-Host "Working directory: $scriptDir" -ForegroundColor Gray
Write-Host ""

$confirmation = Read-Host "Continue? (Y/N)"
if ($confirmation -ne 'Y' -and $confirmation -ne 'y') {
    Write-Host "Cancelled" -ForegroundColor Yellow
    exit 0
}

Write-Host ""
Write-Host "======================================" -ForegroundColor Cyan
Write-Host "Starting export process..." -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""

# Run the export script
& "$scriptDir\1_export_all.ps1"

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "ERROR: Export failed!" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "======================================" -ForegroundColor Cyan
Write-Host "Export completed successfully!" -ForegroundColor Green
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""

# Calculate total size
$exportSize = 0
if (Test-Path "$scriptDir\images") {
    Get-ChildItem -Path "$scriptDir\images" -Filter "*.tar" -ErrorAction SilentlyContinue | ForEach-Object {
        $exportSize += $_.Length
    }
}

if ($exportSize -gt 0) {
    $exportSizeMB = [math]::Round($exportSize / 1MB, 2)
    Write-Host "Total export size: $exportSizeMB MB" -ForegroundColor Cyan
}

Write-Host ""
Write-Host "Files location:" -ForegroundColor White
Write-Host "  $scriptDir" -ForegroundColor Gray
Write-Host ""

Write-Host "Exported files:" -ForegroundColor White
if (Test-Path "$scriptDir\images\admin-bot.tar") {
    Write-Host "  [OK] images\admin-bot.tar" -ForegroundColor Green
} else {
    Write-Host "  [!!] images\admin-bot.tar - NOT FOUND" -ForegroundColor Red
}

if (Test-Path "$scriptDir\images\master-bot.tar") {
    Write-Host "  [OK] images\master-bot.tar" -ForegroundColor Green
} else {
    Write-Host "  [!!] images\master-bot.tar - NOT FOUND" -ForegroundColor Red
}

if (Test-Path "$scriptDir\images\postgres.tar") {
    Write-Host "  [OK] images\postgres.tar" -ForegroundColor Green
} else {
    Write-Host "  [!!] images\postgres.tar - NOT FOUND" -ForegroundColor Red
}

if (Test-Path "$scriptDir\init-db\backup.sql") {
    Write-Host "  [OK] init-db\backup.sql" -ForegroundColor Green
} else {
    Write-Host "  [!!] init-db\backup.sql - NOT FOUND" -ForegroundColor Red
}

Write-Host ""
Write-Host "======================================" -ForegroundColor Cyan
Write-Host "NEXT STEPS" -ForegroundColor Yellow
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "1. Copy 'docker-export' folder to your server" -ForegroundColor White
Write-Host ""

Write-Host "2. On the server:" -ForegroundColor White
Write-Host "   - Install Docker Desktop" -ForegroundColor Gray
Write-Host "   - Run: .\0_check_server.ps1" -ForegroundColor Gray
Write-Host "   - Configure: Copy-Item .env.example .env; notepad .env" -ForegroundColor Gray
Write-Host "   - Deploy: .\2_import_and_deploy.ps1" -ForegroundColor Gray
Write-Host ""

Write-Host "3. Read QUICKSTART.md for detailed instructions" -ForegroundColor White
Write-Host ""

$openFolder = Read-Host "Open folder in Explorer? (Y/N)"
if ($openFolder -eq 'Y' -or $openFolder -eq 'y') {
    Start-Process explorer.exe -ArgumentList $scriptDir
}

Write-Host ""
Write-Host "Done!" -ForegroundColor Green
Write-Host ""
