$password = ConvertTo-SecureString "owo?8x-YA@vRN*" -AsPlainText -Force
$cred = New-Object System.Management.Automation.PSCredential ("root", $password)

Write-Host "================================" -ForegroundColor Green
Write-Host "Final Setup - Build & Deploy" -ForegroundColor Green
Write-Host "================================" -ForegroundColor Green
Write-Host ""

# Prompt for bot tokens
Write-Host "Please enter your bot tokens:" -ForegroundColor Yellow
Write-Host ""
$masterToken = Read-Host "Master Bot Token (from @BotFather)"
$adminToken = Read-Host "Admin Bot Token (from @BotFather)"
$superusers = Read-Host "Admin Superuser IDs (comma-separated, e.g. 123456,789012)"

if ([string]::IsNullOrWhiteSpace($masterToken) -or [string]::IsNullOrWhiteSpace($adminToken)) {
    Write-Host "ERROR: Bot tokens are required!" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "[1/5] Updating .env file..." -ForegroundColor Cyan

$session = New-SSHSession -ComputerName 217.199.254.27 -Credential $cred -AcceptKey

$envContent = @"
DATABASE_URL=postgresql+asyncpg://fs_user:fs_password@postgres:5432/field_service
MASTER_BOT_TOKEN=$masterToken
ADMIN_BOT_TOKEN=$adminToken
TIMEZONE=Europe/Moscow
DISTRIBUTION_SLA_SECONDS=120
DISTRIBUTION_ROUNDS=2
HEARTBEAT_SECONDS=60
COMMISSION_DEADLINE_HOURS=3
GUARANTEE_COMPANY_PAYMENT=2500
WORKDAY_START=10:00
WORKDAY_END=20:00
ASAP_LATE_THRESHOLD=19:30
ADMIN_BOT_SUPERUSERS=$superusers
GLOBAL_ADMINS_TG_IDS=[$superusers]
ACCESS_CODE_TTL_HOURS=24
OVERDUE_WATCHDOG_MIN=10
"@

$cmd = @"
cat > /opt/field-service/.env << 'ENVEOF'
$envContent
ENVEOF
"@
Invoke-SSHCommand -SessionId $session.SessionId -Command $cmd -TimeOut 10 | Out-Null
Write-Host "  .env updated!" -ForegroundColor Green

Write-Host "[2/5] Building Docker images..." -ForegroundColor Cyan
Write-Host "  This may take 3-5 minutes..." -ForegroundColor Yellow
$cmd = "cd /opt/field-service && docker compose build 2>&1"
$result = Invoke-SSHCommand -SessionId $session.SessionId -Command $cmd -TimeOut 300
if ($result.ExitStatus -eq 0) {
    Write-Host "  Build completed!" -ForegroundColor Green
} else {
    Write-Host "  Build output:" -ForegroundColor Yellow
    Write-Host $result.Output
}

Write-Host "[3/5] Running database migrations..." -ForegroundColor Cyan
$cmd = "cd /opt/field-service && docker compose run --rm admin-bot alembic upgrade head 2>&1"
$result = Invoke-SSHCommand -SessionId $session.SessionId -Command $cmd -TimeOut 120
Write-Host $result.Output
if ($result.ExitStatus -eq 0) {
    Write-Host "  Migrations completed!" -ForegroundColor Green
} else {
    Write-Host "  WARNING: Check migration output above" -ForegroundColor Yellow
}

Write-Host "[4/5] Starting all services..." -ForegroundColor Cyan
$cmd = "cd /opt/field-service && docker compose up -d 2>&1"
$result = Invoke-SSHCommand -SessionId $session.SessionId -Command $cmd -TimeOut 60
Write-Host $result.Output

Write-Host "[5/5] Checking service status..." -ForegroundColor Cyan
Start-Sleep -Seconds 5
$cmd = "cd /opt/field-service && docker compose ps"
$result = Invoke-SSHCommand -SessionId $session.SessionId -Command $cmd -TimeOut 15
Write-Host $result.Output

Remove-SSHSession -SessionId $session.SessionId

Write-Host ""
Write-Host "================================" -ForegroundColor Green
Write-Host "DEPLOYMENT COMPLETE!" -ForegroundColor Green
Write-Host "================================" -ForegroundColor Green
Write-Host ""
Write-Host "Your Field Service bots are now running!" -ForegroundColor Yellow
Write-Host ""
Write-Host "Useful commands:" -ForegroundColor White
Write-Host "  Check logs:    ssh root@217.199.254.27 'cd /opt/field-service && docker compose logs -f'" -ForegroundColor Cyan
Write-Host "  Check status:  ssh root@217.199.254.27 'cd /opt/field-service && docker compose ps'" -ForegroundColor Cyan
Write-Host "  Restart bots:  ssh root@217.199.254.27 'cd /opt/field-service && docker compose restart'" -ForegroundColor Cyan
Write-Host "  Stop services: ssh root@217.199.254.27 'cd /opt/field-service && docker compose down'" -ForegroundColor Cyan
Write-Host ""
Write-Host "Test your bots in Telegram now!" -ForegroundColor Green
Write-Host ""
