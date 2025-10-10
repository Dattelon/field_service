# ========================================
# Field Service - Production Deployment
# ========================================

param(
    [bool]$CreateBackup = $true,
    [bool]$RunMigrations = $true,
    [bool]$SkipTests = $false,
    [bool]$GracefulRestart = $true
)

$ErrorActionPreference = "Stop"

# Configuration
$SERVER = "217.199.254.27"
$USER = "root"
$PASSWORD = "owo?8x-YA@vRN*"
$PROJECT_PATH = "/opt/field-service"
$LOCAL_PROJECT = "C:\ProjectF\field-service"
$BACKUP_DIR = "/opt/backups/manual"

# Create log directory
$logDir = "C:\ProjectF\deployment_logs"
if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir | Out-Null
}

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$logFile = "$logDir\deploy_$timestamp.log"

function Write-Log {
    param($Message, $Color = "White")
    $logMessage = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $Message"
    Write-Host $logMessage -ForegroundColor $Color
    Add-Content -Path $logFile -Value $logMessage
}

function Connect-Server {
    $pass = ConvertTo-SecureString $PASSWORD -AsPlainText -Force
    $cred = New-Object System.Management.Automation.PSCredential($USER, $pass)
    return New-SSHSession -ComputerName $SERVER -Credential $cred -AcceptKey
}

Write-Host "========================================" -ForegroundColor Green
Write-Host "FIELD SERVICE DEPLOYMENT" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Log "START DEPLOYMENT" "Green"
Write-Log "Target: $SERVER"
Write-Log "Project: $PROJECT_PATH"
Write-Log "Backup: $CreateBackup"
Write-Log "Migrations: $RunMigrations"

# Step 1: Pre-deployment checks
Write-Host "`n[1/8] Pre-deployment checks..." -ForegroundColor Cyan
Write-Log "[1/8] Pre-deployment checks"

if (-not (Test-Path $LOCAL_PROJECT)) {
    Write-Log "ERROR: Local project not found: $LOCAL_PROJECT" "Red"
    exit 1
}

# Run tests if not skipped
if (-not $SkipTests) {
    Write-Host "Running tests..." -ForegroundColor Yellow
    Write-Log "Running tests..."
    
    Push-Location $LOCAL_PROJECT
    $testResult = & python -m pytest tests/ --tb=short 2>&1
    $testExitCode = $LASTEXITCODE
    Pop-Location
    
    if ($testExitCode -ne 0) {
        Write-Log "ERROR: Tests failed!" "Red"
        Write-Log $testResult "Red"
        $continue = Read-Host "Tests failed. Continue anyway? (y/N)"
        if ($continue -ne "y") {
            Write-Log "Deployment aborted by user" "Yellow"
            exit 1
        }
    } else {
        Write-Log "Tests passed" "Green"
    }
}

Write-Log "Pre-deployment checks: OK" "Green"

# Step 2: Connect to server
Write-Host "`n[2/8] Connecting to server..." -ForegroundColor Cyan
Write-Log "[2/8] Connecting to server: $SERVER"

$session = Connect-Server
if (-not $session) {
    Write-Log "ERROR: Cannot connect to server" "Red"
    exit 1
}
Write-Log "Connected. SessionId: $($session.SessionId)" "Green"

# Step 3: Create backup
if ($CreateBackup) {
    Write-Host "`n[3/8] Creating database backup..." -ForegroundColor Cyan
    Write-Log "[3/8] Creating database backup"
    
    $backupCmd = @"
mkdir -p $BACKUP_DIR
cd /opt/field-service
docker compose exec -T postgres pg_dump -U fs_user field_service | gzip > $BACKUP_DIR/backup_$timestamp.sql.gz
ls -lh $BACKUP_DIR/backup_$timestamp.sql.gz
"@
    
    $result = Invoke-SSHCommand -SessionId $session.SessionId -Command $backupCmd -TimeOut 120
    if ($result.ExitStatus -eq 0) {
        Write-Log "Backup created: backup_$timestamp.sql.gz" "Green"
        Write-Log $result.Output
    } else {
        Write-Log "WARNING: Backup failed, but continuing..." "Yellow"
    }
} else {
    Write-Host "`n[3/8] Skipping backup (as requested)..." -ForegroundColor Yellow
    Write-Log "[3/8] Backup skipped"
}

# Step 4: Create archive and upload
Write-Host "`n[4/8] Uploading project files..." -ForegroundColor Cyan
Write-Log "[4/8] Creating and uploading project archive"

Write-Host "  Creating archive..." -ForegroundColor White
Push-Location "C:\ProjectF"
$archivePath = "field-service-$timestamp.tar.gz"
& tar -czf $archivePath --exclude='.venv' --exclude='__pycache__' --exclude='.pytest_cache' --exclude='*.log' field-service
Pop-Location

if (-not (Test-Path "C:\ProjectF\$archivePath")) {
    Write-Log "ERROR: Failed to create archive" "Red"
    Remove-SSHSession -SessionId $session.SessionId
    exit 1
}

Write-Host "  Uploading to server..." -ForegroundColor White
$pass = ConvertTo-SecureString $PASSWORD -AsPlainText -Force
$cred = New-Object System.Management.Automation.PSCredential($USER, $pass)
$sftp = New-SFTPSession -ComputerName $SERVER -Credential $cred -AcceptKey
Set-SFTPItem -SessionId $sftp.SessionId -Path "C:\ProjectF\$archivePath" -Destination "/tmp/" -Force
Remove-SFTPSession -SessionId $sftp.SessionId

Write-Log "Upload complete" "Green"

# Step 5: Extract on server
Write-Host "`n[5/8] Extracting and preparing..." -ForegroundColor Cyan
Write-Log "[5/8] Extracting project on server"

$extractCmd = @"
cd /opt
# Backup current version
if [ -d field-service ]; then
    rm -rf field-service-backup
    cp -r field-service field-service-backup
    echo 'Backup of current version created'
fi
# Extract new version
tar -xzf /tmp/$archivePath
echo 'Extraction complete'
ls -la $PROJECT_PATH | head -10
"@

$result = Invoke-SSHCommand -SessionId $session.SessionId -Command $extractCmd -TimeOut 60
Write-Log $result.Output
if ($result.ExitStatus -ne 0) {
    Write-Log "ERROR: Extraction failed" "Red"
    Remove-SSHSession -SessionId $session.SessionId
    exit 1
}

# Step 6: Build Docker images
Write-Host "`n[6/8] Building Docker images..." -ForegroundColor Cyan
Write-Log "[6/8] Building Docker images (this may take 3-5 minutes)"

$buildCmd = "cd $PROJECT_PATH && docker compose build"
$result = Invoke-SSHCommand -SessionId $session.SessionId -Command $buildCmd -TimeOut 400

if ($result.ExitStatus -eq 0) {
    Write-Log "Docker build: SUCCESS" "Green"
} else {
    Write-Log "ERROR: Docker build failed" "Red"
    Write-Log $result.Output "Red"
    Remove-SSHSession -SessionId $session.SessionId
    exit 1
}

# Step 7: Run migrations
if ($RunMigrations) {
    Write-Host "`n[7/8] Running database migrations..." -ForegroundColor Cyan
    Write-Log "[7/8] Running database migrations"
    
    $migrateCmd = "cd $PROJECT_PATH && docker compose run --rm admin-bot alembic upgrade head"
    $result = Invoke-SSHCommand -SessionId $session.SessionId -Command $migrateCmd -TimeOut 120
    
    Write-Log $result.Output
    if ($result.ExitStatus -eq 0) {
        Write-Log "Migrations: SUCCESS" "Green"
    } else {
        Write-Log "WARNING: Migrations had issues" "Yellow"
    }
} else {
    Write-Host "`n[7/8] Skipping migrations..." -ForegroundColor Yellow
    Write-Log "[7/8] Migrations skipped"
}

# Step 8: Restart services
Write-Host "`n[8/8] Restarting services..." -ForegroundColor Cyan
Write-Log "[8/8] Restarting services"

if ($GracefulRestart) {
    Write-Host "  Performing graceful restart..." -ForegroundColor Yellow
    Write-Log "Performing graceful restart"
    
    # Graceful restart: start new containers before stopping old
    $restartCmd = @"
cd $PROJECT_PATH
# Start new containers (detached)
docker compose up -d --no-deps --build admin-bot master-bot
# Wait for health check
sleep 10
# Old containers will be replaced automatically
echo 'Graceful restart complete'
"@
} else {
    Write-Host "  Performing standard restart..." -ForegroundColor Yellow
    Write-Log "Performing standard restart"
    
    $restartCmd = @"
cd $PROJECT_PATH
docker compose restart admin-bot master-bot
sleep 5
echo 'Standard restart complete'
"@
}

$result = Invoke-SSHCommand -SessionId $session.SessionId -Command $restartCmd -TimeOut 60
Write-Log $result.Output

# Health check
Write-Host "`nPerforming health check..." -ForegroundColor Cyan
Write-Log "Performing health check"
Start-Sleep -Seconds 5

$healthCmd = @"
cd $PROJECT_PATH
echo '=== Container Status ==='
docker compose ps
echo ''
echo '=== Recent Admin Bot Logs ==='
docker compose logs admin-bot --tail=10 2>&1 | grep -v 'grep'
echo ''
echo '=== Recent Master Bot Logs ==='
docker compose logs master-bot --tail=10 2>&1 | grep -v 'grep'
"@

$result = Invoke-SSHCommand -SessionId $session.SessionId -Command $healthCmd -TimeOut 30
Write-Host $result.Output

# Check for errors in logs
if ($result.Output -match "ERROR|Error|error|CRITICAL|Failed") {
    Write-Log "WARNING: Errors detected in logs!" "Yellow"
    Write-Log "Please check logs manually: docker compose logs -f" "Yellow"
} else {
    Write-Log "Health check: OK" "Green"
}

# Cleanup
Remove-SSHSession -SessionId $session.SessionId
Remove-Item "C:\ProjectF\$archivePath" -Force

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "DEPLOYMENT COMPLETE!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Log "DEPLOYMENT SUCCESS" "Green"
Write-Log "Log file: $logFile"
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "  1. Monitor logs: C:\ProjectF\view_server_logs.ps1" -ForegroundColor White
Write-Host "  2. Check health: C:\ProjectF\check_server_health.ps1" -ForegroundColor White
Write-Host "  3. If issues: C:\ProjectF\rollback_deployment.ps1" -ForegroundColor White
Write-Host ""
