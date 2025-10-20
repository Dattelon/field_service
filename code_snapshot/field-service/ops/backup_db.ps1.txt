param(
    [string]$DatabaseUrl = $Env:DATABASE_URL,
    [string]$BackupDir = "backups"
)

if (-not $DatabaseUrl) {
    Write-Error "DATABASE_URL is not set"
    exit 1
}

$timestamp = (Get-Date).ToUniversalTime().ToString('yyyyMMdd_HHmmssZ')
if (-not (Test-Path -LiteralPath $BackupDir)) {
    New-Item -ItemType Directory -Path $BackupDir | Out-Null
}

$dumpPath = Join-Path -Path $BackupDir -ChildPath ("pg_{0}.dump" -f $timestamp)
& pg_dump -Fc -d $DatabaseUrl -f $dumpPath

Get-ChildItem -Path $BackupDir -Filter 'pg_*.dump' -File | Where-Object {
    $_.LastWriteTime -lt (Get-Date).AddDays(-7)
} | Remove-Item -Force -ErrorAction SilentlyContinue
