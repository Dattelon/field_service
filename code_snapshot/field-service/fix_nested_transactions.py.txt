"""
Script to fix nested transactions in services by adding session parameter
and using maybe_managed_session.
"""
import re
from pathlib import Path


def fix_service_file(file_path: Path) -> tuple[bool, str]:
    """
    Fix a service file to use maybe_managed_session.
    
    Returns:
        (changed, message)
    """
    content = file_path.read_text(encoding='utf-8')
    original = content
    
    # Check if already imports maybe_managed_session
    has_import = 'from field_service.services._session_utils import maybe_managed_session' in content
    
    # Add import if needed
    if not has_import and 'from field_service.db.session import SessionLocal' in content:
        content = content.replace(
            'from field_service.db.session import SessionLocal',
            'from field_service.db.session import SessionLocal\nfrom field_service.services._session_utils import maybe_managed_session'
        )
    
    # Pattern 1: async with self._session_factory() as session:\n            async with session.begin():
    # Replace with: async with maybe_managed_session(session) as s:
    pattern1 = r'async with self\._session_factory\(\) as session:\s*\n\s*async with session\.begin\(\):'
    
    def replacement1(match):
        indent = '        '  # 8 spaces
        return f'async with maybe_managed_session(session) as s:'
    
    # First pass: replace the pattern but keep session variable
    content_lines = content.split('\n')
    new_lines = []
    i = 0
    while i < len(content_lines):
        line = content_lines[i]
        
        # Check for pattern
        if 'async with self._session_factory() as session:' in line and i + 1 < len(content_lines):
            next_line = content_lines[i + 1]
            if 'async with session.begin():' in next_line:
                # Found the pattern - skip both lines and add replacement
                indent = ' ' * (len(line) - len(line.lstrip()))
                new_lines.append(f'{indent}async with maybe_managed_session(session) as s:')
                i += 2
                continue
        
        new_lines.append(line)
        i += 1
    
    content = '\n'.join(new_lines)
    
    # Now replace all 'session.' with 's.' within the changed functions
    # This is tricky - we need to identify the scope and replace only there
    # For now, let's do a simple approach: replace 'await session.' with 'await s.'
    content = content.replace('await session.execute', 'await s.execute')
    content = content.replace('await session.scalar', 'await s.scalar')
    content = content.replace('await session.get', 'await s.get')
    content = content.replace('session.add(', 's.add(')
    content = content.replace('session.add_all(', 's.add_all(')
    content = content.replace('await session.flush', 'await s.flush')
    content = content.replace('await session.commit', 'await s.commit')
    content = content.replace('await session.refresh', 'await s.refresh')
    content = content.replace('await session.run_sync', 'await s.run_sync')
    
    changed = content != original
    if changed:
        file_path.write_text(content, encoding='utf-8')
        return True, f"Fixed {file_path.name}"
    else:
        return False, f"No changes needed for {file_path.name}"


def main():
    # Find all service files in admin_bot/services
    services_dir = Path('C:/ProjectF/field-service/field_service/bots/admin_bot/services')
    
    if not services_dir.exists():
        print(f"Directory not found: {services_dir}")
        return
    
    files_to_fix = [
        'masters.py',
        'staff.py',
        'settings.py',
        'orders.py',
        'distribution.py',
    ]
    
    print("Starting fix process...")
    print()
    
    for filename in files_to_fix:
        file_path = services_dir / filename
        if file_path.exists():
            changed, message = fix_service_file(file_path)
            status = '[OK]' if changed else '[--]'
            print(f"{status} {message}")
        else:
            print(f"[!!] File not found: {filename}")
    
    print()
    print("Done!")


if __name__ == '__main__':
    main()
