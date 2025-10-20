$password = "owo?8x-YA@vRN*"
$securePassword = ConvertTo-SecureString $password -AsPlainText -Force
$credential = New-Object System.Management.Automation.PSCredential("root", $securePassword)
$session = New-SSHSession -ComputerName 217.199.254.27 -Credential $credential -AcceptKey

Write-Host "Stopping containers..."
Invoke-SSHCommand -SessionId $session.SessionId -Command "cd /opt/field-service && docker compose down" -TimeOut 30 | Select-Object -ExpandProperty Output

Write-Host "Building images..."
Invoke-SSHCommand -SessionId $session.SessionId -Command "cd /opt/field-service && docker compose build --no-cache" -TimeOut 600 | Select-Object -ExpandProperty Output

Write-Host "Starting containers..."
Invoke-SSHCommand -SessionId $session.SessionId -Command "cd /opt/field-service && docker compose up -d" -TimeOut 60 | Select-Object -ExpandProperty Output

Write-Host "Checking status..."
Invoke-SSHCommand -SessionId $session.SessionId -Command "cd /opt/field-service && docker compose ps" -TimeOut 10 | Select-Object -ExpandProperty Output

Remove-SSHSession -SessionId $session.SessionId
