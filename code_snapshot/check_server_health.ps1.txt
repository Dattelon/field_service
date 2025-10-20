# Field Service - Server Health Check

$SERVER = "217.199.254.27"
$PASSWORD = "owo?8x-YA@vRN*"

$pass = ConvertTo-SecureString $PASSWORD -AsPlainText -Force
$cred = New-Object System.Management.Automation.PSCredential("root", $pass)
$s = New-SSHSession -ComputerName $SERVER -Credential $cred -AcceptKey

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "FIELD SERVICE - HEALTH CHECK" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# Container status
Write-Host "`n[1] Container Status:" -ForegroundColor Yellow
$r = Invoke-SSHCommand -SessionId $s.SessionId -Command "cd /opt/field-service && docker compose ps"
Write-Host $r.Output

# Disk usage
Write-Host "`n[2] Disk Usage:" -ForegroundColor Yellow
$r = Invoke-SSHCommand -SessionId $s.SessionId -Command "df -h | grep -E '(Filesystem|/dev/)'"
Write-Host $r.Output

# Memory usage
Write-Host "`n[3] Memory Usage:" -ForegroundColor Yellow
$r = Invoke-SSHCommand -SessionId $s.SessionId -Command "free -h"
Write-Host $r.Output

# Docker stats
Write-Host "`n[4] Docker Container Stats:" -ForegroundColor Yellow
$r = Invoke-SSHCommand -SessionId $s.SessionId -Command "docker stats --no-stream --format 'table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}'"
Write-Host $r.Output

# Check for errors in logs
Write-Host "`n[5] Recent Errors in Logs:" -ForegroundColor Yellow
$r = Invoke-SSHCommand -SessionId $s.SessionId -Command "cd /opt/field-service && docker compose logs --tail=100 | grep -i 'error\|critical\|failed' | tail -10"
if ($r.Output.Trim()) {
    Write-Host $r.Output -ForegroundColor Red
} else {
    Write-Host "No recent errors found" -ForegroundColor Green
}

# Heartbeat check
Write-Host "`n[6] Heartbeat Status:" -ForegroundColor Yellow
$r = Invoke-SSHCommand -SessionId $s.SessionId -Command "cd /opt/field-service && docker compose logs --since 5m | grep 'alive' | tail -5"
if ($r.Output.Trim()) {
    Write-Host $r.Output -ForegroundColor Green
} else {
    Write-Host "No heartbeat detected in last 5 minutes!" -ForegroundColor Red
}

# Database connection
Write-Host "`n[7] Database Connection:" -ForegroundColor Yellow
$r = Invoke-SSHCommand -SessionId $s.SessionId -Command "cd /opt/field-service && docker compose exec -T postgres pg_isready -U fs_user -d field_service"
if ($r.ExitStatus -eq 0) {
    Write-Host "Database: OK" -ForegroundColor Green
} else {
    Write-Host "Database: FAILED" -ForegroundColor Red
}

Remove-SSHSession -SessionId $s.SessionId

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "Health check complete" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
