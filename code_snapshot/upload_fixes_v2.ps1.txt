# Upload files via SSH stream
$pass = ConvertTo-SecureString "owo?8x-YA@vRN*" -AsPlainText -Force
$cred = New-Object System.Management.Automation.PSCredential("root", $pass)
$s = New-SSHSession -ComputerName 217.199.254.27 -Credential $cred -AcceptKey

Write-Host "=== Creating backups ===" -ForegroundColor Cyan
$timestamp = Get-Date -Format 'yyyyMMdd_HHmmss'
Invoke-SSHCommand -SessionId $s.SessionId -Command "cd /opt/field-service && tar -czf backup_$timestamp.tar.gz field_service/bots/master_bot/handlers/orders.py field_service/bots/master_bot/texts.py field_service/bots/master_bot/keyboards.py field_service/bots/common/breadcrumbs.py" | Out-Null

Write-Host "=== Uploading files ===" -ForegroundColor Cyan

# Upload orders.py
Write-Host "Uploading orders.py..." -ForegroundColor Yellow
$content = Get-Content "C:\ProjectF\field-service\field_service\bots\master_bot\handlers\orders.py" -Raw -Encoding UTF8
$encoded = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($content))
Invoke-SSHCommand -SessionId $s.SessionId -Command "echo '$encoded' | base64 -d > /opt/field-service/field_service/bots/master_bot/handlers/orders.py" | Out-Null
Write-Host "OK orders.py" -ForegroundColor Green

# Upload texts.py
Write-Host "Uploading texts.py..." -ForegroundColor Yellow
$content = Get-Content "C:\ProjectF\field-service\field_service\bots\master_bot\texts.py" -Raw -Encoding UTF8
$encoded = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($content))
Invoke-SSHCommand -SessionId $s.SessionId -Command "echo '$encoded' | base64 -d > /opt/field-service/field_service/bots/master_bot/texts.py" | Out-Null
Write-Host "OK texts.py" -ForegroundColor Green

# Upload keyboards.py
Write-Host "Uploading keyboards.py..." -ForegroundColor Yellow
$content = Get-Content "C:\ProjectF\field-service\field_service\bots\master_bot\keyboards.py" -Raw -Encoding UTF8
$encoded = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($content))
Invoke-SSHCommand -SessionId $s.SessionId -Command "echo '$encoded' | base64 -d > /opt/field-service/field_service/bots/master_bot/keyboards.py" | Out-Null
Write-Host "OK keyboards.py" -ForegroundColor Green

# Upload breadcrumbs.py
Write-Host "Uploading breadcrumbs.py..." -ForegroundColor Yellow
$content = Get-Content "C:\ProjectF\field-service\field_service\bots\common\breadcrumbs.py" -Raw -Encoding UTF8
$encoded = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($content))
Invoke-SSHCommand -SessionId $s.SessionId -Command "echo '$encoded' | base64 -d > /opt/field-service/field_service/bots/common/breadcrumbs.py" | Out-Null
Write-Host "OK breadcrumbs.py" -ForegroundColor Green

Write-Host ""
Write-Host "=== Restarting master-bot ===" -ForegroundColor Cyan
$result = Invoke-SSHCommand -SessionId $s.SessionId -Command "cd /opt/field-service && docker-compose restart master-bot"
Write-Host $result.Output

Write-Host ""
Write-Host "=== Checking status (wait 5s) ===" -ForegroundColor Cyan
Start-Sleep -Seconds 5
$result = Invoke-SSHCommand -SessionId $s.SessionId -Command "docker ps | grep master-bot"
Write-Host $result.Output

Write-Host ""
Write-Host "=== Checking logs ===" -ForegroundColor Cyan
$result = Invoke-SSHCommand -SessionId $s.SessionId -Command "docker logs field-service-master-bot-1 --tail 20"
Write-Host $result.Output

Remove-SSHSession -SessionId $s.SessionId
Write-Host ""
Write-Host "OK Done!" -ForegroundColor Green
