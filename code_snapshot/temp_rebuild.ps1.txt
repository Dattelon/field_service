$password = "owo?8x-YA@vRN*"
$securePassword = ConvertTo-SecureString $password -AsPlainText -Force
$credential = New-Object System.Management.Automation.PSCredential("root", $securePassword)
$session = New-SSHSession -ComputerName 217.199.254.27 -Credential $credential -AcceptKey

Write-Output "=== Остановка контейнеров ==="
$result1 = Invoke-SSHCommand -SessionId $session.SessionId -Command "cd /opt/field-service && docker compose down"
Write-Output $result1.Output

Write-Output "`n=== Пересборка образов ==="
$result2 = Invoke-SSHCommand -SessionId $session.SessionId -Command "cd /opt/field-service && docker compose build --no-cache"
Write-Output $result2.Output

Write-Output "`n=== Запуск контейнеров ==="
$result3 = Invoke-SSHCommand -SessionId $session.SessionId -Command "cd /opt/field-service && docker compose up -d"
Write-Output $result3.Output

Write-Output "`n=== Проверка статуса ==="
$result4 = Invoke-SSHCommand -SessionId $session.SessionId -Command "cd /opt/field-service && docker compose ps"
Write-Output $result4.Output

Remove-SSHSession -SessionId $session.SessionId
