#!/usr/bin/env python3
"""
Скрипт для безопасного удаления временных файлов
"""
import os
from pathlib import Path

# Корень проекта
ROOT = Path(r"C:\ProjectF")
FIELD_SERVICE = ROOT / "field-service"

# Файлы для удаления
FILES_TO_DELETE_ROOT = [
    # Временные Python скрипты
    "apply_orders_patch.py",
    "apply_patch.ps1",
    "apply_queue_refactor.py",
    "check_queue_refactor.py",
    "_apply_patch.py",
    "rewrite_migration.py",
    "rewrite_services.py",
    
    # Сниппеты
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
    
    # Утилиты debugging
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
    
    # tmp файлы
    "tmp_edit_orders.py",
    "_tmp_fix.py",
    "_update_admin_imports.py",
    "__tmp_check.py",
    "__tmp_codes.py",
    "__tmp_count.py",
    "__tmp_patch_notice.py",
    "__tmp_replace_unicode.py",
    "__tmp_show_lines.py",
    
    # Patch файлы
    "mini.patch",
    "patch.diff",
    "tmp_handlers_step2.patch",
    
    # Старые
    "TZ(old)",
]

FILES_TO_DELETE_FIELD_SERVICE = [
    # Временные скрипты
    "collect_files.py",
    "collect_files.pyc",
    "find_methods.py",
    "_set_city_tz.py",
    
    # Patch/design файлы
    "P0_MODERATION_ACTION_PLAN.md",
    "P0_MODERATION_METHODS.py",
    "P1_QUEUE_SEARCH_PATCH.py",
    "P2_11_BULK_APPROVE_METHOD.py",
    "P2_11_DBFINANCE_PATCH.py",
    "P2_11_SUMMARY.md",
    "P2_BULK_APPROVE_DESIGN.py",
    "P2_SCHEDULED_REPORTS_DESIGN.md",
    "PATCH_DBMastersService_moderation.py",
    
    # Diff файлы
    "patch1.diff",
    "patch_export.diff",
    "temp_patch.diff",
    
    # Temp test файлы
    "temp_message_answer.py",
    "temp_simulate_close.py",
    "temp_simulate_close2.py",
    "temp_simulate_close3.py",
    
    # Snapshot
    "project_snapshot.txt",
]


def delete_files(base_path: Path, files: list[str]) -> tuple[list[str], list[str], list[str]]:
    """Удалить файлы, вернуть (deleted, not_found, errors)"""
    deleted = []
    not_found = []
    errors = []
    
    for file in files:
        full_path = base_path / file
        try:
            if full_path.exists():
                full_path.unlink()
                deleted.append(file)
                print(f"✅ Удалён: {file}")
            else:
                not_found.append(file)
                print(f"⏭️  Не найден: {file}")
        except Exception as e:
            errors.append((file, str(e)))
            print(f"❌ Ошибка при удалении {file}: {e}")
    
    return deleted, not_found, errors


def main():
    print("🗑️ УДАЛЕНИЕ ВРЕМЕННЫХ ФАЙЛОВ\n")
    print("="*60)
    
    # Удаление из корня
    print("\n📁 Корень проекта (C:\\ProjectF):")
    print("-"*60)
    deleted_root, not_found_root, errors_root = delete_files(ROOT, FILES_TO_DELETE_ROOT)
    
    # Удаление из field-service
    print(f"\n📁 field-service:")
    print("-"*60)
    deleted_fs, not_found_fs, errors_fs = delete_files(FIELD_SERVICE, FILES_TO_DELETE_FIELD_SERVICE)
    
    # Итоги
    print("\n" + "="*60)
    print("📊 ИТОГИ:")
    print("="*60)
    
    total_deleted = len(deleted_root) + len(deleted_fs)
    total_not_found = len(not_found_root) + len(not_found_fs)
    total_errors = len(errors_root) + len(errors_fs)
    
    print(f"✅ Удалено файлов: {total_deleted}")
    print(f"   - Корень: {len(deleted_root)}")
    print(f"   - field-service: {len(deleted_fs)}")
    
    print(f"\n⏭️  Не найдено: {total_not_found}")
    print(f"❌ Ошибок: {total_errors}")
    
    if total_errors > 0:
        print("\n❌ Ошибки:")
        for file, error in errors_root + errors_fs:
            print(f"  - {file}: {error}")
    
    print("\n✅ Очистка завершена!")
    print("\nРекомендации:")
    print("1. Проверьте что проект работает: cd field-service && pytest")
    print("2. Сделайте commit: git add -A && git commit -m 'chore: cleanup temp files'")


if __name__ == "__main__":
    main()
