#!/usr/bin/env python3
"""
Скрипт для сбора всех кодовых файлов проекта в один файл.
Исключает документацию, логи, кэш и другие не-кодовые файлы.

Usage:
    python tools/collect_code.py
    python tools/collect_code.py --output code_export.txt
    python tools/collect_code.py --format markdown
"""

from __future__ import annotations

import argparse
import os
from datetime import datetime
from pathlib import Path
from typing import Iterator

# ====== НАСТРОЙКИ ======

# Включаемые расширения файлов (код)
INCLUDE_EXTENSIONS = {
    '.py',           # Python
    '.sql',          # SQL
    '.ini',          # Config
    '.toml',         # Config
    '.yaml', '.yml', # Config
    '.json',         # Config/Data
    '.env.example',  # Config template
    '.sh',           # Shell scripts
    '.bat',          # Batch scripts
    '.js',           # JavaScript (если есть)
    '.html',         # HTML (если есть)
    '.css',          # CSS (если есть)
}

# Исключаемые расширения (документация и прочее)
EXCLUDE_EXTENSIONS = {
    '.md',           # Markdown
    '.txt',          # Text
    '.log',          # Logs
    '.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico',  # Images
    '.pdf', '.doc', '.docx',  # Documents
    '.zip', '.tar', '.gz',     # Archives
    '.pyc', '.pyo',            # Python bytecode
    '.lock',                   # Lock files
    '.bak', '.backup',         # Backups
}

# Исключаемые директории
EXCLUDE_DIRS = {
    '__pycache__',
    '.git',
    '.venv',
    'venv',
    'env',
    '.mypy_cache',
    '.pytest_cache',
    '.ruff_cache',
    'node_modules',
    '.idea',
    '.vscode',
    'dist',
    'build',
    '*.egg-info',
}

# Исключаемые файлы по имени
EXCLUDE_FILES = {
    '.DS_Store',
    'Thumbs.db',
    '.gitignore',
    '.gitattributes',
    '.editorconfig',
    '.pre-commit-config.yaml',
}

# Максимальный размер файла в байтах (10 MB)
MAX_FILE_SIZE = 10 * 1024 * 1024


# ====== ОСНОВНОЙ КОД ======

def should_include_file(file_path: Path) -> bool:
    """Проверяет, нужно ли включать файл в сборку."""
    
    # Проверка имени файла
    if file_path.name in EXCLUDE_FILES:
        return False
    
    # Проверка расширения - исключения
    if any(file_path.name.endswith(ext) for ext in EXCLUDE_EXTENSIONS):
        return False
    
    # Проверка расширения - включения
    if not any(file_path.name.endswith(ext) for ext in INCLUDE_EXTENSIONS):
        # Специальная обработка для файлов без расширения
        if file_path.suffix == '':
            # Включаем только если это известные конфигурационные файлы
            known_no_ext = {'Dockerfile', 'Makefile', 'Procfile'}
            if file_path.name not in known_no_ext:
                return False
        else:
            return False
    
    # Проверка размера файла
    try:
        if file_path.stat().st_size > MAX_FILE_SIZE:
            print(f"⚠️  Пропуск большого файла: {file_path} (>{MAX_FILE_SIZE/1024/1024:.1f} MB)")
            return False
    except OSError:
        return False
    
    return True


def should_skip_directory(dir_path: Path) -> bool:
    """Проверяет, нужно ли пропустить директорию."""
    dir_name = dir_path.name
    
    # Прямое совпадение
    if dir_name in EXCLUDE_DIRS:
        return True
    
    # Скрытые директории (начинаются с точки)
    if dir_name.startswith('.'):
        # Но оставляем некоторые важные
        if dir_name not in {'.github', '.docker'}:
            return True
    
    return False


def collect_files(root_dir: Path) -> Iterator[Path]:
    """Рекурсивно собирает все кодовые файлы из директории."""
    for current_dir, subdirs, files in os.walk(root_dir):
        current_path = Path(current_dir)
        
        # Фильтруем поддиректории (модифицируем список in-place)
        subdirs[:] = [d for d in subdirs if not should_skip_directory(current_path / d)]
        
        # Обрабатываем файлы
        for file_name in files:
            file_path = current_path / file_name
            
            if should_include_file(file_path):
                yield file_path


def format_as_text(files: list[tuple[Path, str]], root_dir: Path) -> str:
    """Форматирует файлы в простой текстовый формат."""
    output = []
    output.append("=" * 80)
    output.append(f"PROJECT CODE EXPORT")
    output.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    output.append(f"Root: {root_dir}")
    output.append(f"Files: {len(files)}")
    output.append("=" * 80)
    output.append("")
    
    for file_path, content in files:
        relative_path = file_path.relative_to(root_dir)
        output.append("")
        output.append("=" * 80)
        output.append(f"FILE: {relative_path}")
        output.append("=" * 80)
        output.append("")
        output.append(content)
        output.append("")
    
    return "\n".join(output)


def format_as_markdown(files: list[tuple[Path, str]], root_dir: Path) -> str:
    """Форматирует файлы в Markdown формат."""
    output = []
    output.append(f"# Project Code Export")
    output.append(f"")
    output.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  ")
    output.append(f"**Root:** `{root_dir}`  ")
    output.append(f"**Files:** {len(files)}  ")
    output.append(f"")
    output.append(f"---")
    output.append(f"")
    
    # Оглавление
    output.append(f"## Table of Contents")
    output.append(f"")
    for idx, (file_path, _) in enumerate(files, 1):
        relative_path = file_path.relative_to(root_dir)
        anchor = str(relative_path).replace('/', '-').replace('\\', '-').replace('.', '')
        output.append(f"{idx}. [{relative_path}](#{anchor})")
    output.append(f"")
    output.append(f"---")
    output.append(f"")
    
    # Содержимое файлов
    for file_path, content in files:
        relative_path = file_path.relative_to(root_dir)
        
        # Определяем язык для подсветки синтаксиса
        ext_to_lang = {
            '.py': 'python',
            '.sql': 'sql',
            '.sh': 'bash',
            '.bat': 'batch',
            '.js': 'javascript',
            '.html': 'html',
            '.css': 'css',
            '.json': 'json',
            '.yaml': 'yaml',
            '.yml': 'yaml',
            '.toml': 'toml',
            '.ini': 'ini',
        }
        lang = ext_to_lang.get(file_path.suffix, '')
        
        output.append(f"## {relative_path}")
        output.append(f"")
        output.append(f"```{lang}")
        output.append(content)
        output.append(f"```")
        output.append(f"")
    
    return "\n".join(output)


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Collect all code files from the project',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        '--output', '-o',
        type=str,
        default='code_export.txt',
        help='Output file path (default: code_export.txt)',
    )
    parser.add_argument(
        '--format', '-f',
        type=str,
        choices=['text', 'markdown'],
        default='text',
        help='Output format (default: text)',
    )
    parser.add_argument(
        '--root', '-r',
        type=str,
        default=None,
        help='Project root directory (default: current directory)',
    )
    
    args = parser.parse_args()
    
    # Определяем корневую директорию
    if args.root:
        root_dir = Path(args.root).resolve()
    else:
        # Ищем корень проекта (где находится этот скрипт)
        script_dir = Path(__file__).resolve().parent
        root_dir = script_dir.parent  # tools/ -> project/
    
    if not root_dir.exists():
        print(f"❌ Директория не найдена: {root_dir}")
        return 1
    
    print(f"📂 Сканирование директории: {root_dir}")
    print(f"🔍 Ищем кодовые файлы...")
    print()
    
    # Собираем файлы
    collected_files: list[tuple[Path, str]] = []
    total_size = 0
    
    for file_path in collect_files(root_dir):
        try:
            # Читаем содержимое
            content = file_path.read_text(encoding='utf-8', errors='ignore')
            collected_files.append((file_path, content))
            total_size += file_path.stat().st_size
            
            # Прогресс
            relative_path = file_path.relative_to(root_dir)
            print(f"✓ {relative_path}")
            
        except Exception as e:
            print(f"⚠️  Ошибка чтения {file_path}: {e}")
            continue
    
    print()
    print(f"✅ Собрано файлов: {len(collected_files)}")
    print(f"📊 Общий размер: {total_size / 1024 / 1024:.2f} MB")
    print()
    
    # Форматируем и сохраняем
    print(f"💾 Сохранение в формате: {args.format}")
    
    if args.format == 'markdown':
        output_content = format_as_markdown(collected_files, root_dir)
    else:
        output_content = format_as_text(collected_files, root_dir)
    
    output_path = Path(args.output)
    output_path.write_text(output_content, encoding='utf-8')
    
    output_size = output_path.stat().st_size / 1024 / 1024
    print(f"✅ Сохранено: {output_path} ({output_size:.2f} MB)")
    print()
    print(f"🎉 Готово!")
    
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
