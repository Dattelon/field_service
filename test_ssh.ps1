$password = ConvertTo-SecureString "owo?8x-YA@vRN*" -AsPlainText -Force
$credential = New-Object System.Management.Automation.PSCredential ("root", $password)

Write-Host "Connecting to server..." -ForegroundColor Yellow
$session = New-SSHSession -ComputerName 217.199.254.27 -Credential $credential -AcceptKey

if ($session) {
    Write-Host "Connected successfully!" -ForegroundColor Green
    
    # Test command
    $result = Invoke-SSHCommand -SessionId $session.SessionId -Command "whoami && uname -a"
    Write-Host $result.Output
    
    Remove-SSHSession -SessionId $session.SessionId
} else {
    Write-Host "Connection failed!" -ForegroundColor Red
}
