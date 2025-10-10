# Field Service - Rollback Deployment

$SERVER = "217.199.254.27"
$PASSWORD = "owo?8x-YA@vRN*"

Write-Host "========================================" -ForegroundColor Red
Write-Host "ROLLBACK DEPLOYMENT" -ForegroundColor Red
Write-Host "========================================" -ForegroundColor Red
Write-Host ""
Write-Host "WARNING: This will restore the previous version!" -ForegroundColor Yellow
$confirm = Read-Host "Continue? (yes/no)"

if ($confirm -ne "yes") {
    Write-Host "Rollback cancelled" -ForegroundColor Yellow
    exit 0
}

$pass = ConvertTo-SecureString $PASSWORD -AsPlainText -Force
$cred = New-Object System.Management.Automation.PSCredential("root", $pass)
$s = New-SSHSession -ComputerName $SERVER -Credential $cred -AcceptKey

Write-Host "`n[1/4] Checking backup..." -ForegroundColor Cyan
$check = Invoke-SSHCommand -SessionId $s.SessionId -Command "[ -d /opt/field-service-backup ] && echo 'exists' || echo 'not found'"
if ($check.Output.Trim() -ne "exists") {
    Write-Host "ERROR: No backup found! Cannot rollback." -ForegroundColor Red
    Remove-SSHSession -SessionId $s.SessionId
    exit 1
}
Write-Host "Backup found" -ForegroundColor Green

Write-Host "`n[2/4] Stopping services..." -ForegroundColor Cyan
Invoke-SSHCommand -SessionId $s.SessionId -Command "cd /opt/field-service && docker compose down" | Out-Null
Write-Host "Services stopped" -ForegroundColor Green

Write-Host "`n[3/4] Restoring previous version..." -ForegroundColor Cyan
$restore = @"
cd /opt
rm -rf field-service-failed
mv field-service field-service-failed
mv field-service-backup field-service
echo 'Previous version restored'
"@
Invoke-SSHCommand -SessionId $s.SessionId -Command $restore | Out-Null
Write-Host "Previous version restored" -ForegroundColor Green

Write-Host "`n[4/4] Starting services..." -ForegroundColor Cyan
$start = @"
cd /opt/field-service
docker compose up -d
sleep 5
docker compose ps
"@
$result = Invoke-SSHCommand -SessionId $s.SessionId -Command $start
Write-Host $result.Output

Remove-SSHSession -SessionId $s.SessionId

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "ROLLBACK COMPLETE" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "  1. Check logs: .\view_server_logs.ps1" -ForegroundColor White
Write-Host "  2. Verify health: .\check_server_health.ps1" -ForegroundColor White
Write-Host ""
Write-Host "Failed version saved in: /opt/field-service-failed" -ForegroundColor Gray
Write-Host ""
