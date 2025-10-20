#!/usr/bin/env python3
import ast
import json
from pathlib import Path
from collections import defaultdict

def find_all_issues(filepath: Path):
    issues = []
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            content = ''.join(lines)
        
        tree = ast.parse(content, filepath)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Dict):
                for key, value in zip(node.keys, node.values):
                    if isinstance(value, ast.Constant) and isinstance(value.value, str):
                        text = value.value
                        if text == "" or (0 < len(text) < 10 and not text.isascii()):
                            key_repr = ast.unparse(key) if key else None
                            context_line = lines[value.lineno - 1].strip() if value.lineno <= len(lines) else ""
                            issues.append({
                                'line': value.lineno,
                                'value': text,
                                'key': key_repr,
                                'context': context_line[:100]
                            })
    except:
        pass
    return issues

root = Path('C:/ProjectF/field-service/field_service')
files_with_issues = {}

for py_file in root.rglob('*.py'):
    if any(part in str(py_file) for part in ['.venv', '__pycache__', '.pytest_cache', 'alembic/versions']):
        continue
    
    issues = find_all_issues(py_file)
    if issues:
        rel_path = str(py_file.relative_to(root.parent))
        files_with_issues[rel_path] = issues

# Save to JSON
with open('C:/ProjectF/field-service/mojibake_report.json', 'w', encoding='utf-8') as f:
    json.dump(files_with_issues, f, ensure_ascii=False, indent=2)

print(f"Found {len(files_with_issues)} files with {sum(len(v) for v in files_with_issues.values())} issues")
print("Report saved to mojibake_report.json")
