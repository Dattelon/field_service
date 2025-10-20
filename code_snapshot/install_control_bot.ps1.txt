# Install Control Bot on Server

$SERVER = "217.199.254.27"
$PASSWORD = "owo?8x-YA@vRN*"

Write-Host "========================================" -ForegroundColor Green
Write-Host "Installing Control Bot on Server" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""

# Connect
$pass = ConvertTo-SecureString $PASSWORD -AsPlainText -Force
$cred = New-Object System.Management.Automation.PSCredential("root", $pass)

# Create archive
Write-Host "[1/4] Creating archive..." -ForegroundColor Cyan
cd C:\ProjectF
tar -czf control-bot.tar.gz control-bot

# Upload
Write-Host "[2/4] Uploading to server..." -ForegroundColor Cyan
$sftp = New-SFTPSession -ComputerName $SERVER -Credential $cred -AcceptKey
Set-SFTPItem -SessionId $sftp.SessionId -Path "C:\ProjectF\control-bot.tar.gz" -Destination "/tmp/" -Force
Remove-SFTPSession -SessionId $sftp.SessionId

# Extract and setup
Write-Host "[3/4] Setting up on server..." -ForegroundColor Cyan
$s = New-SSHSession -ComputerName $SERVER -Credential $cred -AcceptKey

$cmd = @"
cd /opt
tar -xzf /tmp/control-bot.tar.gz
cd control-bot
echo 'Control bot extracted'
ls -la
"@

$result = Invoke-SSHCommand -SessionId $s.SessionId -Command $cmd
Write-Host $result.Output

# Build and start
Write-Host "[4/4] Building and starting..." -ForegroundColor Cyan
$cmd = @"
cd /opt/control-bot
docker compose build
docker compose up -d
docker compose logs --tail=20
"@

$result = Invoke-SSHCommand -SessionId $s.SessionId -Command $cmd -TimeOut 120
Write-Host $result.Output

Remove-SSHSession -SessionId $s.SessionId

# Cleanup
Remove-Item "C:\ProjectF\control-bot.tar.gz" -Force

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "Control Bot Installed!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Check status:" -ForegroundColor Yellow
Write-Host "  ssh root@$SERVER" -ForegroundColor White
Write-Host "  cd /opt/control-bot" -ForegroundColor White
Write-Host "  docker compose ps" -ForegroundColor White
Write-Host "  docker compose logs -f" -ForegroundColor White
Write-Host ""
Write-Host "Test in Telegram:" -ForegroundColor Yellow
Write-Host "  1. Find your bot" -ForegroundColor White
Write-Host "  2. Send /start" -ForegroundColor White
Write-Host "  3. Use buttons" -ForegroundColor White
Write-Host ""
