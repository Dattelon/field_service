#!/usr/bin/env python3
"""
Поиск битых кириллических строк в Python файлах.
Ищем кракозябры типа À, Ð, Ñ, Ð, Ð и т.д.
"""
import re
import sys
from pathlib import Path
from typing import List, Tuple

# Паттерны для поиска кракозябр
MOJIBAKE_PATTERNS = [
    r'[\x80-\xFF]{2,}',  # Два и более байта в диапазоне 128-255
    r'[ÀÁÂÃÄÅÆÇÈÉÊËÌÍÎÏ]{2,}',  # Латиница с диакритикой
    r'[ÐÑÒÓÔÕÖ×ØÙÚÛÜÝÞß]{2,}',  # Еще латиница с диакритикой
    r'[àáâãäåæçèéêëìíîï]{2,}',  # Строчные с диакритикой
    r'[ðñòóôõö÷øùúûüýþÿ]{2,}',  # Строчные с диакритикой
]

# Контексты, которые НЕ проверяем
SKIP_CONTEXTS = [
    r'^\s*#',  # Комментарии
    r'^\s*import\s',  # Импорты
    r'^\s*from\s.*import',  # Импорты from
]

def is_likely_mojibake(text: str) -> bool:
    """Проверяет, похожа ли строка на кракозябры."""
    for pattern in MOJIBAKE_PATTERNS:
        if re.search(pattern, text):
            return True
    return False

def should_skip_line(line: str) -> bool:
    """Проверяет, нужно ли пропустить строку."""
    for pattern in SKIP_CONTEXTS:
        if re.match(pattern, line):
            return True
    return False

def extract_string_literals(line: str) -> List[Tuple[str, int, int]]:
    """
    Извлекает строковые литералы из строки кода.
    Возвращает: [(строка, start_pos, end_pos), ...]
    """
    results = []
    
    # Паттерны для строк
    patterns = [
        r'f"([^"]*)"',  # f-строки с двойными кавычками
        r"f'([^']*)'",  # f-строки с одинарными кавычками
        r'"([^"]*)"',   # обычные строки с двойными кавычками
        r"'([^']*)'",   # обычные строки с одинарными кавычками
    ]
    
    for pattern in patterns:
        for match in re.finditer(pattern, line):
            text = match.group(1)
            if text and not text.isascii():  # Только не-ASCII строки
                results.append((text, match.start(), match.end()))
    
    return results

def find_mojibake_in_file(filepath: Path) -> List[dict]:
    """Ищет кракозябры в файле."""
    issues = []
    
    try:
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()
        
        for line_num, line in enumerate(lines, 1):
            # Пропускаем комментарии и импорты
            if should_skip_line(line):
                continue
            
            # Извлекаем строковые литералы
            string_literals = extract_string_literals(line)
            
            for text, start, end in string_literals:
                if is_likely_mojibake(text):
                    # Проверяем длину - кракозябры обычно короткие (1-15 символов)
                    # но выглядят как мусор
                    if 1 <= len(text) <= 30:
                        issues.append({
                            'file': str(filepath),
                            'line': line_num,
                            'column': start,
                            'text': text,
                            'context': line.strip()
                        })
    
    except Exception as e:
        print(f"Error reading {filepath}: {e}", file=sys.stderr)
    
    return issues

def scan_directory(root: Path) -> List[dict]:
    """Сканирует директорию на наличие Python файлов с кракозябрами."""
    all_issues = []
    
    for py_file in root.rglob('*.py'):
        # Пропускаем виртуальные окружения и кэши
        if any(part in str(py_file) for part in ['.venv', '__pycache__', '.pytest_cache']):
            continue
        
        issues = find_mojibake_in_file(py_file)
        if issues:
            all_issues.extend(issues)
    
    return all_issues

def main():
    root = Path('C:/ProjectF/field-service/field_service')
    
    print(f"Scanning {root}...")
    issues = scan_directory(root)
    
    if not issues:
        print("\nNo mojibake found!")
        return 0
    
    print(f"\nFound {len(issues)} potential issues:\n")
    
    # Группируем по файлам
    by_file = {}
    for issue in issues:
        filepath = issue['file']
        if filepath not in by_file:
            by_file[filepath] = []
        by_file[filepath].append(issue)
    
    # Output report
    for filepath in sorted(by_file.keys()):
        print(f"\nFile: {filepath}")
        for issue in by_file[filepath]:
            print(f"   Line {issue['line']}, column {issue['column']}")
            print(f"   Text: '{issue['text']}'")
            print(f"   Context: {issue['context'][:100]}")
            print()
    
    return 1

if __name__ == '__main__':
    sys.exit(main())
