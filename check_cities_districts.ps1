# Check cities and districts on server (CORRECT USER)
$SERVER = "217.199.254.27"
$PASSWORD = "owo?8x-YA@vRN*"

$pass = ConvertTo-SecureString $PASSWORD -AsPlainText -Force
$cred = New-Object System.Management.Automation.PSCredential("root", $pass)
$s = New-SSHSession -ComputerName $SERVER -Credential $cred -AcceptKey

Write-Host "=== CITIES ===" -ForegroundColor Cyan
$r = Invoke-SSHCommand -SessionId $s.SessionId -Command "docker exec field-service-postgres-1 psql -U fs_user -d field_service -c 'SELECT COUNT(*) FROM cities;'"
Write-Host $r.Output

Write-Host "`n=== DISTRICTS ===" -ForegroundColor Cyan
$r = Invoke-SSHCommand -SessionId $s.SessionId -Command "docker exec field-service-postgres-1 psql -U fs_user -d field_service -c 'SELECT COUNT(*) FROM districts;'"
Write-Host $r.Output

Write-Host "`n=== SAMPLE CITIES ===" -ForegroundColor Cyan
$r = Invoke-SSHCommand -SessionId $s.SessionId -Command "docker exec field-service-postgres-1 psql -U fs_user -d field_service -c 'SELECT id, name FROM cities LIMIT 10;'"
Write-Host $r.Output

Write-Host "`n=== SAMPLE DISTRICTS ===" -ForegroundColor Cyan
$r = Invoke-SSHCommand -SessionId $s.SessionId -Command "docker exec field-service-postgres-1 psql -U fs_user -d field_service -c 'SELECT d.id, c.name as city, d.name as district FROM districts d JOIN cities c ON d.city_id = c.id LIMIT 10;'"
Write-Host $r.Output

Remove-SSHSession -SessionId $s.SessionId
