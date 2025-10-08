# Simple script to create DB structure snapshot
# Uses pg_dump for fast schema export

$ErrorActionPreference = "Stop"

$containerName = "field-service-postgres-1"
$dbUser = "fs_user"
$dbName = "field_service"
$timestamp = Get-Date -Format 'yyyy-MM-dd_HHmmss'
$outputFile = "db_schema_$timestamp.sql"
$readableFile = "db_structure_$timestamp.txt"

Write-Host "==================================" -ForegroundColor Cyan
Write-Host "DB STRUCTURE SNAPSHOT" -ForegroundColor Cyan
Write-Host "==================================" -ForegroundColor Cyan
Write-Host ""

# Create SQL schema dump
Write-Host "Creating SQL schema dump..." -ForegroundColor Yellow
docker exec -i $containerName pg_dump -U $dbUser -d $dbName --schema-only --no-owner --no-privileges -f /tmp/schema.sql

# Copy from container
docker cp ${containerName}:/tmp/schema.sql $outputFile

Write-Host "SQL schema saved: $outputFile" -ForegroundColor Green
Write-Host ""

# Create readable version
Write-Host "Creating readable version..." -ForegroundColor Yellow

$header = @"
================================================================================
DATABASE STRUCTURE: $dbName
================================================================================
Created: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
Format: Readable text
================================================================================

"@

$header | Out-File -FilePath $readableFile -Encoding UTF8

# Statistics
"STATISTICS:" | Out-File -FilePath $readableFile -Append -Encoding UTF8
"--------------------------------------------------------------------------------" | Out-File -FilePath $readableFile -Append -Encoding UTF8

# Tables count
$tablesCount = docker exec -i $containerName psql -U $dbUser -d $dbName -t -c "SELECT COUNT(*) FROM pg_tables WHERE schemaname = 'public';"
"Tables: $($tablesCount.Trim())" | Out-File -FilePath $readableFile -Append -Encoding UTF8

# ENUM types count
$enumsCount = docker exec -i $containerName psql -U $dbUser -d $dbName -t -c "SELECT COUNT(DISTINCT typname) FROM pg_type t WHERE typnamespace = (SELECT oid FROM pg_namespace WHERE nspname = 'public') AND typtype = 'e';"
"ENUM types: $($enumsCount.Trim())" | Out-File -FilePath $readableFile -Append -Encoding UTF8

# Sequences count
$seqCount = docker exec -i $containerName psql -U $dbUser -d $dbName -t -c "SELECT COUNT(*) FROM pg_sequences WHERE schemaname = 'public';"
"Sequences: $($seqCount.Trim())" | Out-File -FilePath $readableFile -Append -Encoding UTF8

# DB size
$dbSize = docker exec -i $containerName psql -U $dbUser -d $dbName -t -c "SELECT pg_size_pretty(pg_database_size('$dbName'));"
"Database size: $($dbSize.Trim())" | Out-File -FilePath $readableFile -Append -Encoding UTF8

"`n" | Out-File -FilePath $readableFile -Append -Encoding UTF8

# Tables list
"TABLES:" | Out-File -FilePath $readableFile -Append -Encoding UTF8
"--------------------------------------------------------------------------------" | Out-File -FilePath $readableFile -Append -Encoding UTF8

docker exec -i $containerName psql -U $dbUser -d $dbName -c "SELECT relname as table_name, n_live_tup as rows FROM pg_stat_user_tables ORDER BY n_live_tup DESC;" | Out-File -FilePath $readableFile -Append -Encoding UTF8

# Add SQL schema
"`n`n" | Out-File -FilePath $readableFile -Append -Encoding UTF8
"================================================================================`n" | Out-File -FilePath $readableFile -Append -Encoding UTF8
"SQL SCHEMA`n" | Out-File -FilePath $readableFile -Append -Encoding UTF8
"================================================================================`n`n" | Out-File -FilePath $readableFile -Append -Encoding UTF8

Get-Content $outputFile | Out-File -FilePath $readableFile -Append -Encoding UTF8

$sqlSize = [math]::Round((Get-Item $outputFile).Length / 1KB, 2)
$txtSize = [math]::Round((Get-Item $readableFile).Length / 1KB, 2)

Write-Host "Readable version saved: $readableFile" -ForegroundColor Green
Write-Host ""
Write-Host "Created files:" -ForegroundColor Cyan
Write-Host "  - $outputFile - SQL schema ($sqlSize KB)" -ForegroundColor Gray
Write-Host "  - $readableFile - Readable version ($txtSize KB)" -ForegroundColor Gray
Write-Host ""
Write-Host "Done!" -ForegroundColor Green
