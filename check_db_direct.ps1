# Direct check
$SERVER = "217.199.254.27"
$PASSWORD = "owo?8x-YA@vRN*"

$pass = ConvertTo-SecureString $PASSWORD -AsPlainText -Force
$cred = New-Object System.Management.Automation.PSCredential("root", $pass)
$s = New-SSHSession -ComputerName $SERVER -Credential $cred -AcceptKey

Write-Host "=== FULL RESULT ===" -ForegroundColor Cyan
$r = Invoke-SSHCommand -SessionId $s.SessionId -Command "docker exec field-service-postgres-1 psql -U field_service -d field_service -c 'SELECT COUNT(*) FROM cities;'"
Write-Host "Output: [$($r.Output)]"
Write-Host "ExitStatus: $($r.ExitStatus)"
Write-Host "Error: [$($r.Error)]"

Remove-SSHSession -SessionId $s.SessionId
