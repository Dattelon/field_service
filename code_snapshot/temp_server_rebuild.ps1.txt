$password = "owo?8x-YA@vRN*"
$securePassword = ConvertTo-SecureString $password -AsPlainText -Force
$credential = New-Object System.Management.Automation.PSCredential("root", $securePassword)
$session = New-SSHSession -ComputerName 217.199.254.27 -Credential $credential -AcceptKey

Write-Output "=== Stopping containers ==="
$result1 = Invoke-SSHCommand -SessionId $session.SessionId -Command "cd /opt/field-service && docker compose down" -TimeOut 30
Write-Output $result1.Output

Write-Output "`n=== Building images (no cache) ==="
$result2 = Invoke-SSHCommand -SessionId $session.SessionId -Command "cd /opt/field-service && docker compose build --no-cache" -TimeOut 300
Write-Output $result2.Output

Write-Output "`n=== Starting containers ==="
$result3 = Invoke-SSHCommand -SessionId $session.SessionId -Command "cd /opt/field-service && docker compose up -d" -TimeOut 60
Write-Output $result3.Output

Write-Output "`n=== Checking status ==="
$result4 = Invoke-SSHCommand -SessionId $session.SessionId -Command "cd /opt/field-service && docker compose ps" -TimeOut 10
Write-Output $result4.Output

Remove-SSHSession -SessionId $session.SessionId
Write-Output "`nDone!"
