#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fix button texts in create.py - replace by line numbers"""

def fix_texts_by_line():
    file_path = r"C:\ProjectF\field-service\field_service\bots\admin_bot\handlers\orders\create.py"
    
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # Lines 935 and 981 (1-indexed) need fixing
    # Convert to 0-indexed
    lines_to_fix = [934, 980]
    
    old_fragment = "  :"
    new_fragment = "Выберите способ распределения."
    
    count = 0
    for idx in lines_to_fix:
        if old_fragment in lines[idx]:
            lines[idx] = lines[idx].replace(old_fragment, new_fragment)
            count += 1
            print(f"Fixed line {idx + 1}")
    
    if count > 0:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.writelines(lines)
        
        print(f"\nSUCCESS: Fixed {count} lines")
        print(f"  Lines: {[l+1 for l in lines_to_fix]}")
    else:
        print("ERROR: Could not find target text in specified lines")
        for idx in lines_to_fix:
            print(f"  Line {idx + 1}: {repr(lines[idx])}")

if __name__ == "__main__":
    fix_texts_by_line()
