# Script for uploading fixed files to server
$pass = ConvertTo-SecureString "owo?8x-YA@vRN*" -AsPlainText -Force
$cred = New-Object System.Management.Automation.PSCredential("root", $pass)
$s = New-SSHSession -ComputerName 217.199.254.27 -Credential $cred -AcceptKey

# Files to upload
$files = @(
    @{
        Local = "C:\ProjectF\field-service\field_service\bots\master_bot\handlers\orders.py"
        Remote = "/opt/field-service/field_service/bots/master_bot/handlers/orders.py"
    },
    @{
        Local = "C:\ProjectF\field-service\field_service\bots\master_bot\texts.py"
        Remote = "/opt/field-service/field_service/bots/master_bot/texts.py"
    },
    @{
        Local = "C:\ProjectF\field-service\field_service\bots\master_bot\keyboards.py"
        Remote = "/opt/field-service/field_service/bots/master_bot/keyboards.py"
    },
    @{
        Local = "C:\ProjectF\field-service\field_service\bots\common\breadcrumbs.py"
        Remote = "/opt/field-service/field_service/bots/common/breadcrumbs.py"
    }
)

foreach ($file in $files) {
    Write-Host "Uploading $($file.Local)..." -ForegroundColor Yellow
    
    # Create backup
    $timestamp = Get-Date -Format 'yyyyMMdd_HHmmss'
    $backupCmd = "cp $($file.Remote) $($file.Remote).backup_$timestamp"
    Invoke-SSHCommand -SessionId $s.SessionId -Command $backupCmd | Out-Null
    
    # Upload file via SFTP
    Set-SCPFile -ComputerName 217.199.254.27 -Credential $cred -LocalFile $file.Local -RemotePath $file.Remote -AcceptKey
    
    Write-Host "OK Uploaded $($file.Remote)" -ForegroundColor Green
}

Write-Host ""
Write-Host "=== Restarting master-bot ===" -ForegroundColor Cyan
$result = Invoke-SSHCommand -SessionId $s.SessionId -Command "cd /opt/field-service; docker-compose restart master-bot"
Write-Host $result.Output

Write-Host ""
Write-Host "=== Checking status ===" -ForegroundColor Cyan
Start-Sleep -Seconds 3
$result = Invoke-SSHCommand -SessionId $s.SessionId -Command "docker ps | grep master-bot"
Write-Host $result.Output

Remove-SSHSession -SessionId $s.SessionId
Write-Host ""
Write-Host "OK Done!" -ForegroundColor Green
