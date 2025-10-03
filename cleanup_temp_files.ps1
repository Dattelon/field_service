# Скрипт для удаления временных файлов
# PowerShell

Write-Host "🗑️ УДАЛЕНИЕ ВРЕМЕННЫХ ФАЙЛОВ" -ForegroundColor Cyan
Write-Host "=" * 60

$root = "C:\ProjectF"
$fieldService = "$root\field-service"

$deletedCount = 0
$notFoundCount = 0
$errorCount = 0

# Файлы в корне проекта
$rootFiles = @(
    "apply_orders_patch.py",
    "apply_patch.ps1",
    "apply_queue_refactor.py",
    "check_queue_refactor.py",
    "_apply_patch.py",
    "rewrite_migration.py",
    "rewrite_services.py",
    "approve_snippet.txt",
    "block.txt",
    "city_chunk.txt",
    "create_order_block.txt",
    "orders_service_block.txt",
    "snip_fin.txt",
    "temp_queue_backup.txt",
    "tmp_section.txt",
    "tmp_section2.txt",
    "menu_dump.json",
    "check_fffd.py",
    "check_parse.py",
    "count_strings.py",
    "esc.py",
    "esc_list.py",
    "extract_block.py",
    "findbytes.py",
    "inspect_chars.py",
    "inspect_line.py",
    "readbytes.py",
    "replace_block.py",
    "repr_block.py",
    "update_dw.py",
    "write_texts.py",
    "tmp_edit_orders.py",
    "_tmp_fix.py",
    "_update_admin_imports.py",
    "__tmp_check.py",
    "__tmp_codes.py",
    "__tmp_count.py",
    "__tmp_patch_notice.py",
    "__tmp_replace_unicode.py",
    "__tmp_show_lines.py",
    "mini.patch",
    "patch.diff",
    "tmp_handlers_step2.patch",
    "TZ(old)"
)

# Файлы в field-service
$fieldServiceFiles = @(
    "collect_files.py",
    "collect_files.pyc",
    "find_methods.py",
    "_set_city_tz.py",
    "P0_MODERATION_ACTION_PLAN.md",
    "P0_MODERATION_METHODS.py",
    "P1_QUEUE_SEARCH_PATCH.py",
    "P2_11_BULK_APPROVE_METHOD.py",
    "P2_11_DBFINANCE_PATCH.py",
    "P2_11_SUMMARY.md",
    "P2_BULK_APPROVE_DESIGN.py",
    "P2_SCHEDULED_REPORTS_DESIGN.md",
    "PATCH_DBMastersService_moderation.py",
    "patch1.diff",
    "patch_export.diff",
    "temp_patch.diff",
    "temp_message_answer.py",
    "temp_simulate_close.py",
    "temp_simulate_close2.py",
    "temp_simulate_close3.py",
    "project_snapshot.txt"
)

Write-Host "`n📁 Корень проекта ($root):" -ForegroundColor Yellow
Write-Host "-" * 60

foreach ($file in $rootFiles) {
    $path = Join-Path $root $file
    if (Test-Path $path) {
        try {
            Remove-Item $path -Force
            Write-Host "✅ Удалён: $file" -ForegroundColor Green
            $deletedCount++
        }
        catch {
            Write-Host "❌ Ошибка при удалении $file`: $_" -ForegroundColor Red
            $errorCount++
        }
    }
    else {
        Write-Host "⏭️  Не найден: $file" -ForegroundColor Gray
        $notFoundCount++
    }
}

Write-Host "`n📁 field-service:" -ForegroundColor Yellow
Write-Host "-" * 60

foreach ($file in $fieldServiceFiles) {
    $path = Join-Path $fieldService $file
    if (Test-Path $path) {
        try {
            Remove-Item $path -Force
            Write-Host "✅ Удалён: $file" -ForegroundColor Green
            $deletedCount++
        }
        catch {
            Write-Host "❌ Ошибка при удалении $file`: $_" -ForegroundColor Red
            $errorCount++
        }
    }
    else {
        Write-Host "⏭️  Не найден: $file" -ForegroundColor Gray
        $notFoundCount++
    }
}

Write-Host "`n" + ("=" * 60)
Write-Host "📊 ИТОГИ:" -ForegroundColor Cyan
Write-Host ("=" * 60)
Write-Host "✅ Удалено файлов: $deletedCount" -ForegroundColor Green
Write-Host "⏭️  Не найдено: $notFoundCount" -ForegroundColor Gray
Write-Host "❌ Ошибок: $errorCount" -ForegroundColor Red

Write-Host "`n✅ Очистка завершена!" -ForegroundColor Green
Write-Host "`nРекомендации:"
Write-Host "1. Проверьте что проект работает: cd field-service; pytest"
Write-Host "2. Сделайте commit: git add -A; git commit -m 'chore: cleanup temp files'"
