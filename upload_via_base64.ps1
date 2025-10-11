# Upload files using base64 encoding
$SERVER = "217.199.254.27"
$PASSWORD = "owo?8x-YA@vRN*"

$FILES = @{
    "texts.py" = "field_service/bots/master_bot/texts.py"
    "keyboards.py" = "field_service/bots/master_bot/keyboards.py"  
    "orders.py" = "field_service/bots/master_bot/handlers/orders.py"
    "breadcrumbs.py" = "field_service/bots/common/breadcrumbs.py"
}

$pass = ConvertTo-SecureString $PASSWORD -AsPlainText -Force
$cred = New-Object System.Management.Automation.PSCredential("root", $pass)
$s = New-SSHSession -ComputerName $SERVER -Credential $cred -AcceptKey

Write-Host "=== UPLOADING FILES USING BASE64 ===" -ForegroundColor Cyan

foreach ($fileName in $FILES.Keys) {
    $localPath = "C:\ProjectF\field-service\$($FILES[$fileName])"
    $remotePath = "/opt/field-service/$($FILES[$fileName])"
    
    Write-Host "`nProcessing: $fileName" -ForegroundColor Yellow
    
    # Read file as bytes and convert to base64
    $bytes = [System.IO.File]::ReadAllBytes($localPath)
    $base64 = [Convert]::ToBase64String($bytes)
    
    # Upload base64 to server and decode
    $cmd = "echo '$base64' | base64 -d > $remotePath"
    $r = Invoke-SSHCommand -SessionId $s.SessionId -Command $cmd -TimeOut 30
    
    if ($r.ExitStatus -eq 0) {
        Write-Host "  OK: $remotePath" -ForegroundColor Green
    } else {
        Write-Host "  ERROR: $($r.Error)" -ForegroundColor Red
    }
}

Write-Host "`n=== VERIFYING ===" -ForegroundColor Cyan
$r = Invoke-SSHCommand -SessionId $s.SessionId -Command "cd /opt/field-service; grep 'shift_break' field_service/bots/master_bot/texts.py | head -2"
Write-Host "texts.py content:"
Write-Host $r.Output

$r2 = Invoke-SSHCommand -SessionId $s.SessionId -Command "cd /opt/field-service; file -i field_service/bots/master_bot/texts.py"
Write-Host "`nFile encoding:"
Write-Host $r2.Output

Remove-SSHSession -SessionId $s.SessionId | Out-Null
Write-Host "`n=== DONE ===" -ForegroundColor Cyan
