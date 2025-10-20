"""
CRITICAL BUGFIX: Offer Accept Errors - Automatic Patch Application

Fixes:
1. distribution_metrics enum type mismatch
2. greenlet_spawn error after session.expire_all()

Author: AI Assistant
Date: 2025-10-13
"""

import re
from pathlib import Path

def apply_patch():
    """Apply critical bugfixes to orders.py"""
    
    file_path = Path(__file__).parent / "field_service" / "bots" / "master_bot" / "handlers" / "orders.py"
    
    print(f"[*] Reading file: {file_path}")
    content = file_path.read_text(encoding='utf-8')
    original_content = content
    
    # ========================================
    # FIX 1: Remove .value from enum columns
    # ========================================
    print("\n[FIX 1] Fixing enum type mismatch in distribution_metrics...")
    
    # Находим блок с distribution_metrics insert
    pattern_old_category = r'category=order_row\.category\.value if hasattr\(order_row\.category, \'value\'\) else str\(order_row\.category\),'
    pattern_new_category = 'category=order_row.category,  # BUGFIX: Pass enum directly, not string'
    
    if re.search(pattern_old_category, content):
        content = re.sub(pattern_old_category, pattern_new_category, content)
        print("   [+] Fixed category enum conversion")
    else:
        print("   [!] Category pattern not found (may already be fixed)")
    
    pattern_old_type = r'order_type=order_row\.type\.value if hasattr\(order_row\.type, \'value\'\) else str\(order_row\.type\),'
    pattern_new_type = 'order_type=order_row.type,  # BUGFIX: Pass enum directly, not string'
    
    if re.search(pattern_old_type, content):
        content = re.sub(pattern_old_type, pattern_new_type, content)
        print("   [+] Fixed order_type enum conversion")
    else:
        print("   [!] Order_type pattern not found (may already be fixed)")
    
    # ========================================
    # FIX 2: Remove session.expire_all()
    # ========================================
    print("\n[FIX 2] Removing session.expire_all() to fix greenlet error...")
    
    # Try to find and remove the expire_all block
    pattern_expire_alt = r'session\.expire_all\(\)\s*\n\s*_log\.info\("offer_accept: session cache expired for order=%s", order_id\)'
    
    if re.search(pattern_expire_alt, content):
        content = re.sub(
            pattern_expire_alt,
            '# BUGFIX: SQLAlchemy automatically refreshes data after commit\n    # No need for expire_all() - it breaks async context',
            content
        )
        print("   [+] Removed session.expire_all() call")
    else:
        print("   [!] expire_all pattern not found (may already be fixed)")
    
    # ========================================
    # Check if changes were made
    # ========================================
    if content == original_content:
        print("\n[!] No changes made - file may already be patched!")
        return False
    
    # ========================================
    # Write changes
    # ========================================
    print("\n[*] Writing changes to file...")
    file_path.write_text(content, encoding='utf-8')
    print("   [+] File updated successfully!")
    
    # ========================================
    # Show diff summary
    # ========================================
    print("\n[*] Changes summary:")
    print("   - Removed .value from category enum conversion")
    print("   - Removed .value from order_type enum conversion")
    print("   - Removed session.expire_all() call")
    
    return True


if __name__ == "__main__":
    print("=" * 60)
    print("CRITICAL BUGFIX: Offer Accept Errors")
    print("=" * 60)
    
    try:
        success = apply_patch()
        
        if success:
            print("\n" + "=" * 60)
            print("[SUCCESS] Patch applied successfully!")
            print("=" * 60)
            print("\n[NEXT STEPS]")
            print("1. Copy file to server:")
            print("   scp field_service/bots/master_bot/handlers/orders.py root@217.199.254.27:/opt/field-service/field_service/bots/master_bot/handlers/")
            print("\n2. Restart master-bot:")
            print("   docker compose restart master-bot")
            print("\n3. Check logs:")
            print("   docker logs --tail 50 field-service-master-bot-1")
        else:
            print("\n[!] No changes needed - file may already be fixed")
            
    except Exception as e:
        print(f"\n[ERROR] Error applying patch: {e}")
        import traceback
        traceback.print_exc()
