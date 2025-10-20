# Скрипт для создания снапшота структуры БД PostgreSQL
# Использует psql для получения структуры

$ErrorActionPreference = "Stop"
$OutputEncoding = [System.Text.Encoding]::UTF8

# Параметры подключения
$containerName = "field-service-postgres-1"
$dbUser = "fs_user"
$dbName = "field_service"
$outputFile = "db_structure_snapshot_$(Get-Date -Format 'yyyy-MM-dd_HHmmss').txt"

Write-Host "==================================" -ForegroundColor Cyan
Write-Host "СОЗДАНИЕ СНАПШОТА СТРУКТУРЫ БД" -ForegroundColor Cyan
Write-Host "==================================" -ForegroundColor Cyan
Write-Host ""

# Создать файл с заголовком
$header = @"
================================================================================
СНАПШОТ СТРУКТУРЫ БАЗЫ ДАННЫХ PostgreSQL
================================================================================
Дата создания: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
База данных: $dbName
================================================================================

"@

$header | Out-File -FilePath $outputFile -Encoding UTF8

Write-Host "📊 Получение общей информации о БД..." -ForegroundColor Yellow

# Общая информация о БД
$generalInfo = @"

================================================================================
ОБЩАЯ ИНФОРМАЦИЯ
================================================================================
"@

$generalInfo | Out-File -FilePath $outputFile -Append -Encoding UTF8

# Версия PostgreSQL
docker exec -i $containerName psql -U $dbUser -d $dbName -c "SELECT version();" | 
    Out-File -FilePath $outputFile -Append -Encoding UTF8

# Размер БД
docker exec -i $containerName psql -U $dbUser -d $dbName -c "SELECT pg_size_pretty(pg_database_size('$dbName')) as database_size;" |
    Out-File -FilePath $outputFile -Append -Encoding UTF8

Write-Host "📋 Получение списка таблиц..." -ForegroundColor Yellow

# Список таблиц с размерами
$tablesInfo = @"

================================================================================
СПИСОК ТАБЛИЦ С РАЗМЕРАМИ
================================================================================
"@

$tablesInfo | Out-File -FilePath $outputFile -Append -Encoding UTF8

docker exec -i $containerName psql -U $dbUser -d $dbName -c @"
SELECT 
    tablename,
    pg_size_pretty(pg_total_relation_size(quote_ident(tablename)::regclass)) as size
FROM pg_tables 
WHERE schemaname = 'public' 
ORDER BY pg_total_relation_size(quote_ident(tablename)::regclass) DESC;
"@ | Out-File -FilePath $outputFile -Append -Encoding UTF8

Write-Host "🔍 Получение детальной структуры таблиц..." -ForegroundColor Yellow

# Получить список таблиц
$tables = docker exec -i $containerName psql -U $dbUser -d $dbName -t -c "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename;"

# Для каждой таблицы получить детальную информацию
foreach ($table in $tables) {
    $table = $table.Trim()
    if ([string]::IsNullOrWhiteSpace($table)) { continue }
    
    Write-Host "  • $table" -ForegroundColor Gray
    
    $tableHeader = @"

================================================================================
ТАБЛИЦА: $table
================================================================================

СТРУКТУРА ТАБЛИЦЫ:
--------------------------------------------------------------------------------
"@
    
    $tableHeader | Out-File -FilePath $outputFile -Append -Encoding UTF8
    
    # Описание таблицы
    docker exec -i $containerName psql -U $dbUser -d $dbName -c "\d $table" |
        Out-File -FilePath $outputFile -Append -Encoding UTF8
    
    # Количество записей
    "`n" | Out-File -FilePath $outputFile -Append -Encoding UTF8
    "КОЛИЧЕСТВО ЗАПИСЕЙ:" | Out-File -FilePath $outputFile -Append -Encoding UTF8
    "--------------------------------------------------------------------------------" | Out-File -FilePath $outputFile -Append -Encoding UTF8
    
    docker exec -i $containerName psql -U $dbUser -d $dbName -c "SELECT COUNT(*) as count FROM $table;" |
        Out-File -FilePath $outputFile -Append -Encoding UTF8
}

Write-Host "🎲 Получение ENUM типов..." -ForegroundColor Yellow

# ENUM типы
$enumsInfo = @"

================================================================================
ENUM ТИПЫ
================================================================================
"@

$enumsInfo | Out-File -FilePath $outputFile -Append -Encoding UTF8

docker exec -i $containerName psql -U $dbUser -d $dbName -c @"
SELECT 
    t.typname as enum_name,
    STRING_AGG(e.enumlabel, ', ' ORDER BY e.enumsortorder) as enum_values
FROM pg_type t
JOIN pg_enum e ON t.oid = e.enumtypid
WHERE t.typnamespace = (SELECT oid FROM pg_namespace WHERE nspname = 'public')
GROUP BY t.typname
ORDER BY t.typname;
"@ | Out-File -FilePath $outputFile -Append -Encoding UTF8

Write-Host "🔢 Получение sequences..." -ForegroundColor Yellow

# Sequences
$sequencesInfo = @"

================================================================================
SEQUENCES
================================================================================
"@

$sequencesInfo | Out-File -FilePath $outputFile -Append -Encoding UTF8

docker exec -i $containerName psql -U $dbUser -d $dbName -c @"
SELECT sequencename, last_value 
FROM pg_sequences s
LEFT JOIN LATERAL (
    SELECT last_value FROM pg_sequences WHERE sequencename = s.sequencename
) lv ON true
WHERE schemaname = 'public'
ORDER BY sequencename;
"@ | Out-File -FilePath $outputFile -Append -Encoding UTF8

Write-Host "📊 Получение статистики по таблицам..." -ForegroundColor Yellow

# Статистика
$statsInfo = @"

================================================================================
СТАТИСТИКА ПО ТАБЛИЦАМ
================================================================================
"@

$statsInfo | Out-File -FilePath $outputFile -Append -Encoding UTF8

docker exec -i $containerName psql -U $dbUser -d $dbName -c @"
SELECT 
    schemaname,
    tablename,
    n_tup_ins as inserts,
    n_tup_upd as updates,
    n_tup_del as deletes,
    n_live_tup as live_rows,
    n_dead_tup as dead_rows
FROM pg_stat_user_tables
ORDER BY n_live_tup DESC;
"@ | Out-File -FilePath $outputFile -Append -Encoding UTF8

Write-Host "🔐 Получение ролей и прав доступа..." -ForegroundColor Yellow

# Роли и права
$rolesInfo = @"

================================================================================
РОЛИ И ПРАВА ДОСТУПА
================================================================================
"@

$rolesInfo | Out-File -FilePath $outputFile -Append -Encoding UTF8

docker exec -i $containerName psql -U $dbUser -d $dbName -c "\du" |
    Out-File -FilePath $outputFile -Append -Encoding UTF8

# Завершение
$footer = @"

================================================================================
СНАПШОТ ЗАВЕРШЕН
================================================================================
Дата завершения: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
Файл: $outputFile
================================================================================
"@

$footer | Out-File -FilePath $outputFile -Append -Encoding UTF8

Write-Host ""
Write-Host "✅ Снапшот структуры БД успешно создан!" -ForegroundColor Green
Write-Host "📄 Файл: $outputFile" -ForegroundColor Cyan
Write-Host "📊 Размер: $((Get-Item $outputFile).Length / 1KB) KB" -ForegroundColor Cyan
Write-Host ""
Write-Host "Откройте файл для просмотра структуры БД" -ForegroundColor Yellow
