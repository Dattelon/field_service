# Upload files directly to Docker container
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

Write-Host "=== UPLOADING TO SERVER /tmp ===" -ForegroundColor Cyan

foreach ($file in $FILES) {
    $localPath = "C:\ProjectF\field-service\$file"
    $fileName = Split-Path $file -Leaf
    
    Write-Host "Uploading $fileName..." -ForegroundColor Yellow
    Set-SCPItem -ComputerName $SERVER -Credential $cred -Path $localPath -Destination "/tmp/$fileName" -AcceptKey -Force
}

Write-Host "`n=== COPYING TO DOCKER CONTAINERS ===" -ForegroundColor Cyan
$s = New-SSHSession -ComputerName $SERVER -Credential $cred -AcceptKey

foreach ($file in $FILES) {
    $fileName = Split-Path $file -Leaf
    $targetPath = "/app/$file"
    
    Write-Host "Copying $fileName to master-bot..." -ForegroundColor Gray
    $r = Invoke-SSHCommand -SessionId $s.SessionId -Command "docker cp /tmp/$fileName field-service-master-bot-1:$targetPath"
    if ($r.ExitStatus -eq 0) { Write-Host "  OK master-bot" -ForegroundColor Green } else { Write-Host "  ERROR: $($r.Error)" -ForegroundColor Red }
    
    Write-Host "Copying $fileName to admin-bot..." -ForegroundColor Gray
    $r2 = Invoke-SSHCommand -SessionId $s.SessionId -Command "docker cp /tmp/$fileName field-service-admin-bot-1:$targetPath"
    if ($r2.ExitStatus -eq 0) { Write-Host "  OK admin-bot" -ForegroundColor Green } else { Write-Host "  ERROR: $($r2.Error)" -ForegroundColor Red }
}

Write-Host "`n=== VERIFYING IN MASTER-BOT ===" -ForegroundColor Cyan
$r = Invoke-SSHCommand -SessionId $s.SessionId -Command "docker exec field-service-master-bot-1 grep 'shift_break' /app/field_service/bots/master_bot/texts.py | head -2"
Write-Host $r.Output

Write-Host "`n=== RESTARTING BOTS ===" -ForegroundColor Cyan
$r = Invoke-SSHCommand -SessionId $s.SessionId -Command "cd /opt/field-service && docker-compose restart master-bot admin-bot"
Write-Host $r.Output

Remove-SSHSession -SessionId $s.SessionId | Out-Null
Write-Host "`n=== DONE ===" -ForegroundColor Cyan
