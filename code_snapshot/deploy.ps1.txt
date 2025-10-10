# Field Service Server Deployment Script
# Run this from Windows PowerShell

$SERVER_IP = "217.199.254.27"
$SERVER_USER = "root"
$SERVER_PASS = "owo?8x-YA@vRN*"
$PROJECT_PATH = "C:\ProjectF\field-service"
$SETUP_SCRIPT = "C:\ProjectF\setup_server.sh"

Write-Host "=========================================" -ForegroundColor Green
Write-Host "Field Service Deployment to Ubuntu Server" -ForegroundColor Green
Write-Host "=========================================" -ForegroundColor Green
Write-Host ""

# Check if required files exist
if (-not (Test-Path $PROJECT_PATH)) {
    Write-Host "ERROR: Project directory not found: $PROJECT_PATH" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path $SETUP_SCRIPT)) {
    Write-Host "ERROR: Setup script not found: $SETUP_SCRIPT" -ForegroundColor Red
    exit 1
}

Write-Host "Checking SSH/SCP availability..." -ForegroundColor Yellow

# Check if OpenSSH is available (Windows 10+)
$sshAvailable = Get-Command ssh -ErrorAction SilentlyContinue
$scpAvailable = Get-Command scp -ErrorAction SilentlyContinue

if (-not $sshAvailable -or -not $scpAvailable) {
    Write-Host "ERROR: OpenSSH not found!" -ForegroundColor Red
    Write-Host "Please install OpenSSH Client:" -ForegroundColor Yellow
    Write-Host "Settings > Apps > Optional Features > OpenSSH Client" -ForegroundColor Yellow
    Write-Host "Or use PuTTY/WinSCP for manual deployment" -ForegroundColor Yellow
    exit 1
}

Write-Host "✓ OpenSSH found" -ForegroundColor Green
Write-Host ""

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "STEP 1: Upload setup script" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan

# Note: sshpass alternative for Windows - using plink from PuTTY suite
Write-Host "Uploading setup_server.sh..." -ForegroundColor Yellow
Write-Host "You will be prompted for password: $SERVER_PASS" -ForegroundColor Yellow
Write-Host ""

# Upload setup script
scp $SETUP_SCRIPT "${SERVER_USER}@${SERVER_IP}:/root/setup_server.sh"

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Failed to upload setup script" -ForegroundColor Red
    exit 1
}

Write-Host "✓ Setup script uploaded" -ForegroundColor Green
Write-Host ""

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "STEP 2: Run server setup" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "Running setup script on server..." -ForegroundColor Yellow
Write-Host "This will take 2-5 minutes..." -ForegroundColor Yellow
Write-Host ""

# Run setup script
ssh "${SERVER_USER}@${SERVER_IP}" "chmod +x /root/setup_server.sh && bash /root/setup_server.sh"

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Setup script failed" -ForegroundColor Red
    exit 1
}

Write-Host "✓ Server setup completed" -ForegroundColor Green
Write-Host ""

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "STEP 3: Upload project files" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "Uploading field-service project..." -ForegroundColor Yellow
Write-Host "This may take several minutes..." -ForegroundColor Yellow
Write-Host ""

# Upload project files
scp -r $PROJECT_PATH "${SERVER_USER}@${SERVER_IP}:/opt/"

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Failed to upload project files" -ForegroundColor Red
    exit 1
}

Write-Host "✓ Project files uploaded" -ForegroundColor Green
Write-Host ""

Write-Host "=========================================" -ForegroundColor Green
Write-Host "DEPLOYMENT SUMMARY" -ForegroundColor Green
Write-Host "=========================================" -ForegroundColor Green
Write-Host ""
Write-Host "✓ Server configured" -ForegroundColor Green
Write-Host "✓ Docker installed" -ForegroundColor Green
Write-Host "✓ PostgreSQL running" -ForegroundColor Green
Write-Host "✓ Project uploaded" -ForegroundColor Green
Write-Host ""
Write-Host "=========================================" -ForegroundColor Yellow
Write-Host "NEXT STEPS (MANUAL)" -ForegroundColor Yellow
Write-Host "=========================================" -ForegroundColor Yellow
Write-Host ""
Write-Host "1. SSH to server:" -ForegroundColor White
Write-Host "   ssh root@$SERVER_IP" -ForegroundColor Cyan
Write-Host ""
Write-Host "2. Edit .env file:" -ForegroundColor White
Write-Host "   cd /opt/field-service" -ForegroundColor Cyan
Write-Host "   nano .env" -ForegroundColor Cyan
Write-Host "   (Update bot tokens, channel IDs, admin IDs)" -ForegroundColor Gray
Write-Host ""
Write-Host "3. Build and run:" -ForegroundColor White
Write-Host "   docker compose build" -ForegroundColor Cyan
Write-Host "   docker compose run --rm admin-bot alembic upgrade head" -ForegroundColor Cyan
Write-Host "   docker compose up -d" -ForegroundColor Cyan
Write-Host ""
Write-Host "4. Check status:" -ForegroundColor White
Write-Host "   docker compose ps" -ForegroundColor Cyan
Write-Host "   docker compose logs -f" -ForegroundColor Cyan
Write-Host ""
Write-Host "5. Read detailed instructions:" -ForegroundColor White
Write-Host "   cat /root/NEXT_STEPS.txt" -ForegroundColor Cyan
Write-Host ""
Write-Host "=========================================" -ForegroundColor Green
Write-Host "Deployment script completed!" -ForegroundColor Green
Write-Host "=========================================" -ForegroundColor Green
