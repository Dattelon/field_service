# Script to show detailed differences
$pass = ConvertTo-SecureString "owo?8x-YA@vRN*" -AsPlainText -Force
$cred = New-Object System.Management.Automation.PSCredential("root", $pass)

$s = New-SSHSession -ComputerName 217.199.254.27 -Credential $cred -AcceptKey

function Compare-FileDetails {
    param($localPath, $remotePath, $name)
    
    Write-Host "`n=== $name ===" -ForegroundColor Cyan
    
    if (Test-Path $localPath) {
        $localContent = Get-Content $localPath -Raw
        $remoteResult = Invoke-SSHCommand -SessionId $s.SessionId -Command "cat $remotePath"
        $remoteContent = $remoteResult.Output -join "`n"
        
        # Line count
        $localLines = ($localContent -split "`n").Count
        $remoteLines = ($remoteContent -split "`n").Count
        
        Write-Host "Local:  $($localContent.Length) bytes, $localLines lines"
        Write-Host "Remote: $($remoteContent.Length) bytes, $remoteLines lines"
        
        # First 10 lines comparison
        $localFirst = ($localContent -split "`n")[0..9] -join "`n"
        $remoteFirst = ($remoteContent -split "`n")[0..9] -join "`n"
        
        if ($localFirst -ne $remoteFirst) {
            Write-Host "First 10 lines differ!" -ForegroundColor Yellow
        }
        
        # Last 10 lines comparison
        $localLast = ($localContent -split "`n")[-10..-1] -join "`n"
        $remoteLast = ($remoteContent -split "`n")[-10..-1] -join "`n"
        
        if ($localLast -ne $remoteLast) {
            Write-Host "Last 10 lines differ!" -ForegroundColor Yellow
        }
    } else {
        Write-Host "Local file not found: $localPath" -ForegroundColor Red
    }
}

# Control bot
Compare-FileDetails -localPath "C:\ProjectF\control-bot\control_bot.py" -remotePath "/opt/control-bot/control_bot.py" -name "control_bot.py"

# Admin bot main
Compare-FileDetails -localPath "C:\ProjectF\field-service\field_service\bots\admin_bot\main.py" -remotePath "/opt/field-service/field_service/bots/admin_bot/main.py" -name "admin_bot/main.py"

# Master bot main
Compare-FileDetails -localPath "C:\ProjectF\field-service\field_service\bots\master_bot\main.py" -remotePath "/opt/field-service/field_service/bots/master_bot/main.py" -name "master_bot/main.py"

# Config
Compare-FileDetails -localPath "C:\ProjectF\field-service\field_service\config.py" -remotePath "/opt/field-service/field_service/config.py" -name "config.py"

# Docker compose
Compare-FileDetails -localPath "C:\ProjectF\field-service\docker-compose.yml" -remotePath "/opt/field-service/docker-compose.yml" -name "docker-compose.yml"

Remove-SSHSession -SessionId $s.SessionId
