$password = ConvertTo-SecureString "owo?8x-YA@vRN*" -AsPlainText -Force
$credential = New-Object System.Management.Automation.PSCredential ("root", $password)

Write-Host "==================================" -ForegroundColor Green
Write-Host "Field Service Server Setup" -ForegroundColor Green
Write-Host "==================================" -ForegroundColor Green
Write-Host ""

$session = New-SSHSession -ComputerName 217.199.254.27 -Credential $credential -AcceptKey

if (-not $session) {
    Write-Host "ERROR: Cannot connect to server!" -ForegroundColor Red
    exit 1
}

Write-Host "[CHECK] Checking installed software..." -ForegroundColor Cyan

# Check Docker
$docker = Invoke-SSHCommand -SessionId $session.SessionId -Command "docker --version 2>&1"
if ($docker.Output -match "Docker version") {
    Write-Host "  Docker: Installed ($($docker.Output.Trim()))" -ForegroundColor Green
} else {
    Write-Host "  Docker: Not installed" -ForegroundColor Yellow
}

# Check Docker Compose
$compose = Invoke-SSHCommand -SessionId $session.SessionId -Command "docker compose version 2>&1"
if ($compose.Output -match "Docker Compose version") {
    Write-Host "  Docker Compose: Installed ($($compose.Output.Trim()))" -ForegroundColor Green
} else {
    Write-Host "  Docker Compose: Not installed" -ForegroundColor Yellow
}

# Check Git
$git = Invoke-SSHCommand -SessionId $session.SessionId -Command "git --version 2>&1"
if ($git.Output -match "git version") {
    Write-Host "  Git: Installed ($($git.Output.Trim()))" -ForegroundColor Green
} else {
    Write-Host "  Git: Not installed" -ForegroundColor Yellow
}

# Check project directory
$projDir = Invoke-SSHCommand -SessionId $session.SessionId -Command "[ -d /opt/field-service ] && echo 'exists' || echo 'not exists'"
if ($projDir.Output.Trim() -eq "exists") {
    Write-Host "  /opt/field-service: Exists" -ForegroundColor Green
} else {
    Write-Host "  /opt/field-service: Not exists" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "[INSTALL] Starting installation..." -ForegroundColor Cyan
Write-Host "This will take 3-5 minutes..." -ForegroundColor Yellow
Write-Host ""

# Upload and execute setup script
Write-Host "Uploading setup script..." -ForegroundColor White
$setupScript = Get-Content "C:\ProjectF\remote_setup.sh" -Raw
$stream = New-SSHShellStream -SessionId $session.SessionId

$stream.WriteLine("cat > /tmp/setup.sh << 'EOFSCRIPT'")
$stream.WriteLine($setupScript)
$stream.WriteLine("EOFSCRIPT")
$stream.WriteLine("chmod +x /tmp/setup.sh")
$stream.WriteLine("bash /tmp/setup.sh 2>&1")

Start-Sleep -Seconds 2

# Read output
$timeout = 300 # 5 minutes
$elapsed = 0
$output = ""

while ($elapsed -lt $timeout) {
    if ($stream.DataAvailable) {
        $output += $stream.Read()
        Write-Host $stream.Read() -NoNewline
    }
    
    if ($output -match "Setup completed at:") {
        Write-Host "`nSetup script completed!" -ForegroundColor Green
        break
    }
    
    Start-Sleep -Seconds 2
    $elapsed += 2
}

$stream.Close()

Write-Host ""
Write-Host "[UPLOAD] Uploading project files..." -ForegroundColor Cyan
Write-Host "This may take 2-3 minutes..." -ForegroundColor Yellow

# Use SCP to upload project
$sftp = New-SFTPSession -ComputerName 217.199.254.27 -Credential $credential -AcceptKey

if ($sftp) {
    # Create remote directory
    Invoke-SSHCommand -SessionId $session.SessionId -Command "mkdir -p /opt/field-service"
    
    # Upload files
    $localPath = "C:\ProjectF\field-service"
    
    if (Test-Path $localPath) {
        Write-Host "Uploading from: $localPath" -ForegroundColor White
        
        # Upload directory recursively
        Set-SFTPItem -SessionId $sftp.SessionId -Path $localPath -Destination "/opt/" -Force
        
        Write-Host "Project files uploaded!" -ForegroundColor Green
    } else {
        Write-Host "ERROR: Project directory not found: $localPath" -ForegroundColor Red
    }
    
    Remove-SFTPSession -SessionId $sftp.SessionId
} else {
    Write-Host "ERROR: Cannot create SFTP session!" -ForegroundColor Red
}

# Cleanup
Remove-SSHSession -SessionId $session.SessionId

Write-Host ""
Write-Host "==================================" -ForegroundColor Green
Write-Host "SERVER SETUP COMPLETE!" -ForegroundColor Green
Write-Host "==================================" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host ""
Write-Host "1. SSH to server:" -ForegroundColor White
Write-Host "   ssh root@217.199.254.27" -ForegroundColor Cyan
Write-Host ""
Write-Host "2. Edit .env file:" -ForegroundColor White
Write-Host "   cd /opt/field-service" -ForegroundColor Cyan
Write-Host "   nano .env" -ForegroundColor Cyan
Write-Host "   (Update bot tokens and admin IDs)" -ForegroundColor Gray
Write-Host ""
Write-Host "3. Build and run:" -ForegroundColor White
Write-Host "   docker compose build" -ForegroundColor Cyan
Write-Host "   docker compose run --rm admin-bot alembic upgrade head" -ForegroundColor Cyan
Write-Host "   docker compose up -d" -ForegroundColor Cyan
Write-Host ""
Write-Host "4. Check logs:" -ForegroundColor White
Write-Host "   docker compose logs -f" -ForegroundColor Cyan
Write-Host ""
