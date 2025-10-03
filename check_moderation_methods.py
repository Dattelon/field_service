#!/usr/bin/env python3
"""Проверка наличия методов модерации в DBMastersService"""
import re
from pathlib import Path

services_db = Path("field-service/field_service/bots/admin_bot/services_db.py")

if not services_db.exists():
    print(f"❌ Файл не найден: {services_db}")
    exit(1)

content = services_db.read_text(encoding='utf-8')

# Извлекаем класс DBMastersService
class_match = re.search(r'class DBMastersService[\s\S]*?(?=\nclass |$)', content)

if not class_match:
    print("❌ Класс DBMastersService не найден!")
    exit(1)

print("✅ Класс DBMastersService найден")
print(f"📏 Размер класса: ~{len(class_match.group(0)) // 1000}KB\n")

class_content = class_match.group(0)

# Проверяем методы модерации
moderation_methods = [
    'approve_master',
    'reject_master',
    'block_master',
    'unblock_master',
    'set_master_limit',
    'enqueue_master_notification'
]

print("🔍 Проверка методов модерации:\n")

found_count = 0
for method in moderation_methods:
    pattern = rf'\s+async def {method}\s*\('
    found = bool(re.search(pattern, class_content))
    status = '✅' if found else '❌'
    print(f"{status} {method}()")
    if found:
        found_count += 1

print(f"\n📊 Итого: {found_count}/{len(moderation_methods)} методов")

if found_count == 0:
    print('\n⚠️ ВЕРДИКТ: Методы модерации НЕ реализованы!')
    print('\n📝 ЧТО ЭТО ЗНАЧИТ:')
    print('- Роутер admin_moderation.py вызывает service.approve_master()')
    print('- Но в DBMastersService этого метода НЕТ')
    print('- При попытке одобрить мастера будет AttributeError')
    print('\n💡 РЕШЕНИЕ:')
    print('Нужно добавить эти 6 методов в класс DBMastersService')
    print('Патч готов: field-service/PATCH_DBMastersService_moderation.py')
elif found_count == 6:
    print('\n✅ ВЕРДИКТ: Все методы модерации реализованы!')
    print('P0-1 можно считать ВЫПОЛНЕННЫМ')
else:
    print(f'\n⚠️ ВЕРДИКТ: Частично реализовано ({found_count}/6)')
    print('Не хватает некоторых методов')
