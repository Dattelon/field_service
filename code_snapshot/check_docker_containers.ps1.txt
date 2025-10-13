# Check Docker containers on server
$SERVER = "217.199.254.27"
$PASSWORD = "owo?8x-YA@vRN*"

$pass = ConvertTo-SecureString $PASSWORD -AsPlainText -Force
$cred = New-Object System.Management.Automation.PSCredential("root", $pass)
$s = New-SSHSession -ComputerName $SERVER -Credential $cred -AcceptKey

Write-Host "Docker containers:" -ForegroundColor Yellow
$r = Invoke-SSHCommand -SessionId $s.SessionId -Command "docker ps --format 'table {{.Names}}\t{{.Status}}'"
Write-Host $r.Output

Remove-SSHSession -SessionId $s.SessionId
