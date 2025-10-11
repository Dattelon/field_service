# Check which cities have districts on server
$SERVER = "217.199.254.27"
$PASSWORD = "owo?8x-YA@vRN*"

$pass = ConvertTo-SecureString $PASSWORD -AsPlainText -Force
$cred = New-Object System.Management.Automation.PSCredential("root", $pass)
$s = New-SSHSession -ComputerName $SERVER -Credential $cred -AcceptKey

Write-Host "=== Cities with/without districts ===" -ForegroundColor Cyan
$query = @"
SELECT 
    c.id,
    c.name,
    COUNT(d.id) as district_count
FROM cities c
LEFT JOIN districts d ON d.city_id = c.id
GROUP BY c.id, c.name
ORDER BY c.id;
"@

$r = Invoke-SSHCommand -SessionId $s.SessionId -Command "docker exec field-service-postgres-1 psql -U fs_user -d field_service -c `"$query`""
Write-Host $r.Output

Remove-SSHSession -SessionId $s.SessionId
