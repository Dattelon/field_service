import os
import zipfile
from pathlib import Path

source = Path(r'C:\ProjectF')
destination = Path(r'C:\ProjectF\ProjectF_archive.zip')

# Паттерны для исключения
exclude_patterns = [
    '.git',
    '__pycache__',
    '.pytest_cache',
    '.venv',
    'venv',
    'env',
    '.vscode',
    '.idea',
    '.claude',
    'code_snapshot',
    'docs',
    'tests',
    '.local/logs',
    'docker-export/images',
    'dist',
    'build',
    '.DS_Store',
    'Thumbs.db'
]

exclude_extensions = ['.pyc', '.pyo', '.pyd', '.log']

def should_exclude(path: Path) -> bool:
    """Проверяет, нужно ли исключить файл/директорию"""
    path_str = str(path).replace('\\', '/')
    
    # Проверка директорий и паттернов
    for pattern in exclude_patterns:
        if f'/{pattern}/' in path_str or path_str.endswith(f'/{pattern}') or f'\\{pattern}\\' in str(path) or str(path).endswith(f'\\{pattern}'):
            return True
        if pattern in path.parts:
            return True
    
    # Проверка расширений
    if path.suffix in exclude_extensions:
        return True
    
    return False

print('Создаю архив проекта...')
print(f'Исключаю: {", ".join(exclude_patterns)}')
print(f'Расширения: {", ".join(exclude_extensions)}')

# Удаляем старый архив
if destination.exists():
    destination.unlink()
    print(f'Удален старый архив: {destination}')

# Собираем файлы
files_to_archive = []
for root, dirs, files in os.walk(source):
    root_path = Path(root)
    
    # Исключаем директории
    dirs[:] = [d for d in dirs if not should_exclude(root_path / d)]
    
    # Добавляем файлы
    for file in files:
        file_path = root_path / file
        if not should_exclude(file_path):
            files_to_archive.append(file_path)

print(f'\nНайдено файлов для архивации: {len(files_to_archive)}')

# Создаем архив
with zipfile.ZipFile(destination, 'w', zipfile.ZIP_DEFLATED) as zipf:
    for i, file_path in enumerate(files_to_archive, 1):
        arcname = file_path.relative_to(source)
        zipf.write(file_path, arcname)
        
        if i % 100 == 0:
            print(f'Обработано файлов: {i}/{len(files_to_archive)}')

# Информация об архиве
if destination.exists():
    size_mb = destination.stat().st_size / (1024 * 1024)
    print(f'\n✓ Архив создан: {destination}')
    print(f'✓ Размер архива: {size_mb:.2f} МБ')
else:
    print('\n✗ Ошибка создания архива!')
