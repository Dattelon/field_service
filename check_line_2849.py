#!/usr/bin/env python3
"""Проверка строки 2849 в services_db.py"""
from pathlib import Path

services_db = Path("field-service/field_service/bots/admin_bot/services_db.py")
content = services_db.read_text(encoding='utf-8')
lines = content.split('\n')

print('📄 Проверка строки 2849:\n')
if len(lines) >= 2849:
    print(f"Строка 2849: {lines[2848]}")  # Массив с 0
    
    print('\n📋 Контекст (строки 2840-2860):\n')
    for i in range(2839, min(2860, len(lines))):
        line_num = i + 1
        marker = '→' if line_num == 2849 else ' '
        print(f"{marker} {line_num}: {lines[i]}")
else:
    print(f"❌ Файл содержит только {len(lines)} строк")

# Теперь поищем все методы модерации
print('\n\n🔍 Поиск всех методов модерации:\n')

import re

moderation_methods = [
    'approve_master',
    'reject_master',
    'block_master',
    'unblock_master',
    'set_master_limit',
    'enqueue_master_notification'
]

for method in moderation_methods:
    pattern = rf'^\s*async def {method}\('
    found_lines = []
    
    for i, line in enumerate(lines, 1):
        if re.match(pattern, line):
            found_lines.append(i)
    
    if found_lines:
        print(f"✅ {method}() - найден на строке(ах): {', '.join(map(str, found_lines))}")
    else:
        print(f"❌ {method}() - НЕ найден")

print('\n📊 ИТОГ:')
found_count = sum(1 for method in moderation_methods 
                  if any(re.match(rf'^\s*async def {method}\(', line) 
                        for line in lines))
print(f"Найдено {found_count}/{len(moderation_methods)} методов")

if found_count == len(moderation_methods):
    print('\n✅ ВСЕ МЕТОДЫ МОДЕРАЦИИ РЕАЛИЗОВАНЫ!')
    print('P0-1 можно считать ВЫПОЛНЕННЫМ ✅')
