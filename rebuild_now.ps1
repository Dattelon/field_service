$password = "owo?8x-YA@vRN*"
$securePassword = ConvertTo-SecureString $password -AsPlainText -Force
$credential = New-Object System.Management.Automation.PSCredential("root", $securePassword)
$session = New-SSHSession -ComputerName 217.199.254.27 -Credential $credential -AcceptKey

$commands = @"
cd /opt/field-service
echo "=== Stopping ==="
docker compose down
echo "=== Building ==="
docker compose build --no-cache
echo "=== Starting ==="
docker compose up -d
echo "=== Status ==="
docker compose ps
"@

$result = Invoke-SSHCommand -SessionId $session.SessionId -Command $commands -TimeOut 600
Write-Output $result.Output

Remove-SSHSession -SessionId $session.SessionId
