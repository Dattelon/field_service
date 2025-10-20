#!/usr/bin/env python3
"""
Find empty or suspicious strings in Python files
"""
import ast
import sys
from pathlib import Path
from typing import List, Set

def find_suspicious_strings(filepath: Path) -> List[dict]:
    """Find empty or suspicious string values in Python files."""
    issues = []
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        tree = ast.parse(content, filepath)
        
        for node in ast.walk(tree):
            # Check Dict nodes for empty string values
            if isinstance(node, ast.Dict):
                for key, value in zip(node.keys, node.values):
                    if isinstance(value, ast.Constant) and isinstance(value.value, str):
                        text = value.value
                        # Check for empty or very short suspicious strings
                        if text == "" or (0 < len(text) < 3 and not text.isascii()):
                            issues.append({
                                'file': str(filepath),
                                'line': value.lineno,
                                'type': 'empty_or_short_string',
                                'value': repr(text),
                                'key': ast.unparse(key) if key else None
                            })
            
            # Check string constants
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                text = node.value
                # Look for patterns that suggest mojibake
                if text and not text.isascii():
                    # Check if it looks like garbage (multiple non-ASCII chars in short string)
                    non_ascii = sum(1 for c in text if ord(c) > 127)
                    if non_ascii > 0 and len(text) < 5:
                        issues.append({
                            'file': str(filepath),
                            'line': node.lineno,
                            'type': 'suspicious_non_ascii',
                            'value': repr(text),
                            'bytes': text.encode('utf-8').hex()
                        })
    
    except SyntaxError as e:
        print(f"Syntax error in {filepath}: {e}", file=sys.stderr)
    except Exception as e:
        print(f"Error processing {filepath}: {e}", file=sys.stderr)
    
    return issues

def scan_project(root: Path) -> List[dict]:
    """Scan all Python files in project."""
    all_issues = []
    
    for py_file in root.rglob('*.py'):
        # Skip virtual environments and caches
        if any(part in str(py_file) for part in ['.venv', '__pycache__', '.pytest_cache', 'alembic/versions']):
            continue
        
        issues = find_suspicious_strings(py_file)
        if issues:
            all_issues.extend(issues)
    
    return all_issues

def main():
    root = Path('C:/ProjectF/field-service/field_service')
    
    print(f"Scanning {root} for empty/suspicious strings...")
    issues = scan_project(root)
    
    if not issues:
        print("\nNo issues found!")
        return 0
    
    print(f"\nFound {len(issues)} potential issues:\n")
    
    # Group by file
    by_file = {}
    for issue in issues:
        filepath = issue['file']
        if filepath not in by_file:
            by_file[filepath] = []
        by_file[filepath].append(issue)
    
    # Print report
    for filepath in sorted(by_file.keys()):
        print(f"\nFile: {filepath}")
        for issue in by_file[filepath]:
            print(f"  Line {issue['line']}: {issue['type']}")
            print(f"    Value: {issue['value']}")
            if 'key' in issue and issue['key']:
                print(f"    Key: {issue['key']}")
            if 'bytes' in issue:
                print(f"    Bytes: {issue['bytes']}")
    
    return 1

if __name__ == '__main__':
    sys.exit(main())
