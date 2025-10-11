# Upload files using SFTP
$SERVER = "217.199.254.27"
$PASSWORD = "owo?8x-YA@vRN*"

$FILES = @(
    "field_service/bots/master_bot/texts.py",
    "field_service/bots/master_bot/keyboards.py",
    "field_service/bots/master_bot/handlers/orders.py",
    "field_service/bots/common/breadcrumbs.py"
)

$pass = ConvertTo-SecureString $PASSWORD -AsPlainText -Force
$cred = New-Object System.Management.Automation.PSCredential("root", $pass)

Write-Host "=== CREATING UPLOAD DIR ===" -ForegroundColor Cyan
$s = New-SSHSession -ComputerName $SERVER -Credential $cred -AcceptKey
Invoke-SSHCommand -SessionId $s.SessionId -Command "mkdir -p /root/upload" | Out-Null

Write-Host "=== UPLOADING FILES ===" -ForegroundColor Cyan
$sftp = New-SFTPSession -ComputerName $SERVER -Credential $cred -AcceptKey

foreach ($file in $FILES) {
    $localPath = "C:\ProjectF\field-service\$file"
    $fileName = Split-Path $file -Leaf
    
    Write-Host "Uploading $fileName..." -ForegroundColor Yellow
    Set-SFTPItem -SessionId $sftp.SessionId -Path $localPath -Destination "/root/upload/$fileName" -Force
    Write-Host "  OK" -ForegroundColor Green
}

Remove-SFTPSession -SessionId $sftp.SessionId | Out-Null

Write-Host "`n=== COPYING TO DOCKER ===" -ForegroundColor Cyan

foreach ($file in $FILES) {
    $fileName = Split-Path $file -Leaf
    $targetPath = "/app/$file"
    
    Write-Host "Copying $fileName..." -ForegroundColor Gray
    $r = Invoke-SSHCommand -SessionId $s.SessionId -Command "docker cp /root/upload/$fileName field-service-master-bot-1:$targetPath"
    Write-Host "  master-bot: $($r.ExitStatus)" -ForegroundColor $(if($r.ExitStatus -eq 0){"Green"}else{"Red"})
    
    $r2 = Invoke-SSHCommand -SessionId $s.SessionId -Command "docker cp /root/upload/$fileName field-service-admin-bot-1:$targetPath"
    Write-Host "  admin-bot: $($r2.ExitStatus)" -ForegroundColor $(if($r2.ExitStatus -eq 0){"Green"}else{"Red"})
}

Write-Host "`n=== VERIFYING ===" -ForegroundColor Cyan
$r = Invoke-SSHCommand -SessionId $s.SessionId -Command "docker exec field-service-master-bot-1 python3 -c `"import sys; f=open('/app/field_service/bots/master_bot/texts.py','r',encoding='utf-8'); print([l for l in f if 'shift_break' in l][:2])`""
Write-Host $r.Output

Write-Host "`n=== RESTARTING ===" -ForegroundColor Cyan
$r = Invoke-SSHCommand -SessionId $s.SessionId -Command "cd /opt/field-service && docker-compose restart master-bot admin-bot" -TimeOut 30
Write-Host $r.Output

Remove-SSHSession -SessionId $s.SessionId | Out-Null
Write-Host "`n=== DONE ===" -ForegroundColor Cyan
