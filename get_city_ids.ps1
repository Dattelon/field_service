# Get city IDs and names from server
$SERVER = "217.199.254.27"
$PASSWORD = "owo?8x-YA@vRN*"

$pass = ConvertTo-SecureString $PASSWORD -AsPlainText -Force
$cred = New-Object System.Management.Automation.PSCredential("root", $pass)
$s = New-SSHSession -ComputerName $SERVER -Credential $cred -AcceptKey

Write-Host "=== CITIES ON SERVER ===" -ForegroundColor Cyan
$query = "SELECT id, name FROM cities ORDER BY id;"

$r = Invoke-SSHCommand -SessionId $s.SessionId -Command "docker exec field-service-postgres-1 psql -U fs_user -d field_service -t -A -F'|' -c `"$query`""
$lines = $r.Output -split "`n"
foreach ($line in $lines) {
    if ($line.Trim()) {
        Write-Host $line
    }
}

Remove-SSHSession -SessionId $s.SessionId
