"""
Скрипт для сбора структуры проекта в один файл.
Игнорирует .git, __pycache__, .venv, node_modules и другие служебные папки.
"""
import os
from pathlib import Path

def should_ignore(name: str) -> bool:
    """Проверяет, нужно ли игнорировать директорию или файл."""
    ignore_list = {
        '.git', '__pycache__', '.venv', 'venv', 'node_modules',
        '.pytest_cache', '.mypy_cache', '.idea', '.vscode',
        'dist', 'build', '*.egg-info', '.backup', 'backup',
        'admin_bot.backup', 'bots\\admin_bot.backup'
    }
    return name in ignore_list or name.startswith('.')

def collect_structure(root_path: Path, prefix: str = "", output_lines: list = None, level: int = 0, max_level: int = 10) -> list:
    """Рекурсивно собирает структуру директорий."""
    if output_lines is None:
        output_lines = []
    
    if level > max_level:
        return output_lines
    
    try:
        items = sorted(root_path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
    except PermissionError:
        return output_lines
    
    dirs = [item for item in items if item.is_dir() and not should_ignore(item.name)]
    files = [item for item in items if item.is_file() and not should_ignore(item.name)]
    
    # Сначала файлы
    for i, file in enumerate(files):
        is_last_file = (i == len(files) - 1) and len(dirs) == 0
        connector = "└── " if is_last_file else "├── "
        output_lines.append(f"{prefix}{connector}{file.name}")
    
    # Потом директории
    for i, directory in enumerate(dirs):
        is_last = i == len(dirs) - 1
        connector = "└── " if is_last else "├── "
        extension = "    " if is_last else "│   "
        
        output_lines.append(f"{prefix}{connector}{directory.name}/")
        collect_structure(directory, prefix + extension, output_lines, level + 1, max_level)
    
    return output_lines

def main():
    # Путь к проекту
    project_root = Path(r"C:\ProjectF\field-service")
    output_file = Path(r"C:\ProjectF\project_structure.txt")
    
    print(f"Собираю структуру проекта из: {project_root}")
    print(f"Результат будет сохранён в: {output_file}")
    
    lines = [f"Структура проекта: {project_root}\n", "=" * 80, ""]
    lines.append(f"{project_root.name}/")
    
    structure_lines = collect_structure(project_root, prefix="", max_level=15)
    lines.extend(structure_lines)
    
    # Сохраняем в файл
    output_file.write_text("\n".join(lines), encoding="utf-8")
    
    print(f"\nСтруктура проекта сохранена в {output_file}")
    print(f"Всего строк: {len(lines)}")

if __name__ == "__main__":
    main()
