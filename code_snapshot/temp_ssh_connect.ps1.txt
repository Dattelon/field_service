$password = "owo?8x-YA@vRN*"
$securePassword = ConvertTo-SecureString $password -AsPlainText -Force
$credential = New-Object System.Management.Automation.PSCredential("root", $securePassword)
$session = New-SSHSession -ComputerName 217.199.254.27 -Credential $credential -AcceptKey

# Список контейнеров
$result1 = Invoke-SSHCommand -SessionId $session.SessionId -Command "cd /opt/field-service && docker compose ps"
Write-Output "=== Docker Containers ==="
Write-Output $result1.Output

# Логи мастер-бота (последние 200 строк)
$result2 = Invoke-SSHCommand -SessionId $session.SessionId -Command "cd /opt/field-service && docker compose logs --tail=200 master-bot"
Write-Output "`n=== Master Bot Logs ==="
Write-Output $result2.Output

Remove-SSHSession -SessionId $session.SessionId
