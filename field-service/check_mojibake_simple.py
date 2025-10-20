#!/usr/bin/env python3
import re
from pathlib import Path

file = Path('field_service/bots/admin_bot/handlers/masters/main.py')
content = file.read_text(encoding='utf-8')

print("Searching for mojibake patterns...")
print("=" * 60)

line_num = 0
found_issues = 0

for line in content.split('\n'):
    line_num += 1
    
    # Skip comments and imports
    if line.strip().startswith('#') or line.strip().startswith('import') or line.strip().startswith('from'):
        continue
    
    # Look for Latin characters with diacritics (common mojibake pattern)
    if re.search(r'[À-ÿ]{2,}', line):
        found_issues += 1
        print(f"\nLine {line_num}:")
        print(f"  {line.strip()[:120]}")
        # Show the specific mojibake pattern
        matches = re.findall(r'[À-ÿ]+', line)
        for match in matches:
            print(f"  -> Mojibake: '{match}'")

print(f"\n{'=' * 60}")
print(f"Total issues found: {found_issues}")
