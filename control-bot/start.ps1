# Field Service Control Bot - Quick Start

Write-Host "========================================" -ForegroundColor Green
Write-Host "Field Service Control Bot" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""

# Check Python
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "ERROR: Python not found!" -ForegroundColor Red
    Write-Host "Install Python from: https://www.python.org/" -ForegroundColor Yellow
    exit 1
}

Write-Host "Python version:" -ForegroundColor Cyan
python --version

# Check if requirements installed
Write-Host "`nChecking dependencies..." -ForegroundColor Cyan
$pipList = pip list 2>$null
if ($pipList -notmatch "aiogram") {
    Write-Host "Installing dependencies..." -ForegroundColor Yellow
    pip install -r requirements.txt
} else {
    Write-Host "Dependencies OK" -ForegroundColor Green
}

# Check .env
if (-not (Test-Path ".env")) {
    Write-Host "`nERROR: .env file not found!" -ForegroundColor Red
    exit 1
}

Write-Host "`nConfiguration:" -ForegroundColor Cyan
Get-Content .env | Where-Object { $_ -notmatch "PASSWORD" } | ForEach-Object {
    Write-Host "  $_" -ForegroundColor White
}

Write-Host "`n========================================" -ForegroundColor Green
Write-Host "Starting Control Bot..." -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Press Ctrl+C to stop" -ForegroundColor Yellow
Write-Host ""

# Start bot
python control_bot.py
