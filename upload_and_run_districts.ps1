# Upload add_all_districts.py to server and run it
$SERVER = "217.199.254.27"
$PASSWORD = "owo?8x-YA@vRN*"
$LOCAL_FILE = "C:\ProjectF\field-service\add_all_districts.py"

$pass = ConvertTo-SecureString $PASSWORD -AsPlainText -Force
$cred = New-Object System.Management.Automation.PSCredential("root", $pass)
$s = New-SSHSession -ComputerName $SERVER -Credential $cred -AcceptKey

Write-Host "=== UPLOADING SCRIPT ===" -ForegroundColor Cyan
Set-SCPItem -ComputerName $SERVER -Credential $cred -Path $LOCAL_FILE -Destination "/tmp/" -AcceptKey

Write-Host "`n=== COPYING TO CONTAINER ===" -ForegroundColor Cyan
$r = Invoke-SSHCommand -SessionId $s.SessionId -Command "docker cp /tmp/add_all_districts.py field-service-admin-bot-1:/app/"
Write-Host $r.Output

Write-Host "`n=== RUNNING SCRIPT ===" -ForegroundColor Cyan
$r = Invoke-SSHCommand -SessionId $s.SessionId -Command "docker exec -i field-service-admin-bot-1 python /app/add_all_districts.py"
Write-Host $r.Output

if ($r.ExitStatus -eq 0) {
    Write-Host "`n✅ SUCCESS!" -ForegroundColor Green
} else {
    Write-Host "`n❌ FAILED!" -ForegroundColor Red
    Write-Host "Error: $($r.Error)" -ForegroundColor Red
}

Remove-SSHSession -SessionId $s.SessionId
