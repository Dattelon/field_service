#!/usr/bin/env python3
"""
Экспорт кодовой базы Field Service проекта
Создаёт снапшот в папке code_snapshot с сохранением структуры
Оптимизирован для быстрой работы (тихий режим)
"""

import shutil
from pathlib import Path
from datetime import datetime

# Конфигурация
PROJECT_ROOT = Path(__file__).parent
SNAPSHOT_DIR = PROJECT_ROOT / "code_snapshot"

# Расширения файлов для экспорта
INCLUDE_EXTENSIONS = {
    # Код
    '.py', '.pyi',
    # Конфигурация
    '.json', '.yaml', '.yml', '.toml', '.ini', '.cfg', '.conf',
    # Документация
    '.md', '.txt', '.rst',
    # SQL и скрипты
    '.sql', '.sh', '.ps1', '.bat',
    # Docker и CI/CD
    '.dockerignore', '.editorconfig', '.gitattributes',
    # Другие важные
    '.env.example', '.gitignore', '.pre-commit-config.yaml'
}

# Файлы БЕЗ расширения для включения
INCLUDE_NO_EXTENSION = {
    'Dockerfile', 'Makefile', 'Procfile', 'requirements.txt',
    'LICENSE', 'README', 'CHANGELOG', 'CONTRIBUTING'
}

# Директории для исключения
EXCLUDE_DIRS = {
    # Python
    '__pycache__', '.pytest_cache', '.ruff_cache', '.mypy_cache',
    '.tox', '.nox', 'htmlcov', '.coverage',
    # Git
    '.git', '.github',
    # Виртуальные окружения
    'venv', 'env', '.env', '.venv', 'virtualenv',
    # Node.js (если есть фронтенд)
    'node_modules',
    # IDE
    '.vscode', '.idea', '.vs',
    # Временные и build
    '.local', 'dist', 'build', 'egg-info', '*.egg-info',
    # Снапшоты
    'code_snapshot',
    # Backup директории
    'backup', '.backup'
}

# Файлы для исключения
EXCLUDE_FILES = {
    '.DS_Store', 'Thumbs.db', 
    '*.pyc', '*.pyo', '*.pyd',
    '.coverage', 'coverage.xml', 
    '*.log', '*.swp', '*.swo',
    '*~'  # Vim backup files
}

# Паттерны для исключения (deprecated, backup и т.д.)
EXCLUDE_PATTERNS = {
    '.deprecated', '.backup', '.old', '.bak'
}

def should_include_file(file_path: Path) -> bool:
    """Проверяет, нужно ли включать файл в снапшот"""
    
    # Проверка на deprecated/backup в имени файла
    for pattern in EXCLUDE_PATTERNS:
        if pattern in file_path.name.lower():
            return False
    
    # Проверка имени файла
    if file_path.name in EXCLUDE_FILES:
        return False
    
    # Проверка по частям пути (директории)
    for part in file_path.parts:
        if part in EXCLUDE_DIRS:
            return False
        # Проверка на .backup директории
        for pattern in EXCLUDE_PATTERNS:
            if pattern in part.lower():
                return False
    
    # Файлы без расширения - проверяем список
    if not file_path.suffix:
        return file_path.name in INCLUDE_NO_EXTENSION
    
    # Проверка расширения
    return file_path.suffix in INCLUDE_EXTENSIONS

def export_code_snapshot():
    """Создаёт снапшот кодовой базы"""
    
    print(f"🚀 Экспорт кодовой базы Field Service проекта")
    print(f"📂 Корень: {PROJECT_ROOT}")
    print(f"📁 Снапшот: {SNAPSHOT_DIR}")
    print()
    
    # Очистка и создание директории снапшота
    if SNAPSHOT_DIR.exists():
        print("🗑️  Очистка старого снапшота...")
        shutil.rmtree(SNAPSHOT_DIR)
    
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Счётчики
    files_exported = 0
    total_size = 0
    errors = []
    
    # Проход по всем файлам проекта (ТИХИЙ РЕЖИМ)
    print("📦 Сканирование и копирование файлов...")
    
    for file_path in PROJECT_ROOT.rglob('*'):
        if not file_path.is_file():
            continue
        
        if not should_include_file(file_path):
            continue
        
        # Относительный путь от корня проекта
        rel_path = file_path.relative_to(PROJECT_ROOT)
        
        # Целевой путь в снапшоте (с .txt расширением для кода)
        if file_path.suffix in INCLUDE_EXTENSIONS or file_path.name in INCLUDE_NO_EXTENSION:
            target_path = SNAPSHOT_DIR / f"{rel_path}.txt"
        else:
            target_path = SNAPSHOT_DIR / rel_path
        
        # Создание директорий
        target_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Копирование файла
        try:
            shutil.copy2(file_path, target_path)
            files_exported += 1
            total_size += file_path.stat().st_size
        except Exception as e:
            errors.append(f"{rel_path}: {e}")
    
    # Создание README в снапшоте
    readme_content = f"""# Field Service Code Snapshot

**Создан:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  
**Файлов:** {files_exported}  
**Размер:** {total_size / 1024 / 1024:.2f} MB

## 📋 О снапшоте

Все файлы проекта сохранены с исходной структурой директорий.
Файлы кода имеют расширение `.txt` для удобного чтения в любом редакторе.

## 📦 Включённые типы файлов

### Код
- Python: `.py`, `.pyi`

### Конфигурация
- Форматы: `.json`, `.yaml`, `.yml`, `.toml`, `.ini`, `.cfg`, `.conf`
- Docker: `Dockerfile`, `.dockerignore`
- Git: `.gitignore`, `.gitattributes`

### Документация
- Форматы: `.md`, `.txt`, `.rst`

### Скрипты и SQL
- Скрипты: `.sql`, `.sh`, `.ps1`, `.bat`
- Зависимости: `requirements.txt`

### Другие
- `.env.example`, `.editorconfig`, `.pre-commit-config.yaml`

## 🚫 Исключённые файлы

### Директории
{', '.join(sorted(EXCLUDE_DIRS))}

### Паттерны
- Файлы с `.deprecated`, `.backup`, `.old`, `.bak`
- Backup директории (`admin_bot.backup` и т.д.)

### Временные файлы
- `*.pyc`, `*.pyo`, `*.pyd`
- `*.log`, `.DS_Store`, `Thumbs.db`

## 📊 Статистика

- **Всего файлов:** {files_exported}
- **Общий размер:** {total_size / 1024 / 1024:.2f} MB
- **Средний размер файла:** {(total_size / files_exported / 1024):.2f} KB
"""

    if errors:
        readme_content += f"\n## ⚠️ Ошибки при копировании ({len(errors)})\n\n"
        for error in errors[:10]:  # Показываем первые 10 ошибок
            readme_content += f"- {error}\n"
        if len(errors) > 10:
            readme_content += f"\n... и ещё {len(errors) - 10} ошибок\n"
    
    (SNAPSHOT_DIR / "README.md").write_text(readme_content, encoding='utf-8')
    
    # Создание файла-индекса структуры проекта
    structure_content = "# Структура проекта Field Service\n\n"
    structure_content += "```\n"
    
    # Рекурсивно строим дерево (только директории)
    def build_tree(path: Path, prefix: str = "", is_last: bool = True):
        lines = []
        if path.is_dir():
            # Название директории
            connector = "└── " if is_last else "├── "
            lines.append(f"{prefix}{connector}{path.name}/\n")
            
            # Получаем поддиректории
            subdirs = [d for d in sorted(path.iterdir()) if d.is_dir() and d.name not in EXCLUDE_DIRS]
            
            # Рекурсивно обходим
            for i, subdir in enumerate(subdirs):
                extension = "    " if is_last else "│   "
                is_last_subdir = (i == len(subdirs) - 1)
                lines.extend(build_tree(subdir, prefix + extension, is_last_subdir))
        
        return lines
    
    # Строим дерево для field-service
    field_service_path = PROJECT_ROOT / "field-service"
    if field_service_path.exists():
        structure_content += "field-service/\n"
        structure_lines = build_tree(field_service_path / "field_service", "", True)
        structure_content += "".join(structure_lines)
    
    structure_content += "```\n"
    
    (SNAPSHOT_DIR / "PROJECT_STRUCTURE.md").write_text(structure_content, encoding='utf-8')
    
    # Итоговая статистика
    print()
    print("=" * 70)
    print(f"✅ Экспорт завершён успешно!")
    print()
    print(f"📊 Итоговая статистика:")
    print(f"   • Файлов экспортировано: {files_exported}")
    print(f"   • Общий размер: {total_size / 1024 / 1024:.2f} MB")
    print(f"   • Средний размер файла: {(total_size / files_exported / 1024):.2f} KB")
    if errors:
        print(f"   ⚠️  Ошибок при копировании: {len(errors)}")
    print()
    print(f"📁 Результат: {SNAPSHOT_DIR}")
    print("=" * 70)

if __name__ == "__main__":
    try:
        export_code_snapshot()
    except KeyboardInterrupt:
        print("\n⚠️  Прервано пользователем")
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        raise
