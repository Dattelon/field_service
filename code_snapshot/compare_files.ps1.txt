# Script to compare local and remote bot files
$localBase = "C:\ProjectF\field-service\field_service\bots"
$remoteBase = "/opt/field-service/field_service/bots"

# SSH connection
$pass = ConvertTo-SecureString "owo?8x-YA@vRN*" -AsPlainText -Force
$cred = New-Object System.Management.Automation.PSCredential("root", $pass)

Write-Host "=== Connecting to server ===" -ForegroundColor Cyan
try {
    $s = New-SSHSession -ComputerName 217.199.254.27 -Credential $cred -AcceptKey -ErrorAction Stop
    Write-Host "Connected (Session ID: $($s.SessionId))" -ForegroundColor Green
} catch {
    Write-Host "Connection error: $_" -ForegroundColor Red
    exit 1
}

# Function to get remote files list
function Get-RemoteFiles {
    param($path)
    $cmd = "cd /opt/field-service && find $path -name '*.py' -type f | sort"
    $result = Invoke-SSHCommand -SessionId $s.SessionId -Command $cmd
    return $result.Output
}

Write-Host "`n=== Comparing file structure ===" -ForegroundColor Cyan

$bots = @("admin_bot", "master_bot", "common")
$differences = @()

foreach ($bot in $bots) {
    Write-Host "`n--- $bot ---" -ForegroundColor Yellow
    
    # Local files
    $localPath = Join-Path $localBase $bot
    $localFiles = Get-ChildItem -Path $localPath -Filter "*.py" -Recurse -File | 
        ForEach-Object { $_.FullName.Replace($localBase + "\", "").Replace("\", "/") } |
        Sort-Object
    
    # Remote files
    $remotePath = "field_service/bots/$bot"
    $remoteFiles = Get-RemoteFiles $remotePath | ForEach-Object { $_.Replace("field_service/bots/", "") }
    
    Write-Host "Local files: $($localFiles.Count)" -ForegroundColor Cyan
    Write-Host "Remote files: $($remoteFiles.Count)" -ForegroundColor Cyan
    
    # Files only locally
    $onlyLocal = $localFiles | Where-Object { $_ -notin $remoteFiles }
    if ($onlyLocal) {
        Write-Host "`nOnly local:" -ForegroundColor Magenta
        $onlyLocal | ForEach-Object { 
            Write-Host "  - $_" -ForegroundColor Magenta
            $differences += [PSCustomObject]@{
                Type = "OnlyLocal"
                Bot = $bot
                File = $_
            }
        }
    }
    
    # Files only on server
    $onlyRemote = $remoteFiles | Where-Object { $_ -notin $localFiles }
    if ($onlyRemote) {
        Write-Host "`nOnly on server:" -ForegroundColor Yellow
        $onlyRemote | ForEach-Object { 
            Write-Host "  - $_" -ForegroundColor Yellow
            $differences += [PSCustomObject]@{
                Type = "OnlyRemote"
                Bot = $bot
                File = $_
            }
        }
    }
    
    # Common files
    $commonFiles = $localFiles | Where-Object { $_ -in $remoteFiles }
    Write-Host "`nCommon files: $($commonFiles.Count)" -ForegroundColor Cyan
}

Remove-SSHSession -SessionId $s.SessionId
Write-Host "`nDisconnected from server" -ForegroundColor Green

# Summary
Write-Host "`n=== SUMMARY ===" -ForegroundColor Cyan
if ($differences.Count -eq 0) {
    Write-Host "File structure is identical" -ForegroundColor Green
} else {
    Write-Host "Found differences: $($differences.Count)" -ForegroundColor Red
    $differences | Format-Table -AutoSize
}
