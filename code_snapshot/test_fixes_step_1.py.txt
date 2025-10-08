# -*- coding: utf-8 -*-
"""
Тестовый скрипт для проверки исправлений Этапа 1.1-1.3
Проверяет синтаксис и базовую корректность изменённых файлов
"""

import ast
import sys
from pathlib import Path

def check_syntax(filepath: str) -> bool:
    """Проверка синтаксиса Python файла"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            code = f.read()
        ast.parse(code)
        print(f"[OK] {Path(filepath).name}: Syntax correct")
        return True
    except SyntaxError as e:
        print(f"[ERROR] {Path(filepath).name}: Syntax error on line {e.lineno}")
        print(f"   {e.msg}")
        return False
    except Exception as e:
        print(f"[ERROR] {Path(filepath).name}: Read error: {e}")
        return False


def check_key_changes(filepath: str, expected_changes: list[str]) -> bool:
    """Проверка наличия ключевых изменений"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        missing = []
        for change in expected_changes:
            if change not in content:
                missing.append(change)
        
        if missing:
            print(f"[WARN] {Path(filepath).name}: Missing expected changes:")
            for m in missing:
                print(f"   - {m}")
            return False
        
        print(f"[OK] {Path(filepath).name}: All key changes present")
        return True
    except Exception as e:
        print(f"[ERROR] {Path(filepath).name}: Check error: {e}")
        return False


def main():
    print("=" * 60)
    print("CHECKING FIXES: Stage 1.1-1.3")
    print("=" * 60)
    print()
    
    # Правильный путь к проекту
    base_path = Path("C:/ProjectF/field-service/field_service")
    
    # Файл 1: master_bot/handlers/orders.py
    print("=" * 60)
    print("FILE 1: orders.py (Fix 1.1 + 1.2)")
    print("=" * 60)
    orders_file = base_path / "bots" / "master_bot" / "handlers" / "orders.py"
    print(f"Path: {orders_file}")
    
    syntax_ok_1 = check_syntax(str(orders_file))
    changes_ok_1 = check_key_changes(
        str(orders_file),
        [
            # Fix 1.1: Race Condition
            "with_for_update(skip_locked=True)",
            "already locked by another master",
            # Fix 1.2: DEFERRED orders
            "m.OrderStatus.DEFERRED",
        ]
    )
    
    print()
    
    # Файл 2: services/distribution_scheduler.py
    print("=" * 60)
    print("FILE 2: distribution_scheduler.py (Fix 1.2 + 1.3)")
    print("=" * 60)
    scheduler_file = base_path / "services" / "distribution_scheduler.py"
    print(f"Path: {scheduler_file}")
    
    syntax_ok_2 = check_syntax(str(scheduler_file))
    changes_ok_2 = check_key_changes(
        str(scheduler_file),
        [
            # Fix 1.2: DEFERRED in SQL
            "o.status = 'DEFERRED'",
            "state IN ('SENT', 'VIEWED')",
            # Fix 1.3: Preferred master diagnostics
            "_check_preferred_master_availability",
            "preferred_master=%s UNAVAILABLE",  # Corrected text
            "searching all masters",
        ]
    )
    
    print()
    print("=" * 60)
    
    all_ok = syntax_ok_1 and syntax_ok_2 and changes_ok_1 and changes_ok_2
    
    if all_ok:
        print("[SUCCESS] ALL CHECKS PASSED!")
        print()
        print("Summary:")
        print("  Fix 1.1: Race Condition - OK")
        print("  Fix 1.2: DEFERRED orders - OK")
        print("  Fix 1.3: Guarantee orders - OK")
        print()
        print("Next steps:")
        print("  1. Start project: docker-compose up -d")
        print("  2. Check logs: docker-compose logs -f distribution_scheduler")
        print("  3. Test offer acceptance (2 masters simultaneously)")
        print("  4. Test DEFERRED order acceptance")
        print("  5. Test guarantee order with unavailable preferred master")
        return 0
    else:
        print("[FAIL] ISSUES DETECTED!")
        print("  Check files for errors before running")
        return 1


if __name__ == "__main__":
    sys.exit(main())
