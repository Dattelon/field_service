# Deploy owner requisites bugfix
$ErrorActionPreference = "Stop"

Write-Host "=== Deploying Owner Requisites Bugfix ===" -ForegroundColor Cyan

# Connection details
$server = "217.199.254.27"
$user = "root"
$pass = ConvertTo-SecureString "owo?8x-YA@vRN*" -AsPlainText -Force
$cred = New-Object System.Management.Automation.PSCredential($user, $pass)

# Files to deploy
$files = @(
    @{
        Local = "C:\ProjectF\field-service\field_service\bots\admin_bot\handlers\finance\main.py"
        Remote = "/opt/field-service/field_service/bots/admin_bot/handlers/finance/main.py"
    },
    @{
        Local = "C:\ProjectF\field-service\field_service\bots\admin_bot\ui\keyboards\finance.py"
        Remote = "/opt/field-service/field_service/bots/admin_bot/ui/keyboards/finance.py"
    },
    @{
        Local = "C:\ProjectF\field-service\field_service\bots\master_bot\handlers\finance.py"
        Remote = "/opt/field-service/field_service/bots/master_bot/handlers/finance.py"
    }
)

$session = $null

try {
    # Create SSH session
    Write-Host "`nCreating SSH session..." -ForegroundColor Yellow
    $session = New-SSHSession -ComputerName $server -Credential $cred -AcceptKey
    Write-Host "OK Session created (ID: $($session.SessionId))" -ForegroundColor Green

    # Copy each file
    Write-Host "`nCopying files..." -ForegroundColor Yellow
    foreach ($file in $files) {
        Write-Host "  Copying: $($file.Local)" -ForegroundColor Gray
        
        # Read file content and encode to base64
        $content = Get-Content -Path $file.Local -Raw -Encoding UTF8
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($content)
        $base64 = [Convert]::ToBase64String($bytes)
        
        # Create temp file with base64 content
        $tempFile = "/tmp/deploy_$(Get-Random).b64"
        $cmd = "echo '$base64' > '$tempFile'"
        $result = Invoke-SSHCommand -SessionId $session.SessionId -Command $cmd
        
        # Decode and save to target
        $cmd = "base64 -d '$tempFile' > '$($file.Remote)'"
        $result = Invoke-SSHCommand -SessionId $session.SessionId -Command $cmd
        if ($result.ExitStatus -ne 0) {
            throw "Failed to deploy file: $($result.Error)"
        }
        
        # Remove temp file
        Invoke-SSHCommand -SessionId $session.SessionId -Command "rm '$tempFile'" | Out-Null
        
        Write-Host "    OK Deployed to: $($file.Remote)" -ForegroundColor Green
    }

    # Restart containers
    Write-Host "`nRestarting containers..." -ForegroundColor Yellow
    $result = Invoke-SSHCommand -SessionId $session.SessionId -Command "cd /opt/field-service; docker compose restart admin-bot master-bot"
    if ($result.ExitStatus -ne 0) {
        throw "Failed to restart containers: $($result.Error)"
    }
    Write-Host "OK Containers restarted" -ForegroundColor Green

    # Show logs
    Write-Host "`nChecking logs..." -ForegroundColor Yellow
    Start-Sleep -Seconds 3
    $result = Invoke-SSHCommand -SessionId $session.SessionId -Command "cd /opt/field-service; docker compose logs --tail=20 admin-bot master-bot"
    Write-Host $result.Output

    Write-Host "`n=== Deployment completed successfully! ===" -ForegroundColor Green

} catch {
    Write-Host "`nX Deployment failed: $_" -ForegroundColor Red
    Write-Host $_.ScriptStackTrace -ForegroundColor Red
    exit 1
} finally {
    if ($session) {
        Remove-SSHSession -SessionId $session.SessionId | Out-Null
        Write-Host "OK SSH session closed" -ForegroundColor Gray
    }
}
