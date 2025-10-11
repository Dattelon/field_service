# Upload fixed files via /tmp
$SERVER = "217.199.254.27"
$PASSWORD = "owo?8x-YA@vRN*"

$FILES = @(
    @{
        Local = "C:\ProjectF\field-service\field_service\bots\master_bot\texts.py"
        Target = "field_service/bots/master_bot/texts.py"
    },
    @{
        Local = "C:\ProjectF\field-service\field_service\bots\master_bot\keyboards.py"
        Target = "field_service/bots/master_bot/keyboards.py"
    },
    @{
        Local = "C:\ProjectF\field-service\field_service\bots\master_bot\handlers\orders.py"
        Target = "field_service/bots/master_bot/handlers/orders.py"
    },
    @{
        Local = "C:\ProjectF\field-service\field_service\bots\common\breadcrumbs.py"
        Target = "field_service/bots/common/breadcrumbs.py"
    }
)

$pass = ConvertTo-SecureString $PASSWORD -AsPlainText -Force
$cred = New-Object System.Management.Automation.PSCredential("root", $pass)

Write-Host "=== UPLOADING FILES ===" -ForegroundColor Cyan

foreach ($file in $FILES) {
    $fileName = Split-Path $file.Local -Leaf
    Write-Host "Processing: $fileName" -ForegroundColor Yellow
    
    # Upload to /tmp
    Set-SCPItem -ComputerName $SERVER -Credential $cred -Path $file.Local -Destination "/tmp/$fileName" -AcceptKey -Force
    Write-Host "  Uploaded to /tmp/$fileName" -ForegroundColor Gray
}

Write-Host ""
Write-Host "=== MOVING FILES ===" -ForegroundColor Cyan
$s = New-SSHSession -ComputerName $SERVER -Credential $cred -AcceptKey

foreach ($file in $FILES) {
    $fileName = Split-Path $file.Local -Leaf
    $targetPath = $file.Target
    Write-Host "Moving $fileName..." -ForegroundColor Gray
    
    $cmd = "mv /tmp/$fileName /opt/field-service/$targetPath"
    $r = Invoke-SSHCommand -SessionId $s.SessionId -Command $cmd
    
    if ($r.ExitStatus -eq 0) {
        Write-Host "  OK: $targetPath" -ForegroundColor Green
    } else {
        Write-Host "  ERROR: $($r.Error)" -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "=== VERIFYING ===" -ForegroundColor Cyan

$cmd1 = "cd /opt/field-service; file -i field_service/bots/master_bot/texts.py"
$r1 = Invoke-SSHCommand -SessionId $s.SessionId -Command $cmd1
Write-Host $r1.Output

$cmd2 = "cd /opt/field-service; head -50 field_service/bots/master_bot/texts.py | grep -n shift_break"
$r2 = Invoke-SSHCommand -SessionId $s.SessionId -Command $cmd2
Write-Host $r2.Output

Remove-SSHSession -SessionId $s.SessionId | Out-Null
Write-Host ""
Write-Host "=== DONE ===" -ForegroundColor Cyan
