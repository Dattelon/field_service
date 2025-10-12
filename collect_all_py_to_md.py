#!/usr/bin/env python3
"""
Сборка всех .py файлов проекта в один .md файл
Исключает кэш, venv и служебные директории
"""

from pathlib import Path
from datetime import datetime
import re

# Конфигурация
PROJECT_ROOT = Path(__file__).parent
OUTPUT_FILE = PROJECT_ROOT / "all_python_code.md"

# Директории для исключения
EXCLUDE_DIRS = {
    # Python
    '__pycache__', '.pytest_cache', '.ruff_cache', '.mypy_cache',
    '.tox', '.nox', 'htmlcov', '.coverage',
    # Git
    '.git', '.github',
    # Виртуальные окружения
    'venv', 'env', '.env', '.venv', 'virtualenv',
    # Node.js
    'node_modules',
    # IDE
    '.vscode', '.idea', '.vs',
    # Временные и build
    '.local', 'dist', 'build', 'egg-info',
    # Снапшоты
    'code_snapshot',
    # Backup
    'backup', '.backup',
    # Alembic versions (миграции - можно исключить)
    # 'versions'  # Раскомментируй если не нужны миграции
}

# Паттерны для исключения файлов
EXCLUDE_PATTERNS = {
    '.deprecated', '.backup', '.old', '.bak', '_backup'
}

def should_include_file(file_path: Path) -> bool:
    """Проверяет, нужно ли включать файл"""
    
    # Только .py файлы
    if file_path.suffix != '.py':
        return False
    
    # Проверка на deprecated/backup в имени
    for pattern in EXCLUDE_PATTERNS:
        if pattern in file_path.name.lower():
            return False
    
    # Проверка директорий в пути
    for part in file_path.parts:
        if part in EXCLUDE_DIRS:
            return False
        for pattern in EXCLUDE_PATTERNS:
            if pattern in part.lower():
                return False
    
    return True

def get_file_section(file_path: Path, project_root: Path) -> str:
    """Создаёт секцию для файла в markdown"""
    
    rel_path = file_path.relative_to(project_root)
    rel_path_str = str(rel_path).replace('\\', '/')
    
    # Определяем уровень заголовка по глубине вложенности
    depth = len(rel_path.parts)
    header_level = min(depth + 1, 6)  # Максимум 6 уровней в markdown
    header = '#' * header_level
    
    # Читаем содержимое файла
    try:
        content = file_path.read_text(encoding='utf-8')
        lines_count = content.count('\n') + 1
    except Exception as e:
        content = f"# Oshibka chteniya faila: {e}"
        lines_count = 0
    
    # Формируем секцию
    section = f"\n{header} `{rel_path_str}`\n\n"
    section += f"**Strok:** {lines_count}  \n"
    section += f"**Razmer:** {file_path.stat().st_size / 1024:.2f} KB\n\n"
    section += "```python\n"
    section += content
    section += "\n```\n"
    section += "\n---\n"
    
    return section

def collect_python_files():
    """Собирает все Python файлы в один markdown"""
    
    print(f"Sborka vseh Python failov proekta")
    print(f"Koren: {PROJECT_ROOT}")
    print(f"Vyhodnoy fail: {OUTPUT_FILE}")
    print()
    
    # Находим все .py файлы
    print("Poisk .py failov...")
    py_files = []
    
    for file_path in PROJECT_ROOT.rglob('*.py'):
        if should_include_file(file_path):
            py_files.append(file_path)
    
    # Сортируем файлы по пути для структурированности
    py_files.sort(key=lambda p: str(p.relative_to(PROJECT_ROOT)))
    
    print(f"OK Naydeno failov: {len(py_files)}")
    print()
    
    # Группируем файлы по основным директориям
    file_groups = {}
    for file_path in py_files:
        rel_path = file_path.relative_to(PROJECT_ROOT)
        # Берём первую директорию как группу
        if len(rel_path.parts) > 1:
            group = rel_path.parts[0]
        else:
            group = "kornevaya direktoriya"
        
        if group not in file_groups:
            file_groups[group] = []
        file_groups[group].append(file_path)
    
    # Создаём markdown файл
    print("Sozdanie markdown faila...")
    
    total_lines = 0
    total_size = 0
    
    content = f"""# Field Service - Vse Python faily proekta

**Sozdan:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  
**Vsego failov:** {len(py_files)}  

---

## Statistika po direktoriyam

"""
    
    # Статистика по группам
    for group, files in sorted(file_groups.items()):
        group_size = sum(f.stat().st_size for f in files)
        content += f"- **{group}**: {len(files)} файлов ({group_size / 1024:.2f} KB)\n"
    
    content += f"\n---\n\n## Oglavlenie\n\n"
    
    # Оглавление
    for group, files in sorted(file_groups.items()):
        content += f"\n### {group}\n\n"
        for file_path in files:
            rel_path = file_path.relative_to(PROJECT_ROOT)
            rel_path_str = str(rel_path).replace('\\', '/')
            # Создаём якорь для ссылки (убираем спецсимволы)
            anchor = rel_path_str.lower().replace('/', '-').replace('\\', '-').replace('.', '').replace('_', '-')
            content += f"- [{rel_path_str}](#{anchor})\n"
    
    content += f"\n---\n\n## Ishodnyi kod\n"
    
    # Добавляем содержимое всех файлов
    for i, file_path in enumerate(py_files, 1):
        print(f"  [{i}/{len(py_files)}] {file_path.relative_to(PROJECT_ROOT)}")
        
        section = get_file_section(file_path, PROJECT_ROOT)
        content += section
        
        total_size += file_path.stat().st_size
        try:
            file_content = file_path.read_text(encoding='utf-8')
            total_lines += file_content.count('\n') + 1
        except:
            pass
    
    # Добавляем итоговую статистику в конец
    content += f"\n\n---\n\n## Itogovaya statistika\n\n"
    content += f"- **Vsego failov:** {len(py_files)}\n"
    content += f"- **Vsego strok koda:** {total_lines:,}\n"
    content += f"- **Obshiy razmer:** {total_size / 1024 / 1024:.2f} MB\n"
    content += f"- **Sredniy razmer faila:** {total_size / len(py_files) / 1024:.2f} KB\n"
    content += f"- **Srednee strok v faile:** {total_lines // len(py_files)}\n"
    
    # Записываем в файл
    OUTPUT_FILE.write_text(content, encoding='utf-8')
    
    print()
    print("=" * 70)
    print(f"OK Sborka zavershena uspeshno!")
    print()
    print(f"Itogovaya statistika:")
    print(f"   Failov sobrano: {len(py_files)}")
    print(f"   Vsego strok: {total_lines:,}")
    print(f"   Obshiy razmer: {total_size / 1024 / 1024:.2f} MB")
    print(f"   Razmer markdown: {OUTPUT_FILE.stat().st_size / 1024 / 1024:.2f} MB")
    print()
    print(f"Rezultat: {OUTPUT_FILE}")
    print("=" * 70)

if __name__ == "__main__":
    try:
        collect_python_files()
    except KeyboardInterrupt:
        print("\nPrervano polzovatelem")
    except Exception as e:
        print(f"\nOshibka: {e}")
        import traceback
        traceback.print_exc()
