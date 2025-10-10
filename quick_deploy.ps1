# Quick Deploy Script
$SERVER = "217.199.254.27"
$USER = "root"
$SETUP_SCRIPT = "C:\ProjectF\remote_setup.sh"
$PROJECT_DIR = "C:\ProjectF\field-service"

Write-Host "================================" -ForegroundColor Green
Write-Host "Field Service Quick Deploy" -ForegroundColor Green
Write-Host "================================" -ForegroundColor Green
Write-Host ""
Write-Host "Server: $SERVER" -ForegroundColor Yellow
Write-Host "Password: owo?8x-YA@vRN*" -ForegroundColor Yellow
Write-Host ""

# Check prerequisites
if (-not (Test-Path $SETUP_SCRIPT)) {
    Write-Host "ERROR: Setup script not found!" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path $PROJECT_DIR)) {
    Write-Host "ERROR: Project directory not found!" -ForegroundColor Red
    exit 1
}

Write-Host "[1/3] Uploading setup script..." -ForegroundColor Cyan
Write-Host "You will be asked for password..." -ForegroundColor Yellow
Write-Host ""

# Upload setup script
& scp $SETUP_SCRIPT "${USER}@${SERVER}:/root/setup.sh"

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Failed to upload script" -ForegroundColor Red
    exit 1
}

Write-Host "OK: Script uploaded" -ForegroundColor Green
Write-Host ""

Write-Host "[2/3] Running setup on server..." -ForegroundColor Cyan
Write-Host "This will take 3-5 minutes..." -ForegroundColor Yellow
Write-Host ""

# Execute setup script
& ssh "${USER}@${SERVER}" "chmod +x /root/setup.sh && bash /root/setup.sh"

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Setup failed" -ForegroundColor Red
    exit 1
}

Write-Host "OK: Server configured" -ForegroundColor Green
Write-Host ""

Write-Host "[3/3] Uploading project files..." -ForegroundColor Cyan
Write-Host "This may take 2-3 minutes..." -ForegroundColor Yellow
Write-Host ""

# Upload project
& scp -r $PROJECT_DIR "${USER}@${SERVER}:/opt/"

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Failed to upload project" -ForegroundColor Red
    exit 1
}

Write-Host "OK: Project uploaded" -ForegroundColor Green
Write-Host ""
Write-Host "================================" -ForegroundColor Green
Write-Host "DEPLOYMENT COMPLETE!" -ForegroundColor Green
Write-Host "================================" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "1. Connect: ssh root@$SERVER" -ForegroundColor White
Write-Host "2. Edit .env: nano /opt/field-service/.env" -ForegroundColor White
Write-Host "3. Build: cd /opt/field-service && docker compose build" -ForegroundColor White
Write-Host "4. Migrate: docker compose run --rm admin-bot alembic upgrade head" -ForegroundColor White
Write-Host "5. Start: docker compose up -d" -ForegroundColor White
Write-Host ""
