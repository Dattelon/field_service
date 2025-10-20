#!/usr/bin/env python3
"""
Comprehensive report of all string issues in the project
"""
import ast
from pathlib import Path
from collections import defaultdict

def find_all_issues(filepath: Path):
    """Find all string issues in a file."""
    issues = []
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            content = ''.join(lines)
        
        tree = ast.parse(content, filepath)
        
        for node in ast.walk(tree):
            # Check Dict nodes
            if isinstance(node, ast.Dict):
                for key, value in zip(node.keys, node.values):
                    if isinstance(value, ast.Constant) and isinstance(value.value, str):
                        text = value.value
                        # Empty strings or very short non-ASCII
                        if text == "" or (0 < len(text) < 10 and not text.isascii()):
                            key_repr = ast.unparse(key) if key else None
                            context_line = lines[value.lineno - 1].strip() if value.lineno <= len(lines) else ""
                            issues.append({
                                'line': value.lineno,
                                'value': text,
                                'key': key_repr,
                                'context': context_line[:100]
                            })
    
    except (SyntaxError, Exception):
        pass
    
    return issues

def main():
    root = Path('C:/ProjectF/field-service/field_service')
    
    # Collect all issues by file
    files_with_issues = defaultdict(list)
    
    for py_file in root.rglob('*.py'):
        if any(part in str(py_file) for part in ['.venv', '__pycache__', '.pytest_cache', 'alembic/versions']):
            continue
        
        issues = find_all_issues(py_file)
        if issues:
            rel_path = py_file.relative_to(root.parent)
            files_with_issues[str(rel_path)] = issues
    
    # Print summary report
    print("=" * 80)
    print(f"BITЫЕ КИРИЛЛИЧЕСКИЕ СТРОКИ - СВОДНЫЙ ОТЧЁТ")
    print("=" * 80)
    print(f"\nВсего файлов с проблемами: {len(files_with_issues)}")
    print(f"Всего проблем: {sum(len(v) for v in files_with_issues.values())}\n")
    
    # Group by directory
    by_dir = defaultdict(list)
    for fpath in sorted(files_with_issues.keys()):
        dir_name = str(Path(fpath).parent)
        by_dir[dir_name].append(fpath)
    
    print("\n📁 ГРУППИРОВКА ПО ДИРЕКТОРИЯМ:\n")
    for dir_name in sorted(by_dir.keys()):
        files = by_dir[dir_name]
        total_issues = sum(len(files_with_issues[f]) for f in files)
        print(f"{dir_name}:")
        print(f"  Файлов: {len(files)}, Проблем: {total_issues}")
        for fpath in files:
            print(f"    - {Path(fpath).name} ({len(files_with_issues[fpath])} проблем)")
    
    print("\n" + "=" * 80)
    print("ДЕТАЛЬНАЯ ИНФОРМАЦИЯ ПО КАЖДОМУ ФАЙЛУ")
    print("=" * 80 + "\n")
    
    for fpath in sorted(files_with_issues.keys()):
        issues = files_with_issues[fpath]
        print(f"\n📄 {fpath}")
        print(f"   Всего проблем: {len(issues)}\n")
        
        for issue in issues[:10]:  # Show first 10 issues per file
            print(f"   Строка {issue['line']}:")
            print(f"     Ключ: {issue['key']}")
            print(f"     Значение: {repr(issue['value'])}")
            if issue['value'] == '':
                print(f"     ❌ ПУСТАЯ СТРОКА - нужен русский текст!")
            else:
                print(f"     ⚠️  БИТАЯ КИРИЛЛИЦА")
            print()
        
        if len(issues) > 10:
            print(f"   ... и ещё {len(issues) - 10} проблем\n")
    
    print("\n" + "=" * 80)
    print("ИТОГО:")
    print(f"  - Файлов для исправления: {len(files_with_issues)}")
    print(f"  - Всего проблемных строк: {sum(len(v) for v in files_with_issues.values())}")
    print("=" * 80)

if __name__ == '__main__':
    main()
