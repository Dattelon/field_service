#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Исправление текстов кнопок в create.py"""

def fix_texts():
    file_path = r"C:\ProjectF\field-service\field_service\bots\admin_bot\handlers\orders\create.py"
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Замена "Выберите способ:" на "Выберите способ распределения."
    old_text = 'Выберите способ:'
    new_text = 'Выберите способ распределения.'
    
    count = content.count(old_text)
    print(f"Found {count} occurrences of '{old_text}'")
    
    if count > 0:
        content = content.replace(old_text, new_text)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"SUCCESS: Replaced {count} occurrences")
        print(f"  Old: {old_text}")
        print(f"  New: {new_text}")
    else:
        print("NOT FOUND: Searching for variants...")
        
        # Check for different variants
        variants = [
            "способ:",
            "способ ",
            "Выберите",
        ]
        
        for var in variants:
            if var in content:
                print(f"  Found variant: {var}")

if __name__ == "__main__":
    fix_texts()
