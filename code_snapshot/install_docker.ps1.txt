$password = ConvertTo-SecureString "owo?8x-YA@vRN*" -AsPlainText -Force
$cred = New-Object System.Management.Automation.PSCredential ("root", $password)

Write-Host "================================" -ForegroundColor Green
Write-Host "Installing Docker on Server" -ForegroundColor Green
Write-Host "================================" -ForegroundColor Green

$session = New-SSHSession -ComputerName 217.199.254.27 -Credential $cred -AcceptKey

if (-not $session) {
    Write-Host "ERROR: Cannot connect!" -ForegroundColor Red
    exit 1
}

Write-Host "`n[1/7] Updating system..." -ForegroundColor Cyan
$cmd = @"
apt-get update -y && apt-get upgrade -y
"@
Invoke-SSHCommand -SessionId $session.SessionId -Command $cmd -TimeOut 120 | Out-Null

Write-Host "[2/7] Installing prerequisites..." -ForegroundColor Cyan
$cmd = @"
apt-get install -y ca-certificates curl gnupg lsb-release
"@
Invoke-SSHCommand -SessionId $session.SessionId -Command $cmd -TimeOut 60 | Out-Null

Write-Host "[3/7] Adding Docker GPG key..." -ForegroundColor Cyan
$cmd = @"
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg
"@
Invoke-SSHCommand -SessionId $session.SessionId -Command $cmd -TimeOut 30 | Out-Null

Write-Host "[4/7] Adding Docker repository..." -ForegroundColor Cyan
$cmd = @"
echo "deb [arch=`$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu `$(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null
apt-get update -y
"@
Invoke-SSHCommand -SessionId $session.SessionId -Command $cmd -TimeOut 60 | Out-Null

Write-Host "[5/7] Installing Docker..." -ForegroundColor Cyan
$cmd = @"
DEBIAN_FRONTEND=noninteractive apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
"@
$result = Invoke-SSHCommand -SessionId $session.SessionId -Command $cmd -TimeOut 180
Write-Host $result.Output

Write-Host "[6/7] Starting Docker..." -ForegroundColor Cyan
$cmd = @"
systemctl start docker
systemctl enable docker
"@
Invoke-SSHCommand -SessionId $session.SessionId -Command $cmd -TimeOut 30 | Out-Null

Write-Host "[7/7] Verifying installation..." -ForegroundColor Cyan
$result = Invoke-SSHCommand -SessionId $session.SessionId -Command "docker --version && docker compose version"
Write-Host $result.Output -ForegroundColor Green

Write-Host "`n[SETUP] Configuring project..." -ForegroundColor Cyan

# Create docker-compose.yml if missing
$cmd = @"
cd /opt/field-service
if [ ! -f docker-compose.yml ]; then
  cat > docker-compose.yml << 'EOF'
version: '3.8'
services:
  postgres:
    image: postgres:15-alpine
    container_name: fs_postgres
    environment:
      POSTGRES_DB: field_service
      POSTGRES_USER: fs_user
      POSTGRES_PASSWORD: fs_password
    ports:
      - "5432:5432"
    volumes:
      - fs_pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U fs_user -d field_service"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped

  admin-bot:
    build: .
    command: python -m field_service.bots.admin_bot.main
    env_file: .env
    depends_on:
      - postgres
    restart: unless-stopped

  master-bot:
    build: .
    command: python -m field_service.bots.master_bot.main
    env_file: .env
    depends_on:
      - postgres
    restart: unless-stopped

volumes:
  fs_pgdata:
EOF
fi
echo "docker-compose.yml ready"
"@
Invoke-SSHCommand -SessionId $session.SessionId -Command $cmd -TimeOut 15 | Out-Null

# Create .env if missing
$cmd = @"
cd /opt/field-service
if [ ! -f .env ]; then
  cat > .env << 'EOF'
DATABASE_URL=postgresql+asyncpg://fs_user:fs_password@postgres:5432/field_service
MASTER_BOT_TOKEN=8423680284:AAHXBq-Lmtn5cVwUoxMwhJPOAoCMVGz4688
ADMIN_BOT_TOKEN=7531617746:AAGvHQ0RySGtSSMAYenNdwyenZFkTZA6xbQ
TIMEZONE=Europe/Moscow
DISTRIBUTION_SLA_SECONDS=120
DISTRIBUTION_ROUNDS=2
HEARTBEAT_SECONDS=60
COMMISSION_DEADLINE_HOURS=3
GUARANTEE_COMPANY_PAYMENT=2500
WORKDAY_START=10:00
WORKDAY_END=20:00
ASAP_LATE_THRESHOLD=19:30
ADMIN_BOT_SUPERUSERS=
GLOBAL_ADMINS_TG_IDS=[]
ACCESS_CODE_TTL_HOURS=24
OVERDUE_WATCHDOG_MIN=10
EOF
fi
echo ".env ready"
"@
Invoke-SSHCommand -SessionId $session.SessionId -Command $cmd -TimeOut 15 | Out-Null

Write-Host "[FIREWALL] Configuring firewall..." -ForegroundColor Cyan
$cmd = @"
ufw --force enable
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
ufw status
"@
$result = Invoke-SSHCommand -SessionId $session.SessionId -Command $cmd -TimeOut 30
Write-Host $result.Output

Write-Host "[POSTGRES] Starting PostgreSQL..." -ForegroundColor Cyan
$cmd = @"
cd /opt/field-service
docker compose up -d postgres
sleep 10
docker compose ps
"@
$result = Invoke-SSHCommand -SessionId $session.SessionId -Command $cmd -TimeOut 60
Write-Host $result.Output

Remove-SSHSession -SessionId $session.SessionId

Write-Host "`n================================" -ForegroundColor Green
Write-Host "INSTALLATION COMPLETE!" -ForegroundColor Green
Write-Host "================================" -ForegroundColor Green
Write-Host "`nWhat was installed:" -ForegroundColor Yellow
Write-Host "  Docker & Docker Compose" -ForegroundColor White
Write-Host "  PostgreSQL container (running)" -ForegroundColor White
Write-Host "  Project files in /opt/field-service" -ForegroundColor White
Write-Host "  Firewall configured" -ForegroundColor White

Write-Host "`nNext steps:" -ForegroundColor Yellow
Write-Host "1. Edit .env file with your bot tokens:" -ForegroundColor White
Write-Host "   nano /opt/field-service/.env" -ForegroundColor Cyan
Write-Host ""
Write-Host "2. Build Docker images:" -ForegroundColor White
Write-Host "   cd /opt/field-service" -ForegroundColor Cyan
Write-Host "   docker compose build" -ForegroundColor Cyan
Write-Host ""
Write-Host "3. Run database migrations:" -ForegroundColor White
Write-Host "   docker compose run --rm admin-bot alembic upgrade head" -ForegroundColor Cyan
Write-Host ""
Write-Host "4. Start all services:" -ForegroundColor White
Write-Host "   docker compose up -d" -ForegroundColor Cyan
Write-Host ""
Write-Host "5. Check logs:" -ForegroundColor White
Write-Host "   docker compose logs -f" -ForegroundColor Cyan
Write-Host ""
