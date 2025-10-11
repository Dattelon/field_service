# Upload using Python on server with base64
$SERVER = "217.199.254.27"
$PASSWORD = "owo?8x-YA@vRN*"

$FILES = @(
    @{Path="field_service/bots/master_bot/texts.py"; Name="texts.py"},
    @{Path="field_service/bots/master_bot/keyboards.py"; Name="keyboards.py"},
    @{Path="field_service/bots/master_bot/handlers/orders.py"; Name="orders.py"},
    @{Path="field_service/bots/common/breadcrumbs.py"; Name="breadcrumbs.py"}
)

$pass = ConvertTo-SecureString $PASSWORD -AsPlainText -Force
$cred = New-Object System.Management.Automation.PSCredential("root", $pass)
$s = New-SSHSession -ComputerName $SERVER -Credential $cred -AcceptKey

Write-Host "=== UPLOADING FILES ===" -ForegroundColor Cyan

foreach ($file in $FILES) {
    $localPath = "C:\ProjectF\field-service\$($file.Path)"
    $serverPath = "/app/$($file.Path)"
    
    Write-Host "`nProcessing $($file.Name)..." -ForegroundColor Yellow
    
    # Read file as base64
    $bytes = [System.IO.File]::ReadAllBytes($localPath)
    $base64 = [Convert]::ToBase64String($bytes)
    
    # Split base64 into chunks (avoid command line length limit)
    $chunkSize = 50000
    $chunks = @()
    for ($i = 0; $i -lt $base64.Length; $i += $chunkSize) {
        $end = [Math]::Min($i + $chunkSize, $base64.Length)
        $chunks += $base64.Substring($i, $end - $i)
    }
    
    Write-Host "  Uploading in $($chunks.Count) chunks..." -ForegroundColor Gray
    
    # Create Python script to write file
    $pythonScript = @"
import base64
data = ''
"@
    
    foreach ($chunk in $chunks) {
        $pythonScript += "`ndata += '$chunk'"
    }
    
    $pythonScript += @"

decoded = base64.b64decode(data)
with open('$serverPath', 'wb') as f:
    f.write(decoded)
print('Written', len(decoded), 'bytes to $serverPath')
"@
    
    # Execute in master-bot container
    $tempScript = "/tmp/upload_$(Get-Random).py"
    $r = Invoke-SSHCommand -SessionId $s.SessionId -Command "cat > $tempScript << 'EOFPYTHON'`n$pythonScript`nEOFPYTHON"
    
    $r2 = Invoke-SSHCommand -SessionId $s.SessionId -Command "docker exec field-service-master-bot-1 python3 $tempScript"
    Write-Host "  master-bot: $($r2.Output)" -ForegroundColor Green
    
    $r3 = Invoke-SSHCommand -SessionId $s.SessionId -Command "docker exec field-service-admin-bot-1 python3 $tempScript"
    Write-Host "  admin-bot: $($r3.Output)" -ForegroundColor Green
    
    Invoke-SSHCommand -SessionId $s.SessionId -Command "rm $tempScript" | Out-Null
}

Write-Host "`n=== VERIFYING ===" -ForegroundColor Cyan
$r = Invoke-SSHCommand -SessionId $s.SessionId -Command "docker exec field-service-master-bot-1 grep -n 'shift_break' /app/field_service/bots/master_bot/texts.py | head -2"
Write-Host $r.Output

Write-Host "`n=== RESTARTING ===" -ForegroundColor Cyan
$r = Invoke-SSHCommand -SessionId $s.SessionId -Command "cd /opt/field-service && docker-compose restart master-bot admin-bot" -TimeOut 30
Write-Host $r.Output

Remove-SSHSession -SessionId $s.SessionId | Out-Null
Write-Host "`n=== DONE ===" -ForegroundColor Cyan
