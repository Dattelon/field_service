# Остановить боты на сервере

$SERVER = "217.199.254.27"
$PASSWORD = "owo?8x-YA@vRN*"

Write-Host "Stopping bots on server..." -ForegroundColor Yellow

$pass = ConvertTo-SecureString $PASSWORD -AsPlainText -Force
$cred = New-Object System.Management.Automation.PSCredential("root", $pass)
$s = New-SSHSession -ComputerName $SERVER -Credential $cred -AcceptKey

$result = Invoke-SSHCommand -SessionId $s.SessionId -Command "cd /opt/field-service && docker compose stop admin-bot master-bot"
Write-Host $result.Output

Write-Host "`n✓ Bots stopped on server" -ForegroundColor Green

Remove-SSHSession -SessionId $s.SessionId
