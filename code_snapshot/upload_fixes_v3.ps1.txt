# Simple upload using scp
Write-Host "=== Uploading files to server ===" -ForegroundColor Cyan

$files = @(
    "field_service/bots/master_bot/handlers/orders.py",
    "field_service/bots/master_bot/texts.py",
    "field_service/bots/master_bot/keyboards.py",
    "field_service/bots/common/breadcrumbs.py"
)

foreach ($file in $files) {
    $local = "C:\ProjectF\field-service\$file"
    $remote = "root@217.199.254.27:/opt/field-service/$file"
    
    Write-Host "Uploading $file..." -ForegroundColor Yellow
    
    # Using pscp from PuTTY
    $env:PSCP_PASSWORD = "owo?8x-YA@vRN*"
    & pscp -pw "owo?8x-YA@vRN*" -batch $local $remote
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "OK $file" -ForegroundColor Green
    } else {
        Write-Host "ERROR uploading $file" -ForegroundColor Red
    }
}

# Restart master-bot via SSH
Write-Host ""
Write-Host "=== Restarting master-bot ===" -ForegroundColor Cyan
$pass = ConvertTo-SecureString "owo?8x-YA@vRN*" -AsPlainText -Force
$cred = New-Object System.Management.Automation.PSCredential("root", $pass)
$s = New-SSHSession -ComputerName 217.199.254.27 -Credential $cred -AcceptKey

$result = Invoke-SSHCommand -SessionId $s.SessionId -Command "cd /opt/field-service && docker-compose restart master-bot"
Write-Host $result.Output

Start-Sleep -Seconds 5

Write-Host ""
Write-Host "=== Checking status ===" -ForegroundColor Cyan
$result = Invoke-SSHCommand -SessionId $s.SessionId -Command "docker ps | grep master-bot"
Write-Host $result.Output

Remove-SSHSession -SessionId $s.SessionId

Write-Host ""
Write-Host "OK Done!" -ForegroundColor Green
