# Field Service - View Server Logs

param(
    [string]$Service = "all",  # all, admin-bot, master-bot, postgres
    [int]$Lines = 50,
    [switch]$Follow = $false
)

$SERVER = "217.199.254.27"
$PASSWORD = "owo?8x-YA@vRN*"

$pass = ConvertTo-SecureString $PASSWORD -AsPlainText -Force
$cred = New-Object System.Management.Automation.PSCredential("root", $pass)
$s = New-SSHSession -ComputerName $SERVER -Credential $cred -AcceptKey

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "FIELD SERVICE LOGS" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Service: $Service | Lines: $Lines | Follow: $Follow" -ForegroundColor Yellow
Write-Host ""

$cmd = "cd /opt/field-service && docker compose logs"

if ($Service -ne "all") {
    $cmd += " $Service"
}

$cmd += " --tail=$Lines"

if ($Follow) {
    Write-Host "Press Ctrl+C to stop following logs..." -ForegroundColor Yellow
    Write-Host ""
    $cmd += " -f"
    $stream = New-SSHShellStream -SessionId $s.SessionId
    $stream.WriteLine($cmd)
    
    try {
        while ($true) {
            if ($stream.DataAvailable) {
                Write-Host $stream.Read() -NoNewline
            }
            Start-Sleep -Milliseconds 100
        }
    }
    finally {
        $stream.Close()
    }
} else {
    $result = Invoke-SSHCommand -SessionId $s.SessionId -Command $cmd -TimeOut 30
    Write-Host $result.Output
}

Remove-SSHSession -SessionId $s.SessionId

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Examples:" -ForegroundColor Yellow
Write-Host "  .\view_server_logs.ps1 -Service admin-bot -Lines 100" -ForegroundColor White
Write-Host "  .\view_server_logs.ps1 -Service master-bot -Follow" -ForegroundColor White
Write-Host "  .\view_server_logs.ps1 -Service all -Lines 200" -ForegroundColor White
Write-Host "========================================" -ForegroundColor Cyan
