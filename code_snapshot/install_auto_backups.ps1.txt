# Field Service - Install Auto Backups on Server

$SERVER = "217.199.254.27"
$PASSWORD = "owo?8x-YA@vRN*"

Write-Host "========================================" -ForegroundColor Green
Write-Host "Installing Auto Backups on Server" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""

# Connect
$pass = ConvertTo-SecureString $PASSWORD -AsPlainText -Force
$cred = New-Object System.Management.Automation.PSCredential("root", $pass)

Write-Host "Uploading backup setup script..." -ForegroundColor Cyan
$sftp = New-SFTPSession -ComputerName $SERVER -Credential $cred -AcceptKey
Set-SFTPItem -SessionId $sftp.SessionId -Path "C:\ProjectF\setup_auto_backups.sh" -Destination "/tmp/" -Force
Remove-SFTPSession -SessionId $sftp.SessionId

Write-Host "Running setup on server..." -ForegroundColor Cyan
$s = New-SSHSession -ComputerName $SERVER -Credential $cred -AcceptKey
$result = Invoke-SSHCommand -SessionId $s.SessionId -Command "chmod +x /tmp/setup_auto_backups.sh && bash /tmp/setup_auto_backups.sh" -TimeOut 60
Write-Host $result.Output

if ($result.ExitStatus -eq 0) {
    Write-Host "`nAuto backups installed successfully!" -ForegroundColor Green
} else {
    Write-Host "`nInstallation failed!" -ForegroundColor Red
}

Remove-SSHSession -SessionId $s.SessionId
