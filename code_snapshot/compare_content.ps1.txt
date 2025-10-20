# Script to compare content of key files
$pass = ConvertTo-SecureString "owo?8x-YA@vRN*" -AsPlainText -Force
$cred = New-Object System.Management.Automation.PSCredential("root", $pass)

Write-Host "=== Connecting to server ===" -ForegroundColor Cyan
$s = New-SSHSession -ComputerName 217.199.254.27 -Credential $cred -AcceptKey
Write-Host "Connected" -ForegroundColor Green

# Control bot
Write-Host "`n=== Control Bot ===" -ForegroundColor Cyan
$localControlBot = Get-Content "C:\ProjectF\control-bot\control_bot.py" -Raw
$remoteResult = Invoke-SSHCommand -SessionId $s.SessionId -Command "cat /opt/control-bot/control_bot.py"
$remoteControlBot = $remoteResult.Output -join "`n"

$localHash = (Get-FileHash -InputStream ([System.IO.MemoryStream]::new([System.Text.Encoding]::UTF8.GetBytes($localControlBot))) -Algorithm SHA256).Hash
$remoteHash = (Get-FileHash -InputStream ([System.IO.MemoryStream]::new([System.Text.Encoding]::UTF8.GetBytes($remoteControlBot))) -Algorithm SHA256).Hash

Write-Host "Local control_bot.py: $localHash"
Write-Host "Remote control_bot.py: $remoteHash"

if ($localHash -eq $remoteHash) {
    Write-Host "control_bot.py: IDENTICAL" -ForegroundColor Green
} else {
    Write-Host "control_bot.py: DIFFERENT" -ForegroundColor Red
    Write-Host "Local size: $($localControlBot.Length) bytes"
    Write-Host "Remote size: $($remoteControlBot.Length) bytes"
}

# Key files from field-service
Write-Host "`n=== Field Service Key Files ===" -ForegroundColor Cyan

$keyFiles = @(
    "field_service/bots/admin_bot/main.py",
    "field_service/bots/master_bot/main.py",
    "field_service/config.py",
    "docker-compose.yml",
    ".env"
)

$differences = @()

foreach ($file in $keyFiles) {
    $localPath = "C:\ProjectF\field-service\" + $file.Replace("/", "\")
    
    if (Test-Path $localPath) {
        $localContent = Get-Content $localPath -Raw -ErrorAction SilentlyContinue
        $remoteResult = Invoke-SSHCommand -SessionId $s.SessionId -Command "cat /opt/field-service/$file"
        $remoteContent = $remoteResult.Output -join "`n"
        
        $localHash = (Get-FileHash -InputStream ([System.IO.MemoryStream]::new([System.Text.Encoding]::UTF8.GetBytes($localContent))) -Algorithm SHA256).Hash
        $remoteHash = (Get-FileHash -InputStream ([System.IO.MemoryStream]::new([System.Text.Encoding]::UTF8.GetBytes($remoteContent))) -Algorithm SHA256).Hash
        
        if ($localHash -eq $remoteHash) {
            Write-Host "$file : OK" -ForegroundColor Green
        } else {
            Write-Host "$file : DIFFERENT" -ForegroundColor Red
            $differences += $file
        }
    } else {
        Write-Host "$file : NOT FOUND LOCALLY" -ForegroundColor Yellow
    }
}

Remove-SSHSession -SessionId $s.SessionId
Write-Host "`n=== Summary ===" -ForegroundColor Cyan
if ($differences.Count -eq 0) {
    Write-Host "All key files are identical" -ForegroundColor Green
} else {
    Write-Host "Different files: $($differences.Count)" -ForegroundColor Red
    $differences | ForEach-Object { Write-Host "  - $_" -ForegroundColor Red }
}
